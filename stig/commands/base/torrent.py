# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details
# http://www.gnu.org/licenses/gpl-3.0.txt

from ...logging import make_logger
log = make_logger(__name__)

from .. import (InitCommand, ExpectedResource)
from . import _mixin as mixin
from ._common import (make_X_FILTER_spec, make_COLUMNS_doc,
                      make_SORT_ORDERS_doc, make_SCRIPTING_doc)

import asyncio
import os


class CreateTorrentCmdbase(metaclass=InitCommand):
    name = 'create'
    aliases = ()
    provides = set()
    category = 'torrent'
    description = 'Create torrent file or magnet link'
    usage = ('create [<OPTIONS>] <PATH>',)
    examples = ('create path/to/dir -f ~/some.torrent -t http://my.tracker:1234/announce',
                'create path/to/file -m -f ~/another.torrent',
                'create path/to/file -t tracker1:1234/announce -t tracker2:5678/announce')

    NO_TORRENT_FILE = object()
    argspecs = (
        { 'names': ('PATH',),
          'description': "Path to torrent's content" },

        { 'names': ('--name', '-n'),
          'default_description': 'Basename of PATH',
          'description': 'Torrent name' },

        { 'names': ('--file', '-f'), 'nargs': '?', 'default': NO_TORRENT_FILE,
          'default_description': "Torrent name + '.torrent'",
          'description': 'Path to the torrent file' },

        { 'names': ('--yes', '-y'), 'action': 'store_true',
          'description': 'Overwrite FILE without asking' },

        { 'names': ('--magnet', '-m'), 'action': 'store_true',
          'description': 'Create magnet link' },

        { 'names': ('--tracker', '-t'), 'action': 'append',
          'description': "Tracker's announce URL (repeatable)"},

        { 'names': ('--webseed', '-w'), 'action': 'append',
          'description': "Webseed URL (repeatable)"},

        { 'names': ('--httpseed', '-s'), 'action': 'append',
          'description': "HTTP seed URL (repeatable)"},

        { 'names': ('--private', '-p'), 'action': 'store_true',
          'description': 'Only use tracker(s) for peer discovery (no DHT/PEX)'},

        { 'names': ('--comment', '-c'),
          'description': 'Comment that is stored in the torrent file'},

        { 'names': ('--date', '-d'),
          'default_description': 'Current UTC date with time set to 00:00:00',
          'description': ('Creation date as YYYY-MM-DD[ HH:MM[:SS]] '
                          "or '-' to not include creation date") },

        { 'names': ('--xseed', '-x'), 'action': 'store_true',
          'description': 'Randomize info hash to help with cross-seeding' },
    )

    srvapi = ExpectedResource

    DATE_FORMATS = ('%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%d %H:%M',
                    '%Y-%m-%dT%H:%M',
                    '%Y-%m-%d')

    async def run(self, **args):
        from torf import Torrent
        from ...client import URL
        from datetime import datetime

        try:
            self.torrent = torf.Torrent(
                path               = args['PATH'],
                name               = args['name'],
                trackers           = (str(URL(url)) for url in args['tracker'] or ()),
                webseeds           = (str(URL(url)) for url in args['webseed'] or ()),
                httpseeds          = (str(URL(url)) for url in args['httpseed'] or ()),
                comment            = args['comment'],
                private            = args['private'],
                randomize_infohash = args['xseed'],
            )
        except torf.TorfError as e:
            log.error(str(e))
            return False

        def get_date(date_str):
            if date_str == '-':
                return None
            elif date_str is None:
                return datetime.utcnow().replace(hour=0, minute=0, second=0,
                                                 microsecond=0)
            else:
                for f in self.DATE_FORMATS:
                    try:
                        date = datetime.strptime(date_str, f)
                    except ValueError:
                        pass
                    else:
                        return date
                raise ValueError('Invalid date: %r' % date_str)

        try:
            self.torrent.creation_date = get_date(args['date'])
        except ValueError as e:
            log.error(str(e))
            return False

        generate_args = {'torrent_filehandle': None, 'create_magnet': False}
        remove_torrent_file_on_failure = True
        self.torrent_filepath = torrent_filepath = None

        if args['magnet']:
            generate_args['create_magnet'] = True

        if not args['magnet'] or args['file'] is not None:
            if args['file'] is None:
                self.torrent_filepath = torrent_filepath = self.torrent.name + '.torrent'
            else:
                self.torrent_filepath = torrent_filepath = args['file']

            # Open file now so we can fail early or have a guaranteed place to
            # write the generated torrent data
            overwrite_question = 'Overwrite torrent file %s?' % torrent_filepath
            if os.path.exists(torrent_filepath):
                if os.path.isdir(torrent_filepath):
                    log.error('Torrent file is a directory: %s' % torrent_filepath)
                    return False

                if args['yes'] or await self.ask_yes_no(overwrite_question):
                    generate_args['torrent_filehandle'] = \
                        self._get_torrent_filehandle(torrent_filepath)
                    remove_torrent_file_on_failure = False
            else:
                generate_args['torrent_filehandle'] = \
                    self._get_torrent_filehandle(torrent_filepath)

        # Torrent creation and progress display is implemented per UI
        if generate_args['torrent_filehandle'] or generate_args['create_magnet']:
            success = False
            try:
                success = self.generate(**generate_args)
            finally:
                # If generate() failed and torrent_filepath didn't exist
                # already, we should remove it
                if not success and torrent_filepath and remove_torrent_file_on_failure:
                    try:
                        os.remove(torrent_filepath)
                        log.debug('Removed unfinished torrent file: %r', torrent_filepath)
                    except Exception:
                        pass

    def _get_torrent_filehandle(self, torrent_filepath):
        try:
            # Open file for writing without truncating in case it already exists
            fd = os.open(torrent_filepath, os.O_RDWR | os.O_CREAT,
                         mode=0o666)  # No execution
            return os.fdopen(fd, 'rb+')
        except OSError as e:
            log.error('Unable to write torrent file: %s' % torrent_filepath)


