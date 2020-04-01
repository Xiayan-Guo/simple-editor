"""Handy utility functions."""

import collections
import contextlib
import functools
import logging
import os
import platform
import shlex
import shutil
import string as string_module      # string is used as a variable name
import subprocess
import sys
import threading
import tkinter
from tkinter import ttk
import traceback

import _run

log = logging.getLogger(__name__)

def bind_with_data(widget, sequence, callback, add=False):
    """
    Like ``widget.bind(sequence, callback)``, but supports the ``data``
    argument of ``event_generate()``.

    Here's an example::

        import utils

        def on_wutwut(event):
            print(event.data)

        utils.bind_with_data(some_widget, '<<Thingy>>', on_wutwut, add=True)

        # this prints 'wut wut'
        some_widget.event_generate('<<Thingy>>', data='wut wut')

    Note that everything is a string in Tcl, so tkinter ``str()``'s the data.

    The event objects have all the attributes that tkinter events
    usually have, and these additional attributes:

        ``data``
            See the above example.

        ``data_int`` and ``data_float``
            These are set to ``int(event.data)`` and ``float(event.data)``,
            or None if ``data`` is not a valid integer or float.

        ``data_widget``
            If a widget was passed as ``data`` to ``event_generate()``,
            this is that widget. Otherwise this is None.
        ``data_tuple(converter1, converter2, ...)``
            If a string from :func:`.create_tcl_list` is passed to
            ``event_generate()``, this splits the list back to the strings
            passed to :func:`.create_tcl_list` and optionally converts them to
            other types like ``converter(string_value)``. For example,
            ``event.data_tuple(int, int, str, float)`` returns a 4-tuple with
            types ``(int, int, str, float)``, throwing an error if some of the
            elements can't be converted or the iterable passed to
            :func:`.create_tcl_list` didn't contain exactly 4 elements.
    """
    # tkinter creates event objects normally and appends them to the
    # deque, then run_callback() adds data_blablabla attributes to the
    # event objects and runs callback(event)
    event_objects = collections.deque()
    widget.bind(sequence, event_objects.append, add=add)

    def run_the_callback(data_string):
        event = event_objects.popleft()
        event.data = data_string

        # TODO: test this
        try:
            split_result = event.widget.tk.splitlist(data_string)
        except tkinter.TclError:
            event.data_tuple = None
        else:
            def data_tuple(*converters):
                if len(split_result) != len(converters):
                    raise ValueError(
                        "the event data has %d elements, but %d converters "
                        "were given" % (len(split_result), len(converters)))
                return tuple(
                    converter(string)
                    for converter, string in zip(converters, split_result))

            event.data_tuple = data_tuple

        try:
            event.data_int = int(data_string)
        except ValueError:
            event.data_int = None

        try:
            event.data_float = float(data_string)
        except ValueError:
            event.data_float = None

        try:
            event.data_widget = widget.nametowidget(data_string)
        # nametowidget raises KeyError when the widget is unknown, but
        # that feels like an implementation detail
        except Exception:
            event.data_widget = None

        return callback(event)      # may return 'break'

    # tkinter's bind() ignores the add argument when the callback is a
    # string :(
    funcname = widget.register(run_the_callback)
    widget.tk.eval('bind %s %s {+ if {"[%s %%d]" == "break"} break }'
                   % (widget, sequence, funcname))
    return funcname

try:
    Spinbox = ttk.Spinbox
except AttributeError:
    try:
        Spinbox = ttk.SpinBox
    except AttributeError:
        # this is based on the code of ttk.Combobox, if tkinter changes so
        # that this breaks then ttk.Spinbox will be probably added as well
        class Spinbox(ttk.Entry):

            def __init__(self, master=None, *, from_=None, **kwargs):
                if from_ is not None:
                    kwargs['from'] = from_  # this actually works
                super().__init__(master, 'ttk::spinbox', **kwargs)

            def configure(self, *args, **kwargs):
                if 'from_' in kwargs:
                    kwargs['from'] = kwargs.pop('from_')
                return super().configure(*args, **kwargs)

            config = configure


