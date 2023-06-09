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

import os

import urwid
from natsort import humansorted

from .. import objects, utils
from ..client import constants as const
from .main import redraw_screen

# Workaround for urwid bug: When a Text widget is initialized with an empty
# string, subsequent set_text() calls have no effect.
EMPTY_TEXT = ' '


class KeyChainsWidget(urwid.WidgetWrap):
    _sizing = ['flow']
    _headers = ('Key Chain', 'Command', 'Description')

    def selectable(self):
        return False

    def __init__(self):
        self._pile = urwid.Pile([])
        super().__init__(urwid.AttrMap(self._pile, 'keychains'))

    def update(self, keymap, context, active_keychains, keys_given):
        active_keychains = list(active_keychains)
        self._pile.contents[:] = []
        if not active_keychains:
            return

        # Find number of keychain columns
        key_col_num = max(len(kc) for kc,action in active_keychains)

        # Find widest key for each column (each key is in its own cell)
        key_col_widths = [0] * key_col_num
        for kc,action in active_keychains:
            for colnum in range(key_col_num):
                try:
                    width = len(kc[colnum])
                except IndexError:
                    width = 0
                key_col_widths[colnum] = max(key_col_widths[colnum], width)
        # Total key chain column width is:
        # max(len(key) for each key) + (1 space between keys)
        key_col_width = sum(key_col_widths) + key_col_num - 1

        # Create list of rows
        keychain_col_width = max(len(self._headers[0]), key_col_width)
        spacer = ('pack' , urwid.Text('  '))
        rows = [
            # First row is the headers
            urwid.AttrMap(urwid.Columns([
                (keychain_col_width, urwid.Text(self._headers[0])),
                spacer,
                urwid.Text(self._headers[1]),
                spacer,
                urwid.Text(self._headers[2]),
            ]), 'keychains.header')
        ]
        next_key_index = len(keys_given)
        if len(active_keychains) > 10:
            active_keychains = self._compress_keychains(active_keychains, next_key_index)
        for kc,action in humansorted(active_keychains, key=lambda x: str(x[0])):
            row = []
            for colnum in range(key_col_num):
                colwidth = key_col_widths[colnum]
                try:
                    keytext = kc[colnum].ljust(colwidth)
                except IndexError:
                    # This keychain is shorter than the longest one
                    row.append(('pack', urwid.Text(('keychains.keys', ''.ljust(colwidth)))))
                else:
                    # Highlight the key the user needs to press to advance keychain
                    attrs = ('keychains.keys.next' if colnum == next_key_index else 'keychains.keys')
                    row.append(('pack', urwid.Text((attrs, keytext))))

                # Add space between this key cell and the next unless this is the last column
                if colnum < key_col_num - 1:
                    row.append(('pack', urwid.Text(('keychains.keys', ' '))))

            # Fill remaining space if 'Key Chain' header is longer than all key chains
            remaining_width = keychain_col_width - key_col_width
            row.append(('pack', urwid.Text(('keychains.keys', ''.ljust(remaining_width)))))

            row.append(spacer)
            row.append(urwid.AttrMap(urwid.Text(str(action)),
                                     'keychains.action'))
            row.append(spacer)
            row.append(urwid.AttrMap(urwid.Text(keymap.get_description(kc, context)),
                                     'keychains.description'))

            rows.append(urwid.Columns(row))

        options = self._pile.options('pack')
        for row in rows:
            self._pile.contents.append((row, options))

    @staticmethod
    def _compress_keychains(keychains, next_key_index):
        # Cut off any keys after next_key_index and deduplilcate the resulting
        # shortened keys.
        # Example: <a> <b> <1> command with argument 1
        #          <a> <b> <2> command with argument 2
        #          <a> <b> <3> command with argument 3
        # Becomes: <a> <b> …   command with argument …
        reduced = {}
        for kc,action in keychains:
            key = kc[:next_key_index + 1]
            if key != kc:
                subkeychains = (action for kc,action in keychains
                                if kc.startswith(key))
                action = utils.string.common_substring(*subkeychains)
                key += ('…',)
            if key not in reduced:
                reduced[key] = action
        return tuple(reduced.items())


class QuickHelpWidget(urwid.Text):
    def __init__(self):
        super().__init__('')

    def update(self):
        def get_key(cmd, contexts):
            """
            Return shortest key sequence that executes `cmd` in any context given in
            `contexts`
            """
            from .tuiobjects import keymap
            for context in contexts:
                keys = tuple(keymap.keys(lambda key,action: action.startswith(cmd), context))
                if keys:
                    return sorted(keys, key=lambda k: len(k))[0]

        def get_first_key(cmd, contexts):
            """Same as `get_key`, but return only first key of key sequence"""
            key = get_key(cmd, contexts)
            if isinstance(key, tuple):  # key is a key sequence
                return key[0]
            else:
                return key

        def maybe_add_entry(items, label, key):
            if key is not None:
                items.append([('topbar.help.space',  '   '),
                              ('topbar.help.key',    str(key)),
                              ('topbar.help.equals', ' '),
                              ('topbar.help.label',  label)])

        items = []
        maybe_add_entry(items, 'Settings', get_key('tab set', contexts=('main', None)))
        maybe_add_entry(items, 'Save', get_key('dump', contexts=('main', None)))
        maybe_add_entry(items, 'Prompt', get_key('tui show cli', contexts=('main', None)))
        maybe_add_entry(items, 'Quit', get_key('quit', contexts=('main', None)))
        maybe_add_entry(items, 'Help', get_first_key('tab help', contexts=('main', None)))
        self.set_text(items) if items else self.set_text('')


