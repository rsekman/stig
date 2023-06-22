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

from collections import abc, defaultdict

import urwid

from ..utils.string import strwidth
from .main import redraw_screen

from ..logging import make_logger  # isort:skip
log = make_logger(__name__)


class TabID(int):
    def __repr__(self):
        return '<TabID %d>' % self


def _find_unused_id(existing_ids):
    """Find lowest unused ID in `existing_ids`"""
    if not existing_ids:
        return TabID(0)
    else:
        for id_candidate in range(0, max(existing_ids) + 2):
            if id_candidate not in existing_ids:
                return TabID(id_candidate)


class TabBar(urwid.GridFlow):
    def __init__(self, spacing=1, default_width=20):
        return super().__init__([], default_width, spacing, 0, 'left')

    def __getitem__(self, pos):
        return self.contents[pos][0]

    def __setitem__(self, pos, widget):
        self.contents[pos] = self._make_title(widget)

    def __delitem__(self, pos):
        del self.contents[pos]

    def insert(self, pos, widget):
        self.contents.insert(pos, self._make_title(widget))

    def append(self, widget):
        self.contents.append(self._make_title(widget))

    def _make_title(self, widget):
        if hasattr(widget.base_widget, 'text'):
            opts = ('given', strwidth(widget.base_widget.text))
        else:
            opts = ()
        return (widget, self.options(*opts))

    @property
    def focus(self):
        return self.contents.focus

    @focus.setter
    def focus(self, pos):
        self.contents.focus = pos

    def __iter__(self):
        for w in self.contents:
            yield w[0]


