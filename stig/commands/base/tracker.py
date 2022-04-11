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

import asyncio
from collections import abc

from ... import objects
from ...completion import candidates
from .. import CmdError, CommandMeta
from . import _mixin as mixin
from ._common import (make_COLUMNS_doc, make_SCRIPTING_doc, make_SORT_ORDERS_doc,
                      make_X_FILTER_spec)

from ...logging import make_logger  # isort:skip
log = make_logger(__name__)


class ListTrackersCmdbase(mixin.get_tracker_sorter, mixin.get_tracker_columns,
                          mixin.get_tracker_filter, metaclass=CommandMeta):
    name = 'trackerlist'
    aliases = ('trkls', 'lstrk')
    provides = set()
    category = 'tracker'
    description = 'List tracker(s) of torrent(s)'
    usage = ('trackerlist [<OPTIONS>]',
             'trackerlist [<OPTIONS>] <TORRENT FILTER>',
             'trackerlist [<OPTIONS>] <TORRENT FILTER> <TRACKER FILTER>')
    examples = ("trackerlist 'name~debian'",
                "trackerlist tracker=my.tracker.local error")
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='?'),
        make_X_FILTER_spec('TRACKER', or_focused=True, nargs='?'),

        {'names': ('--sort', '-s'),
         'default_description': "current value of 'sort.trackers' setting",
         'description': ('Comma-separated list of sort orders '
                         "(see SORT ORDERS section)")},

        {'names': ('--columns', '-c'),
         'default_description': "current value of 'columns.trackers' setting",
         'description': ('Comma-separated list of column names '
                         "(see COLUMNS section)")},
    )

    from ...client.sorters import TrackerSorter
    from ...views.tracker import COLUMNS
    more_sections = {
        'COLUMNS': make_COLUMNS_doc(COLUMNS, '--columns', 'columns.trackers', append=(
            '',
            'The "torrent" column is added automatically if multiple '
            'torrents could be listed potentially.')),
        'SORT ORDERS': make_SORT_ORDERS_doc(TrackerSorter, '--sort', 'sort.trackers'),
        'SCRIPTING': make_SCRIPTING_doc(name),
    }

    async def run(self, TORRENT_FILTER, TRACKER_FILTER, sort, columns):
        columns = objects.localcfg['columns.trackers'] if columns is None else columns
        sort = objects.localcfg['sort.trackers'] if sort is None else sort
        try:
            torfilter = self.select_torrents(TORRENT_FILTER,
                                             allow_no_filter=True,
                                             discover_torrent=True)
            trkfilter = self.get_tracker_filter(TRACKER_FILTER)
            sort      = self.get_tracker_sorter(sort)
            columns   = self.get_tracker_columns(columns)
        except ValueError as e:
            raise CmdError(e)

        # Unless we're listing trackers of exactly one torrent, specified by its
        # ID, automatically add the 'torrent' column.
        if 'torrent' not in columns and \
           (not isinstance(torfilter, abc.Sequence) or len(torfilter) != 1):
            columns += ('torrent',)

        log.debug('Listing %s trackers of %s torrents', trkfilter, torfilter)

        if asyncio.iscoroutinefunction(self.make_tracker_list):
            await self.make_tracker_list(torfilter, trkfilter, sort, columns)
        else:
            self.make_tracker_list(torfilter, trkfilter, sort, columns)

    @classmethod
    def completion_candidates_posargs(cls, args):
        """Complete positional arguments"""
        posargs = args.posargs({('--columns', '-c'): 1,
                                ('--sort', '-s'): 1})
        if posargs.curarg_index == 1:
            return candidates.torrent_filter(args.curarg)
        elif posargs.curarg_index == 2:
            torrent_filter = posargs[1]
            return candidates.tracker_filter(args.curarg, torrent_filter)

    @classmethod
    def completion_candidates_params(cls, option, args):
        """Complete parameters (e.g. --option parameter1,parameter2)"""
        if option == '--columns':
            return candidates.column_names('trackers')
        elif option == '--sort':
            return candidates.sort_orders('TrackerSorter')


class AnnounceCmdbase(metaclass=CommandMeta):
    name = 'announce'
    aliases = ('an',)
    provides = set()
    category = 'tracker'
    description = 'Announce torrents to their trackers now if possible'
    usage = ('announce',
             'announce <TORRENT FILTER> <TORRENT FILTER> ...')
    examples = ('announce tracker~example.org',)
    argspecs = (
        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='*'),
    )

    async def run(self, TORRENT_FILTER):
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            raise CmdError(e)
        else:
            response = await self.make_request(
                objects.srvapi.torrent.announce(tfilter),
                polling_frenzy=False)
            if not response.success:
                raise CmdError()

    @classmethod
    def completion_candidates_posargs(cls, args):
        """Complete positional arguments"""
        return candidates.torrent_filter(args.curarg)


class TrackerCmdbase(metaclass=CommandMeta):
    name = 'tracker'
    aliases = ('trk',)
    provides = set()
    category = 'tracker'
    description = 'Add/Remove trackers to/from torrents'
    _ADD_ACTIONS = ('add',)
    _REMOVE_ACTIONS = ('remove', 'rm')
    _ALL_ACTIONS = _ADD_ACTIONS + _REMOVE_ACTIONS
    usage = ('tracker %s <URL>' % '|'.join(_ALL_ACTIONS),
             'tracker %s <TORRENT FILTER> <URL> <URL> ...' % '|'.join(_ALL_ACTIONS))

    examples = ('tracker add !tracker http://tracker3.example.org:12345/announce',
                'tracker remove all tracker1.example tracker2.example ')
    argspecs = (
        {'names': ('ACTION',)},

        make_X_FILTER_spec('TORRENT', or_focused=True, nargs='?'),

        {'names': ('URL',), 'nargs': '+',
         'description': ('Announce URL to add to or remove from matching torrents; '
                         'may be partial (e.g. domain name) when removing trackers')},
    )

    async def run(self, ACTION, TORRENT_FILTER, URL):
        urls = tuple(URL)
        try:
            tfilter = self.select_torrents(TORRENT_FILTER,
                                           allow_no_filter=False,
                                           discover_torrent=True)
        except ValueError as e:
            raise CmdError(e)

        if any(ACTION == action for action in self._ADD_ACTIONS):
            request = objects.srvapi.torrent.tracker_add(tfilter, urls)
            log.debug('Adding trackers to %s torrents: %s', tfilter, ', '.join(urls))
        elif any(ACTION == action for action in self._REMOVE_ACTIONS):
            request = objects.srvapi.torrent.tracker_remove(tfilter, urls, partial_match=True)
            log.debug('Removing trackers from %s torrents: %s', tfilter, ', '.join(urls))
        else:
            raise CmdError('Invalid ACTION: %r' % (ACTION,))

        response = await self.make_request(request, polling_frenzy=True)
        if not response.success:
            raise CmdError()

    @classmethod
    def completion_candidates_posargs(cls, args):
        """Complete positional arguments"""
        if args.curarg_index == 1:
            return candidates.Candidates(('add', 'remove'), label='Action')
        elif args.curarg_index == 2:
            return candidates.torrent_filter(args.curarg)
