import functools
import hashlib
import itertools
import os
import tkinter
from tkinter import ttk, messagebox, filedialog
import traceback
import importlib

import images, utils, settings

class TabManager(ttk.Notebook):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        partial = functools.partial     # pep-8 line length
        self.bindings = [
            ('<Control-Prior>', partial(self._on_page_updown, False, -1)),
            ('<Control-Next>', partial(self._on_page_updown, False, +1)),
            ('<Control-Shift-Prior>', partial(self._on_page_updown, True, -1)),
            ('<Control-Shift-Next>', partial(self._on_page_updown, True, +1)),
        ]
        for number in range(1, 10):
            callback = functools.partial(self._on_alt_n, number)
            self.bindings.append(('<Alt-Key-%d>' % number, callback))

        self.bind('<<NotebookTabChanged>>', self._focus_selected_tab, add=True)
        self.bind('<Button-1>', self._on_click, add=True)

    def _focus_selected_tab(self, event):
        tab = self.select()
        if tab is not None:
            tab.on_focus()

    def _on_click(self, event):
        if self.identify(event.x, event.y) != 'label':
            # something else than the top label was clicked
            return

        # find the right edge of the label
        right = event.x
        while self.identify(right, event.y) == 'label':
            right += 1
        if event.x + images.get('closebutton').width() >= right:
            # the close button was clicked
            tab = self.tabs()[self.index('@%d,%d' % (event.x, event.y))]
            if tab.can_be_closed():
                self.close_tab(tab)

    def _on_page_updown(self, shifted, diff, event):
        if shifted:
            self.move_selected_tab(diff)
        else:
            self.select_another_tab(diff)
        return 'break'

    def _on_alt_n(self, n, event):
        try:
            self.select(n - 1)
            return 'break'
        except tkinter.TclError:        # index out of bounds
            return None

    def select(self, tab_id=None):
        # select the given tab as if the user clicked it.  tab_id should be a Tab widget.
        if tab_id is None:
            selected = super().select()
            if not selected:
                return None
            return self.nametowidget(str(selected))

        # the tab can be e.g. an index, that's why two super() calls
        super().select(tab_id)
        return None

    def tabs(self):
        # return a tuple of tabs in the tab manager.
        return tuple(self.nametowidget(str(tab)) for tab in super().tabs())

    def add_tab(self, tab, select=True):
        # append a Tab to this tab manager.
        assert tab not in self.tabs(), "cannot add the same tab twice"
        for existing_tab in self.tabs():
            if tab.equivalent(existing_tab):
                if select:
                    self.select(existing_tab)
                return existing_tab

        self.add(tab, text=tab.title, image=images.get('closebutton'),
                 compound='right')
        if select:
            self.select(tab)

        # the update() is needed in some cases because virtual events
        # don't run if the widget isn't visible yet
        self.update()
        self.event_generate('<<NewTab>>', data=tab)
        return tab

    def close_tab(self, tab):
        # destroy a tab without calling can_be_closed
        self.forget(tab)
        tab.destroy()

    def select_another_tab(self, diff):
        # try to select another tab next to the currently selected tab. 
        # diff should be 1 for selecting a tab at right or -1 for left
        assert diff in {1, -1}, repr(diff)
        if not self.tabs():
            return False

        index = self.index(self.select())
        try:
            self.select(index + diff)
            return True
        except tkinter.TclError: 
            return False

    def move_selected_tab(self, diff):
        # try to move the currently selected tab left or right.
        # diff should be 1 for moving to right or -1 for left.
        # This returns True if the tab was moved and False if there was no
        # room for moving it or there are no tabs.

        assert diff in {1, -1}, repr(diff)
        if not self.tabs():
            return False

        i1 = self.index(self.select())
        i2 = i1 + diff
        if i1 > i2:
            i1, i2 = i2, i1

        if i1 < 0 or i2 >= self.index('end'):
            return False

        tab = self.tabs()[i2]
        options = self.tab(i2)
        selected = (tab is self.select())

        self.forget(i2)
        self.insert(i1, tab, **options)
        if selected:
            self.select(tab)

        return True


class Tab(ttk.Frame):

    def __init__(self, manager):
        super().__init__(manager)
        self._status = ''
        self._title = ''

        # top and bottom frames must be packed first because this way
        # they extend past other frames in the corners
        self.top_frame = ttk.Frame(self)
        self.bottom_frame = ttk.Frame(self)
        self.left_frame = ttk.Frame(self)
        self.right_frame = ttk.Frame(self)
        self.top_frame.pack(side='top', fill='x')
        self.bottom_frame.pack(side='bottom', fill='x')
        self.left_frame.pack(side='left', fill='y')
        self.right_frame.pack(side='right', fill='y')

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, new_status):
        self._status = new_status
        self.event_generate('<<StatusChanged>>')

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, text):
        self._title = text
        if self in self.master.tabs():
            self.master.tab(self, text=text)

    def can_be_closed(self):
        # This is usually called before the tab is closed. The tab
        # shouldn't be closed if this returns False.
        return True

    def on_focus(self):
        """This is called when the tab is selected.
        """

    def equivalent(self, other):
        """This is explained in TabManager.add_tab
        """
        return False

class _FileType:
    def __init__(self, name, pattern):
        self.name = name
        self.filename_patterns = pattern