class ListTorrentsCmdbase(mixin.get_torrent_sorter, mixin.get_torrent_columns,
                          metaclass=InitCommand):
    name = 'list'
    aliases = ('ls',)
    provides = set()
    category = 'torrent'
    description = 'List torrents'
    usage = ('list [<OPTIONS>]',
             'list [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('ls active',
                'ls !active',
                'ls seeds<10',
                'ls active&tracker~example.org',
                'ls active|idle&tracker~example')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=False, nargs='*'),

        { 'names': ('--sort', '-s'),
          'default_description': "current value of 'sort.torrents' setting",
          'description': ('Comma-separated list of sort orders '
                          "(see SORT ORDERS section)") },

        { 'names': ('--columns', '-c'),
          'default_description': "current value of 'columns.torrents' setting",
          'description': ('Comma-separated list of column names '
                          "(see COLUMNS section)") },
    )

    from ...views.trackerlist import COLUMNS
    from ...client.sorters.tsorter import TorrentSorter
    more_sections = {
        'COLUMNS': make_COLUMNS_doc(COLUMNS, '--columns', 'columns.torrents'),
        'SORT ORDERS': make_SORT_ORDERS_doc(TorrentSorter, '--sort', 'sort.torrents'),
        'SCRIPTING': make_SCRIPTING_doc(name),
    }

    cfg = ExpectedResource

    async def run(self, TORRENT_FILTER, sort, columns):
        sort = self.cfg['sort.torrents'].value if sort is None else sort
        columns = self.cfg['columns.torrents'].value if columns is None else columns
        try:
            columns = self.get_torrent_columns(columns)
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=True,
                                           discover_torrent=False)
            sort = self.get_torrent_sorter(sort)
        except ValueError as e:
            log.error(e)
            return False
        else:
            log.debug('Listing %s torrents sorted by %s', tfilter, sort)
            if asyncio.iscoroutinefunction(self.make_tlist):
                return await self.make_tlist(tfilter, sort, columns)
            else:
                return self.make_tlist(tfilter, sort, columns)


class TorrentSummaryCmdbase(mixin.get_torrent, metaclass=InitCommand):
    name = 'summary'
    aliases = ('info', 'details')
    provides = set()
    category = 'torrent'
    description = 'Display detailed torrent information'
    usage = ('summary',
             'summary <TORRENT FILTER>')
    examples = ('summary id=71',)
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='?'),
    )
    srvapi = ExpectedResource

    async def run(self, TORRENT_FILTER):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            log.error(e)
            return False
        else:
            log.debug('Showing summary of torrent: %r', tfilter)
            if asyncio.iscoroutinefunction(self.display_summary):
                return await self.display_summary(tfilter)
            else:
                return self.display_summary(tfilter)


class AddTorrentsCmdbase(metaclass=InitCommand):
    name = 'add'
    aliases = ('download','get')
    provides = set()
    category = 'torrent'
    description = 'Download torrents'
    usage = ('add [<OPTIONS>] <TORRENT> <TORRENT> <TORRENT> ...',)
    examples = ('add 72d7a3179da3de7a76b98f3782c31843e3f818ee',
                'add --stopped http://example.org/something.torrent')
    argspecs = (
        { 'names': ('TORRENT',), 'nargs': '+',
          'description': 'Link or path to torrent file, magnet link or hash' },

        { 'names': ('--stopped','-s'), 'action': 'store_true',
          'description': 'Do not start downloading the added torrent(s)' },

        { 'names': ('--path','-p'),
          'description': 'Custom download directory for added torrent(s)' },
    )
    srvapi = ExpectedResource

    async def run(self, TORRENT, stopped, path):
        success = True
        force_torrentlist_update = False
        for source in TORRENT:
            response = await self.make_request(self.srvapi.torrent.add(source, stopped=stopped, path=path))
            success = success and response.success
            force_torrentlist_update = force_torrentlist_update or success

        # Update torrentlist AFTER all 'add' requests
        if force_torrentlist_update and hasattr(self, 'polling_frenzy'):
            self.polling_frenzy()
        return success