class Tabs(urwid.Widget):
    """Organize multiple widgets in tabs"""

    _sizing = frozenset([urwid.FLOW, urwid.BOX])
    _max_focus_history_size = 100

    def __init__(self, *contents, tabbar=None):
        """
        Create new Tabs widget

        contents: Iterable of dictionaries or iterables that match the arguments
                  of the `insert` method
        tabbar: TabBar instance that is used to display tab titles or any object
                with a 'base_widget' attribute (e.g. AttrMap) that returns a
                TabBar object
        """
        if tabbar is None:
            self._tabbar = TabBar()
        elif not isinstance(tabbar, urwid.Widget):
            raise ValueError('tabbar must be TabBar instance, not {}: {!r}'
                             .format(type(tabbar).__name__, tabbar))
        else:
            self._tabbar = tabbar

        self._ids = []
        self._focus_history = []
        self._info = defaultdict(lambda: {})
        self._contents = urwid.MonitoredFocusList()
        self._contents.set_focus_changed_callback(self._focus_changed_callback)
        for content in contents:
            if not isinstance(content, abc.Mapping):
                content = dict(zip(('title', 'widget', 'position', 'focus'),
                                   content))
            self.insert(**content)

    def render(self, size, focus=False):
        if len(size) < 2:
            cols, rows = (size[0], None)
        else:
            cols, rows = size

        if len(self._contents) < 1:
            # No contents - return empty canvas
            return urwid.SolidCanvas(' ', cols, rows)

        if rows is not None:
            size_content = (cols, rows - self._tabbar.rows((cols,)))
        else:
            size_content = (cols,)

        combinelist = []
        position = self._contents.focus

        # Always render tab titles as focused to highlight the focused tab
        canvas = self._tabbar.render((cols,), focus=True)
        combinelist.append((canvas, position, True))

        # Render and add content of currently selected tab
        current_widget = self._contents[position]
        if current_widget is None:
            canvas = urwid.SolidCanvas(' ', *size_content)
        else:
            canvas = current_widget.render(size_content, focus)
        combinelist.append((canvas, position, focus))
        return urwid.CanvasCombine(combinelist)

    def get_index(self, position=None):
        """
        Return tab index at `position` or None if there are no tabs

        position: Index (int), ID (TabID) or None (focused tab)

        Raises IndexError if tab can't be found.
        """
        if position is None:
            return self.focus_position
        elif isinstance(position, TabID):
            if position in self._ids:
                return self._ids.index(position)
            else:
                raise IndexError('No tab with ID: {}'.format(position))
        else:
            i = self.focus_position if position is None else position
            if i is not None:
                tab_count = len(self._contents)
                if i < 0:
                    # Negative index means right-bound index (-1 is the rightmost tab)
                    if i >= -tab_count:
                        return self.get_index(tab_count + i)
                elif i < tab_count:
                    # Positive index means left-bound index (1 is the leftmost tab)
                    return i
                raise IndexError('No tab at position: {}'.format(position))

    def get_id(self, position=None):
        """
        Return unique TabID of tab at `position` or None if there are no tabs

        position: Index (int), ID (TabID) or None (focused tab)

        Raises IndexError if tab can't be found.
        """
        i = self.get_index(position)
        return self._ids[i] if i is not None else None

    def load(self, title, widget=None, position=None, focus=True):
        """
        Set content at `position`, in focused tab or in new tab

        If `position` is not None, it is forwarded to `set_title`/`set_content`
        together with `title`/`widget`.

        If no tabs exist, a new tab is created with `title` and `widget`.  If
        `widget` is None, a blank widget is used.

        Otherwise, the focused tab's title and content is replaced with
        `set_title` and `set_content`.

        Set `focus` to False to load content in background.

        Return TabID of newly created tab
        """
        if position is not None:
            # Overload content in specified tab
            self.set_content(widget, position=position)
            self.set_title(title, position=position)
            if focus:
                if isinstance(position, TabID):
                    self.focus_id = position
                else:
                    self.focus_position = position
            return self.get_id(position)
        elif self.focus_position is None:
            # No tabs exist - create new tab
            return self.insert(title, widget, focus=focus)
        else:
            # Overload content in focused tab
            self.set_content(widget)
            self.set_title(title)
            return self.get_id()

    @redraw_screen
    def insert(self, title, widget=None, position=-1, focus=True):
        """
        Insert new tab

        title: Any flow or fixed widget to use as the tab's title
        widget: Widget to show when this tab is selected or None
        position: Where to insert the new tab; int for list-like index or
                  'right'/'left' to insert next to focused tab
        focus: True to focus the new tab, False otherwise

        Return TabID of inserted tab
        """
        curpos = self.focus_position
        if position == 'right':
            newpos = (curpos + 1) if curpos is not None else 0
        elif position == 'left':
            newpos = max(curpos, 0) if curpos is not None else 0
        elif isinstance(position, int):
            if position < 0:
                newpos = position + len(self._contents) + 1
            else:
                newpos = position
        else:
            raise ValueError('Invalid position: {!r}'.format(position))

        # Insert new tab ID
        this_id = _find_unused_id(self._ids)
        self._ids.insert(newpos, this_id)

        # Insert title
        self._tabbar.base_widget.insert(newpos, title)

        # Insert content
        self._contents.insert(newpos, widget)
        if focus:
            self.focus_position = newpos
        return this_id

    @redraw_screen
    def move(self, position=None, destination='right', wrap=False):
        """
        Move tab at `position` to `where`

        position: Index (int), ID (TabID) or None (focused tab)
        destination: "left", "right" or new index (int)
        wrap: Whether to move the right-most tab to the first index when it is
              moved to the right and the left-most tab to the last index when it
              is moved to the left

        Raises IndexError if tab can't be found.
        """
        focused_tab_id = self.focus_id
        max_index = len(self._ids) - 1
        old_index = self.get_index(position)
        if destination == 'left':
            new_index = old_index - 1
            if new_index < 0:
                new_index = max_index if wrap else 0
        elif destination == 'right':
            new_index = old_index + 1
            if new_index > max_index:
                new_index = 0 if wrap else max_index
        elif isinstance(destination, int):
            new_index = destination
        else:
            raise ValueError('Invalid destination: %r' % (destination,))

        # Temporarily disable focus change callback
        self._contents.set_focus_changed_callback(lambda _: None)

        for lst in (self._ids, self._contents, self._tabbar.base_widget):
            item = lst[old_index]
            del lst[old_index]
            if new_index == -1:
                # list.insert() can only insert before
                lst.append(item)
            elif new_index < -1:
                # First negative index is -1
                lst.insert(new_index + 1, item)
            else:
                lst.insert(new_index, item)

        # Restore focus
        self.focus_id = focused_tab_id
        self._contents.set_focus_changed_callback(self._focus_changed_callback)

    @redraw_screen
    def remove(self, position=None):
        """
        Remove tab `position`

        position: Index (int), ID (TabID) or None (focused tab)

        Raises IndexError if tab can't be found.
        """
        index = self.get_index(position)
        tabid = self.get_id(position)
        if tabid is None:
            raise RuntimeError('Tabs is empty')
        del self._ids[index]
        del self._contents[index]
        if tabid in self._info:
            del self._info[tabid]
        del self._tabbar.base_widget[index]
        fh = self._focus_history
        while tabid in fh:
            fh.remove(tabid)

    def clear(self):
        """Remove all tabs"""
        while len(self._ids):
            self.remove(0)  # Remove tab at index 0

    def get_title(self, position=None):
        """
        Return tab title widget at `position`

        position: Index (int), ID (TabID) or None (focused tab)

        Raises IndexError if tab can't be found.
        """
        i = self.get_index(position)
        if i is not None:
            return self._tabbar.base_widget[i]

    def set_title(self, title, position=None):
        """
        Change the title widget of a tab

        title: New title widget; should be a Text object optionally wrapped by
               AttrMap
        position: Index (int), ID (TabID) or None (focused tab)

        Raises IndexError if tab can't be found.
        """
        i = self.get_index(position)
        if i is not None:
            self._tabbar.base_widget[i] = title
        else:
            raise RuntimeError('Tabs is empty')

    def get_content(self, position=None):
        """
        Return tab content widget at `position`

        position: Index (int), ID (TabID) or None (focused tab)

        Raises IndexError if tab can't be found.
        """
        i = self.get_index(position)
        if i is not None:
            return self._contents[i]

    def set_content(self, widget=None, position=None):
        """
        Set content of tab at `position` to `widget`

        position: Index (int), ID (TabID) or None (focused tab)

        Raises IndexError if tab can't be found.
        """
        i = self.get_index(position)
        if i is not None:
            self._contents[i] = widget
        else:
            raise RuntimeError('Tabs is empty')

    def get_info(self, position=None):
        """
        Return information about tab at `position`

        position: Index (int), ID (TabID) or None (focused tab)

        Raises IndexError if tab can't be found.
        """
        tabid = self.get_id(position)
        if tabid is not None:
            return self._info[tabid]

    def set_info(self, position=None, **kwargs):
        """
        Set information about tab at `position`

        position: Index (int), ID (TabID) or None (focused tab)

        Information is taken as arbitrary keyword arguments and is stored as an ordinary
        dictionary.

        Raises IndexError if tab can't be found.
        """
        tabid = self.get_id(position)
        if tabid is not None:
            self._info[tabid].update(kwargs)
        else:
            raise RuntimeError('Tabs is empty')

    def _focus_changed_callback(self, pos):
        tab_id = self.get_id(pos)
        self._focus_history.append(tab_id)
        while len(self._focus_history) > self._max_focus_history_size:
            self._focus_history.pop(0)

    @property
    def focus(self):
        """Content widget of currently focused tab or None if no tabs exist"""
        position = self._contents.focus
        if position is not None:
            return self._contents[position]
        return None

    @property
    def prev_focus(self):
        """Content widget of previously focused tab or None"""
        fh = self._focus_history
        if len(fh) >= 2:
            # fh[-1] is the currently focused tab ID
            prev_id = fh[-2]
            try:
                return self.get_content(prev_id)
            except IndexError:
                pass

    @property
    def focus_position(self):
        """Index (starting from 0) of currently focused tab or None if no tabs exist"""
        return self._contents.focus

    @focus_position.setter
    def focus_position(self, position):
        if 0 <= position < len(self._contents):
            self._tabbar.base_widget.focus = position
            self._contents.focus = position
        else:
            raise IndexError('No tab at position: {!r}'.format(position))

    @property
    def prev_focus_position(self):
        """Index of previously focused tab or None"""
        fh = self._focus_history
        if len(fh) >= 2:
            # fh[-1] is the currently focused tab ID
            prev_id = fh[-2]
            try:
                return self.get_index(prev_id)
            except IndexError:
                pass

    @property
    def focus_id(self):
        """TabID of currently focused tab or None if no tabs exist"""
        i = self.focus_position
        if i is not None:
            return self._ids[i]

    @focus_id.setter
    @redraw_screen
    def focus_id(self, tabid):
        i = self.get_index(tabid)
        if 0 <= i < len(self._contents):
            self._tabbar.base_widget.focus = i
            self._contents.focus = i
        else:
            raise IndexError('No tab with ID: {}'.format(tabid))

    @property
    def prev_focus_id(self):
        """TabID of previously focused tab or None"""
        fh = self._focus_history
        if len(fh) >= 2:
            return fh[-2]

    @property
    def ids(self):
        """Yields all tab IDs"""
        for w in self._ids:
            yield w

    @property
    def contents(self):
        """Yields all content widgets"""
        for w in self._contents:
            yield w

    @property
    def titles(self):
        """Yields all tab title widgets"""
        yield from self._tabbar.base_widget

    def __len__(self):
        return len(self._contents)

    def __iter__(self):
        return iter(self._contents)

    def selectable(self):
        return True

    def keypress(self, size, key):
        focus_widget = self.focus

        if focus_widget is not None:
            if len(size) > 1:
                cols, rows = size
                size = (cols, rows - self._tabbar.rows((cols,)))
            else:
                size = (size[0],)

            if focus_widget.selectable():
                key = focus_widget.keypress(size, key)

        if key is not None:
            focus_pos = self.focus_position
            cmd = self._command_map[key]
            if cmd == urwid.CURSOR_LEFT and focus_pos > 0:
                self.focus_position -= 1
                key = None
            elif cmd == urwid.CURSOR_RIGHT and focus_pos < len(self._contents) - 1:
                self.focus_position += 1
                key = None
        return key