def get_filedialog_kwargs():
    # This is a way to run tkinter dialogs that display the filetypes and extensions. 
    result = [("All files", "*"), ("Plain Text", "*.txt")]
    return {'filetypes': result}

class FileTab(Tab):

    def __init__(self, manager, content='', path=None):
        super().__init__(manager)

        self._save_hash = None

        self._path = path
        self._filetype = _FileType('Plain Text', '*.txt')
        self.bind('<<PathChanged>>', self._update_title, add=True)

        self._tokens = []
        # we need to set width and height to 1 to make sure it's never too
        # large for seeing other widgets
        self.textwidget = tkinter.Text(
            self, width=1, height=1, wrap='none', undo=True)
        self.textwidget.pack(side='left', fill='both', expand=True)
        self.textwidget.bind('<<ContentChanged>>', self._update_title,
                             add=True)

        if content:
            self.textwidget.insert('1.0', content)
            self.textwidget.edit_reset()   # reset undo/redo

        self.bind('<<PathChanged>>', self._update_status, add=True)
        self.bind('<<FiletypeChanged>>', self._update_status, add=True)
        self.textwidget.bind('<<CursorMoved>>', self._update_status, add=True)

        self.scrollbar = ttk.Scrollbar(self)
        self.scrollbar.pack(side='left', fill='y')
        self.textwidget['yscrollcommand'] = self.scrollbar.set
        self.scrollbar['command'] = self.textwidget.yview

        self.mark_saved()
        self._update_title()
        self._update_status()

    @classmethod
    def open_file(cls, manager, path):
        # Read a file and return a new FileTab object.
        config = settings.get_section('General')
        with open(path, 'r', encoding=config['encoding']) as file:
            content = file.read()
        return cls(manager, content, path)

    def equivalent(self, other):
        #Return True if *self* and *other* are saved to the same place.
        return (isinstance(other, FileTab) and
                self.path is not None and
                other.path is not None and
                os.path.samefile(self.path, other.path))

    def iter_chunks(self, n=100):
        # Iterate over the content as chunks of n lines.
        start = 1     # this is not a mistake, line numbers start at 1
        while True:
            end = start + n
            if self.textwidget.index('%d.0' % end) == self.textwidget.index('end'):
                # '%d.0' % start can be 'end - 1 char' in a corner
                # case, let's not yield an empty string
                last_chunk = self.textwidget.get('%d.0' % start, 'end - 1 char')
                if last_chunk:
                    yield last_chunk
                break

            yield self.textwidget.get('%d.0' % start, '%d.0' % end)
            start = end

    def _get_hash(self):
        config = settings.get_section('General')
        encoding = config['encoding']

        result = hashlib.md5()
        for chunk in self.iter_chunks():
            chunk = chunk.encode(encoding, errors='replace')
            result.update(chunk)

        # hash objects don't define an __eq__ so we need to use a string
        # representation of the hash
        return result.hexdigest()

    def mark_saved(self):
        self._save_hash = self._get_hash()
        self._update_title()

    def is_saved(self):
        #Return False if the text has changed since previous save.
        return self._get_hash() == self._save_hash

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, new_path):
        if self.path is None and new_path is None:
            it_changes = False
        elif self.path is None or new_path is None:
            it_changes = True
        else:
            # windows paths are case-insensitive
            it_changes = (os.path.normcase(self._path) !=
                          os.path.normcase(new_path))

        self._path = new_path
        if it_changes:
            self.event_generate('<<PathChanged>>')

    @property
    def tokens(self):
        return self._tokens

    @tokens.setter
    def tokens(self, new_tokens):
        if len(new_tokens) > 0:
            self._tokens = new_tokens

    @property
    def filetype(self):
        return self._filetype

    def _update_title(self, junk=None):
        text = 'New File' if self.path is None else os.path.basename(self.path)
        if not self.is_saved():
            text = '*' + text + '*'
        self.title = text

    def _update_status(self, junk=None):
        if self.path is None:
            prefix = "New file"
        else:
            prefix = "File '%s'" % self.path
        line, column = self.textwidget.index('insert').split('.')

        self.status = "%s, %s\tLine %s, column %s" % (
            prefix, self.filetype.name,
            line, column)

    def can_be_closed(self):
        # If the file has been saved, this returns True. Otherwise, return False.
        if self.is_saved():
            return True

        if self.path is None:
            msg = "Do you want to save your changes?"
        else:
            msg = ("Do you want to save your changes to %s?"
                   % os.path.basename(self.path))
        answer = messagebox.askyesnocancel("Close file", msg)
        if answer is None:
            # cancel
            return False
        if answer:
            # yes
            return self.save()
        # no was clicked, can be closed
        return True

    def on_focus(self):
        self.textwidget.focus()

    def save(self):
        # Save the file to the current path
        if self.path is None:
            return self.save_as()

        self.event_generate('<<Save>>')

        encoding = settings.get_section('General')['encoding']
        try:
            with utils.backup_open(self.path, 'w', encoding=encoding) as f:
                for chunk in self.iter_chunks():
                    f.write(chunk)
        except (OSError, UnicodeError) as e:
            utils.errordialog(type(e).__name__, "Saving failed!",
                              traceback.format_exc())
            return None

        self.mark_saved()
        return True

    def save_as(self):
        # Ask the user where to save the file and save it there.
        path = filedialog.asksaveasfilename(
            **get_filedialog_kwargs())
        if not path:
            return False

        self.path = path
        self.save()
        return True