class MoveTorrentsCmdbase(metaclass=InitCommand):
    name = 'move'
    aliases = ('mv',)
    provides = set()
    category = 'torrent'
    description = "Change torrents' location"
    usage = ('move <PATH>',
             'move <TORRENT FILTER> <PATH>')
    examples = ('move new/path',
                'move size>50g path/to/lots/of/storage')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='?'),
        {'names': ('PATH',),
         'description': ('New location of the specified torrent(s).  If PATH is relative '
                         '(does not start with "/"), it is relative to the value of the '
                         'setting "srv.path.complete".')},
    )
    srvapi = ExpectedResource

    async def run(self, TORRENT_FILTER, PATH):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            log.error(e)
            return False
        else:
            response = await self.make_request(self.srvapi.torrent.move(tfilter, PATH),
                                               polling_frenzy=True)
            return response.success


class RemoveTorrentsCmdbase(metaclass=InitCommand):
    name = 'remove'
    aliases = ('rm', 'delete')
    provides = set()
    category = 'torrent'
    description = 'Remove torrents'
    usage = ('remove [<OPTIONS>]',
             'remove [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('remove',
                'remove "stupid torrent" silly\ torrent and_this_torrent',
                'remove -d "unwanted torrent"')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),
        { 'names': ('--delete-files','-d'), 'action': 'store_true',
          'description': 'Delete any downloaded files' },
    )
    srvapi = ExpectedResource
    cfg = ExpectedResource

    async def run(self, TORRENT_FILTER, delete_files):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            log.error(e)
            return False
        else:
            async def do_remove(tfilter=tfilter, delete_files=delete_files):
                response = await self.make_request(
                    self.srvapi.torrent.remove(tfilter, delete=delete_files),
                    polling_frenzy=True)
                return response.success

            response = await self.srvapi.torrent.torrents(tfilter, keys=('id',))
            hits = len(response.torrents)
            if hits > self.cfg['remove.max-hits'].value:
                await self.show_list_of_hits(tfilter)
                question = 'Are you sure you want to remove %d torrent%s?' % (
                    hits, '' if hits == 1 else 's')
                return await self.ask_yes_no(question, yes=do_remove,
                                             after=self.remove_list_of_hits)
            else:
                return await do_remove()


# Argument definitions that are shared between commands
ARGSPEC_TOGGLE = {
    'names': ('--toggle','-t'), 'action': 'store_true',
    'description': ('Start TORRENT if stopped and vice versa')
}

class StartTorrentsCmdbase(metaclass=InitCommand):
    name = 'start'
    aliases = ()
    provides = set()
    category = 'torrent'
    description = 'Start downloading torrents'
    usage = ('start [<OPTIONS>]',
             'start [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('start',
                "start 'night of the living dead' Metropolis",
                'start ubuntu --force')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),
        { 'names': ('--force','-f'), 'action': 'store_true',
          'description': 'Ignore download queue' },
        ARGSPEC_TOGGLE,
    )
    srvapi = ExpectedResource

    async def run(self, TORRENT_FILTER, toggle, force):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            log.error(e)
            return False
        else:
            if toggle:
                response = await self.make_request(
                    self.srvapi.torrent.toggle_stopped(tfilter, force=force),
                    polling_frenzy=True)
            else:
                response = await self.make_request(
                    self.srvapi.torrent.start(tfilter, force=force),
                    polling_frenzy=True)
            return response.success


class StopTorrentsCmdbase(metaclass=InitCommand):
    name = 'stop'
    aliases = ('pause',)
    provides = set()
    category = 'torrent'
    description = 'Stop downloading torrents'
    usage = ('stop [<OPTIONS>]',
             'stop [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('stop',
                'stop "night of the living dead" idle',
                'stop --toggle ubuntu')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),
        ARGSPEC_TOGGLE,
    )
    srvapi = ExpectedResource

    async def run(self, TORRENT_FILTER, toggle):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            log.error(e)
            return False
        else:
            if toggle:
                response = await self.make_request(
                    self.srvapi.torrent.toggle_stopped(tfilter),
                    polling_frenzy=True)
            else:
                response = await self.make_request(
                    self.srvapi.torrent.stop(tfilter),
                    polling_frenzy=True)
            return response.success


class VerifyTorrentsCmdbase(metaclass=InitCommand):
    name = 'verify'
    aliases = ('check',)
    provides = set()
    category = 'torrent'
    description = 'Verify downloaded torrent data'
    usage = ('verify [<OPTIONS>]',
             'verify [<OPTIONS>] <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('verify',
                'verify debian')
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),
    )
    srvapi = ExpectedResource

    async def run(self, TORRENT_FILTER):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            log.error(e)
            return False
        else:
            response = await self.make_request(self.srvapi.torrent.verify(tfilter),
                                               polling_frenzy=False)
            return response.success
