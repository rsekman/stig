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

import urwid

from ..scroll import ScrollBar
from ..table import Table
from .trklist_columns import TUICOLUMNS
from . import (ItemWidgetBase, ListWidgetBase)


class TrackerItemWidget(ItemWidgetBase):
    palette_unfocused = 'trackerlist'
    palette_focused   ='trackerlist.focused'
    columns_focus_map = {}
    for col in TUICOLUMNS.values():
        columns_focus_map.update(col.style.focus_map)


class TrackerListWidget(ListWidgetBase):
    TUICOLUMNS = TUICOLUMNS
    ListItemClass = TrackerItemWidget
    keymap_context = 'tracker'
    palette_name = 'trackerlist'

    def __init__(self, srvapi, keymap, torfilter, trkfilter, columns=None, sort=None, title=None):
        super().__init__(srvapi, keymap, columns=columns, sort=sort, title=title)
        self._torfilter = torfilter
        self._trkfilter = trkfilter

        # Create tracker filter generator
        if trkfilter is not None:
            def filter_trackers(trackers):
                yield from trkfilter.apply(trackers)
        else:
            def filter_trackers(trackers):
                yield from trackers
        self._maybe_filter_trackers = filter_trackers

        self._poller = self._srvapi.create_poller(
            self._srvapi.torrent.torrents, torfilter, keys=('trackers', 'name', 'id'))
        self._poller.on_response(self._handle_trackers)

    def _handle_trackers(self, response):
        if response is None or not response.torrents:
            self.clear()
        else:
            def trackers_combined(torrents):
                for t in torrents:
                    yield from self._maybe_filter_trackers(t['trackers'])
            self._items = {trk['id']:trk for trk in trackers_combined(response.torrents)}
        self._invalidate()

    @property
    def sort(self):
        return self._sort

    @sort.setter
    def sort(self, sort):
        ListWidgetBase.sort.fset(self, sort)
        self._poller.poll()

    @property
    def title_name(self):
        if self._title is None:
            # self._torfilter is either None or a TorrentFilter instance
            title = str(self._torfilter or 'all')
            if self._trkfilter:
                title += ' %s' % self._trkfilter
            return title
        else:
            return ListWidgetBase.title_name.fget(self)