class ConnectionStatusWidget(urwid.WidgetWrap):
    def __init__(self):
        self._text = urwid.Text('Not connected')
        self._attrmap = urwid.AttrMap(self._text, 'topbar.host.disconnected')
        super().__init__(self._attrmap)
        objects.srvapi.rpc.on('connecting', self._handle_connecting)
        objects.srvapi.rpc.on('connected', self._handle_connected)
        objects.srvapi.rpc.on('disconnected', self._handle_disconnected)
        objects.srvapi.rpc.on('error', self._handle_error)

    @staticmethod
    def _connection_string(rpc):
        string = '%s:%s' % (rpc.host, int(rpc.port))
        if rpc.tls:
            string = 'https://' + string
        return string

    @redraw_screen
    def _handle_connecting(self, rpc):
        self._text.set_text('Connecting to %s' % self._connection_string(rpc))
        self._attrmap.set_attr_map({None: 'topbar.host.connecting'})

    @redraw_screen
    def _handle_connected(self, rpc):
        self._text.set_text('%s Transmission %s' % (self._connection_string(rpc), rpc.version))
        self._attrmap.set_attr_map({None: 'topbar.host.connected'})

    @redraw_screen
    def _handle_disconnected(self, rpc):
        self._text.set_text(self._connection_string(rpc))
        self._attrmap.set_attr_map({None: 'topbar.host.disconnected'})

    @redraw_screen
    def _handle_error(self, rpc, error):
        from ..client import RPCError
        if not isinstance(error, RPCError):
            self._text.set_text(str(error))  # error should also contain url
            self._attrmap.set_attr_map({None: 'topbar.host.disconnected'})


class BandwidthStatusWidget(urwid.Widget):
    _RATE_WIDTH = 6
    _SPACER_WIDTH = 1
    _TAIL_WIDTH = 5

    def __init__(self):
        self._text_up = urwid.Text('', align='right')
        self._text_up_limit = urwid.Text('')
        self._text_dn = urwid.Text('', align='right')
        self._text_dn_limit = urwid.Text('')

        spacer = urwid.AttrMap(urwid.SolidFill(' '), 'bottombar')
        self._spacer_canvas = spacer.render((self._SPACER_WIDTH, 1))

        def mkattr(text, attrsname):
            return urwid.AttrMap(urwid.Padding(text), attrsname)

        self._attr_up = mkattr(self._text_up, 'bottombar.bandwidth.up')
        self._attr_up_limit = mkattr(self._text_up_limit, 'bottombar.bandwidth.up')
        self._attr_dn = mkattr(self._text_dn, 'bottombar.bandwidth.down')
        self._attr_dn_limit = mkattr(self._text_dn_limit, 'bottombar.bandwidth.down')

        self._up_limit_width = 0
        self._dn_limit_width = 0
        self._connected = False

        objects.srvapi.status.on_update(self._update_current_rates)
        objects.srvapi.settings.on_update(self._update_rate_limits)

    @redraw_screen
    def _invalidate(self):
        super()._invalidate()

    def _update_current_rates(self, status):
        up = status.rate_up
        if up is not const.DISCONNECTED:
            up_attrs = 'bottombar.bandwidth.up.highlighted' if up > 0 else 'bottombar.bandwidth.up'
            self._text_up.set_text((up_attrs, up.without_unit))

        dn = status.rate_down
        if dn is not const.DISCONNECTED:
            dn_attrs = 'bottombar.bandwidth.down.highlighted' if dn > 0 else 'bottombar.bandwidth.down'
            self._text_dn.set_text((dn_attrs, dn.without_unit))
            self._connected = True
        else:
            self._connected = False
        self._invalidate()

    def _update_rate_limits(self, settings):
        up = settings['limit.rate.up']
        dn = settings['limit.rate.down']

        # Empty display if DISCONNECTED or UNLIMITED
        def as_str(rate):
            return ('' if rate in (const.DISCONNECTED, const.UNLIMITED)
                    else '/%s' % rate.without_unit)
        self._text_up_limit.set_text(as_str(up))
        self._text_dn_limit.set_text(as_str(dn))

        self._up_limit_width = len(self._text_up_limit.text)
        self._dn_limit_width = len(self._text_dn_limit.text)
        self._invalidate()

    def _mk_tail_canv(self, direction, icon):
        unit = {'bit': 'b', 'byte': 'B'}[objects.localcfg['unit.bandwidth']]
        text = urwid.Text('%s/s %s' % (unit, icon))
        attr_text = urwid.AttrMap(text, 'bottombar.bandwidth.%s' % direction)
        return attr_text.render((self._TAIL_WIDTH,))

    def render(self, size, focus=False):
        if not self._connected:
            size = self.pack(size)
            return urwid.AttrMap(urwid.SolidFill(' '), 'bottombar').render(size)

        canv_up_tail = self._mk_tail_canv('up', '↑')
        canv_dn_tail = self._mk_tail_canv('down', '↓')

        # List of (canvas, position, focus) tuples
        combinelist = []

        # Download
        canv_dn = self._attr_dn.render((self._RATE_WIDTH,))
        combinelist.append((canv_dn, None, False, self._RATE_WIDTH))
        if self._dn_limit_width > 0:
            canv_dn_limit = self._attr_dn_limit.render((self._dn_limit_width,))
            combinelist.append((canv_dn_limit, None, False, self._dn_limit_width))
        combinelist.append((canv_dn_tail, None, False, self._TAIL_WIDTH))

        combinelist.append((self._spacer_canvas, None, False, self._SPACER_WIDTH))

        # Upload
        canv_up = self._attr_up.render((self._RATE_WIDTH,))
        combinelist.append((canv_up, None, False, self._RATE_WIDTH))
        if self._up_limit_width > 0:
            canv_up_limit = self._attr_up_limit.render((self._up_limit_width,))
            combinelist.append((canv_up_limit, None, False, self._up_limit_width))
        combinelist.append((canv_up_tail, None, False, self._TAIL_WIDTH))

        return urwid.CanvasJoin(combinelist)

    _sizing = ['fixed']

    def rows(self, size, focus=False):
        return 1

    def pack(self, size, focus=False):
        cols = ((self._RATE_WIDTH * 2) + (self._TAIL_WIDTH * 2) +
                self._dn_limit_width + self._up_limit_width +
                self._SPACER_WIDTH)
        return (cols, 1)