def errordialog(title, message, monospace_text=None):
    """This is a lot like ``tkinter.messagebox.showerror``.

    This function can be called with or without creating a root window
    first. If *monospace_text* is not None, it will be displayed below
    the message in a ``tkinter.Text`` widget.

    Example::

        try:
            do something
        except SomeError:
            utils.errordialog("Oh no", "Doing something failed!",
                              traceback.format_exc())
    """
    root = _run.get_main_window()
    if root is None:
        window = tkinter.Tk()
    else:
        window = tkinter.Toplevel()
        window.transient(root)

    # there's nothing but this frame in the window because ttk widgets
    # may use a different background color than the window
    big_frame = ttk.Frame(window)
    big_frame.pack(fill='both', expand=True)

    label = ttk.Label(big_frame, text=message)

    if monospace_text is None:
        label.pack(fill='both', expand=True)
        geometry = '250x150'
    else:
        label.pack(anchor='center')
        # there's no ttk.Text 0_o this looks very different from
        # everything else and it sucks :(
        text = tkinter.Text(big_frame, width=1, height=1)
        text.pack(fill='both', expand=True)
        text.insert('1.0', monospace_text)
        text['state'] = 'disabled'
        geometry = '400x300'

    button = ttk.Button(big_frame, text="OK", command=window.destroy)
    button.pack(pady=10)

    window.title(title)
    window.geometry(geometry)
    window.wait_window()

@contextlib.contextmanager
def backup_open(path, *args, **kwargs):
    """Like :func:`open`, but uses a backup file if needed.

    This is useless with modes like ``'r'`` because they don't modify
    the file, but this is useful when overwriting the user's files.

    This needs to be used as a context manager. For example::

        try:
            with utils.backup_open(cool_file, 'w') as file:
                ...
        except (UnicodeError, OSError):
            # log the error and report it to the user

    This automatically restores from the backup on failure.
    """
    if os.path.exists(path):
        # there's something to back up
        name, ext = os.path.splitext(path)
        while os.path.exists(name + ext):
            name += '-backup'
        backuppath = name + ext

        log.info("backing up '%s' to '%s'", path, backuppath)
        shutil.copy(path, backuppath)

        try:
            yield open(path, *args, **kwargs)
        except Exception as e:
            log.info("restoring '%s' from the backup", path)
            shutil.move(backuppath, path)
            raise e
        else:
            log.info("deleting '%s'" % backuppath)
            os.remove(backuppath)

    else:
        yield open(path, *args, **kwargs)


def get_keyboard_shortcut(binding):
    """Convert a Tk binding string to a format that most people are used to.

    >>> get_keyboard_shortcut('<Control-c>')
    'Ctrl+C'
    >>> get_keyboard_shortcut('<Control-C>')
    'Ctrl+Shift+C'
    >>> get_keyboard_shortcut('<Control-0>')
    'Ctrl+Zero'
    >>> get_keyboard_shortcut('<Control-1>')
    'Ctrl+1'
    >>> get_keyboard_shortcut('<F11>')
    'F11'
    """
    # TODO: handle more corner cases? see bind(3tk)
    parts = binding.lstrip('<').rstrip('>').split('-')
    result = []

    for part in parts:
        if part == 'Control':
            # TODO: i think this is supposed to use the command symbol
            # on OSX? i don't have a mac
            result.append('Ctrl')
        # tk doesnt like e.g. <Control-ö> :( that's why ascii only here
        elif len(part) == 1 and part in string_module.ascii_lowercase:
            result.append(part.upper())
        elif len(part) == 1 and part in string_module.ascii_uppercase:
            result.append('Shift')
            result.append(part)
        elif part == '0':
            # 0 and O look too much like each other
            result.append('Zero')
        else:
            # good enough guess :D
            result.append(part.capitalize())

    return '+'.join(result)