class TorrentCountersWidget(urwid.WidgetWrap):
    def __init__(self):
        self._text = urwid.Text(EMPTY_TEXT)
        super().__init__(urwid.AttrMap(self._text, 'bottombar'))
        objects.srvapi.status.on_update(self._update_counters)

    def _update_counters(self, status):
        counters = status.count
        if const.DISCONNECTED in counters:
            self._text.set_text('')
            return

        parts = []
        for name in ('downloading', 'uploading', 'stopped'):
            count = getattr(counters, name)
            if count > 0:
                parts.append('%d %s' % (count, name))

        text = ['%s torrents' % counters.total]
        if parts:
            text[-1] += ': ' + ', '.join(parts)

        if counters.isolated > 0:
            text[-1] += ', '
            text.append(('bottombar.important', '%s isolated' % counters.isolated))

        self._text.set_text(text)


class AvailableDiskSpaceWidget(urwid.WidgetWrap):
    def __init__(self):
        self._text = urwid.Text(EMPTY_TEXT)
        self._cached_freespace = None
        super().__init__(urwid.AttrMap(self._text, 'bottombar'))
        objects.srvapi.freespace.on_update(self._update_diskspace)

    def _update_diskspace(self, freespace):
        self._cached_freespace = freespace
        parts = []
        for path,info in freespace.info.items():
            if isinstance(info.path, str):
                if info.error is not None:
                    errmsg = getattr(info.error, 'message', info.error)
                    text = '%s: %s' % (os.path.basename(info.path), errmsg)
                    attr = 'bottombar.important'
                    parts.append((attr, text))
                    parts.append(('bottombar', '  '))
                elif info.free is not None:
                    text = '%s %s' % (os.path.basename(info.path), info.free)
                    if info.free <= objects.localcfg['tui.free-space.low']:
                        attr = 'bottombar.important'
                    else:
                        attr = 'bottombar'
                    parts.append((attr, text))
                    parts.append(('bottombar', '  '))
        if parts:
            parts.insert(0, 'Free: ')
            self._text.set_text(parts[:-1])
        else:
            self._text.set_text('')

    def refresh(self):
        if self._cached_freespace is not None:
            self._update_diskspace(self._cached_freespace)


class MarkedItemsWidget(urwid.WidgetWrap):
    def __init__(self):
        self._text = urwid.Text(('bottombar', ' '))
        super().__init__(self._text)

    def update(self, count):
        if count > 0:
            new_text = ('bottombar.marked', ' %d marked ' % count)
        else:
            new_text = ('bottombar', EMPTY_TEXT)

        if new_text != self._text.text:
            self._text.set_text(new_text)
