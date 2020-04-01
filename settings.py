import atexit
import codecs
import collections.abc
import functools
import json
import logging
import os
import sys
import tkinter
import tkinter.font as tkfont
from tkinter import messagebox, ttk
import types

import _run
import dirs, images, utils

# this is a custom exception because plain ValueError is often raised
# when something goes wrong unexpectedly
class InvalidValue(Exception):
    '''
    '''

# globals ftw
_sections = {}
_loaded_json = {}
_dialog = None          # the settings window
_notebook = None        # main widget in the dialog


def get_section(section_name):
    # Return a section object, creating it if it doesn't exist yet.
    _init()
    try:
        return _sections[section_name]
    except KeyError:
        _sections[section_name] = _ConfigSection(section_name)
        return _sections[section_name]


# generate standard sections
# the sections are tabs of the setting dialog
class _ConfigSection(collections.abc.MutableMapping):

    def __init__(self, name):
        if _notebook is None:
            raise RuntimeError("%s.init() wasn't called" % __name__)

        self.content_frame = ttk.Frame(_notebook)
        _notebook.add(self.content_frame, text=name)

        self._name = name
        self._infos = {}        # see add_option()
        self._var_cache = {}

    def add_option(self, key, default, *, reset=True):
        # Add a new option without adding widgets to the setting dialog.

        self._infos[key] = types.SimpleNamespace(
            default=default,        # not validated
            reset=reset,
            callbacks=[],
            errorvar=tkinter.BooleanVar(),  # true when the triangle is showing
        )

    def __setitem__(self, key, value):
        info = self._infos[key]

        old_value = self[key]
        try:
            _loaded_json[self._name][key] = value
        except KeyError:
            _loaded_json[self._name] = {key: value}

        if value != old_value:
            for func in info.callbacks:
                try:
                    func(value)
                except InvalidValue as e:
                    _loaded_json[self._name][key] = old_value
                    raise e
                except Exception:
                    try:
                        func_name = func.__module__ + '.' + func.__qualname__
                    except AttributeError:
                        func_name = repr(func)

    def __getitem__(self, key):
        try:
            return _loaded_json[self._name][key]
        except KeyError:
            return self._infos[key].default

    def __delitem__(self, key):    # the abc requires this
        raise TypeError("cannot delete options")

    def __iter__(self):
        return iter(self._infos.keys())

    def __len__(self):
        return len(self._infos)

    def reset(self, key):
        # Set section[key] back to the default value.
        self[key] = self._infos[key].default

    def connect(self, key, callback, run_now=True):
        # Schedule ``callback(section[key])`` to be called when the value of an option changes.
        if run_now:
            try:
                callback(self[key])
            except InvalidValue:
                try:
                    func_name = (callback.__module__ + '.' +
                                 callback.__qualname__)
                except AttributeError:
                    func_name = repr(callback)
                self.reset(key)
        self._infos[key].callbacks.append(callback)

    def disconnect(self, key, callback):
        self._infos[key].callbacks.remove(callback)

    # returns an image the same size as the triangle image, but empty
    @staticmethod
    def _get_fake_triangle(cache=[]):
        if not cache:
            cache.append(tkinter.PhotoImage(
                width=images.get('triangle').width(),
                height=images.get('triangle').height()))
            atexit.register(cache.clear)
        return cache[0]

    def get_var(self, key, var_type=tkinter.StringVar):
        # Return a tkinter variable that is bound to an option.
        if key in self._var_cache:
            if not isinstance(self._var_cache[key], var_type):
                raise TypeError("get_var(%r, var_type) was called multiple "
                                "times with different var types" % key)
            return self._var_cache[key]

        info = self._infos[key]
        var = var_type()

        def var2config(*junk):
            try:
                value = var.get()
            except (tkinter.TclError, ValueError):
                info.errorvar.set(True)
                return

            try:
                self[key] = value
            except InvalidValue:
                info.errorvar.set(True)
                return

            info.errorvar.set(False)

        self.connect(key, var.set)      # runs var.set
        var.trace('w', var2config)

        self._var_cache[key] = var
        return var

    def add_frame(self, triangle_key):
        # Add a ttk.Frame to the dialog and return it.
        frame = ttk.Frame(self.content_frame)
        frame.pack(fill='x')

        if triangle_key is not None:
            errorvar = self._infos[triangle_key].errorvar
            triangle_label = ttk.Label(frame)
            triangle_label.pack(side='right')

            def on_errorvar_changed(*junk):
                if errorvar.get():
                    triangle_label['image'] = images.get('triangle')
                else:
                    triangle_label['image'] = self._get_fake_triangle()

            errorvar.trace('w', on_errorvar_changed)
            on_errorvar_changed()

        return frame

    def add_checkbutton(self, key, text):
        # Add a ttk.Checkbutton that sets an option to a bool.
        var = self.get_var(key, tkinter.BooleanVar)
        ttk.Checkbutton(self.add_frame(key), text=text,
                        variable=var).pack(side='left')

    def add_entry(self, key, text):
        # Add a ttk.Entry that sets an option to a string.
        frame = self.add_frame(key)
        ttk.Label(frame, text=text).pack(side='left')
        ttk.Entry(frame, textvariable=self.get_var(key)).pack(side='right')

    def add_combobox(self, key, choices, text, *, case_sensitive=True):
        # Add a ttk.Combobox that sets an option to a string.
        def validator(value):
            if case_sensitive:
                ok = (value in choices)
            else:
                ok = (value.casefold() in map(str.casefold, choices))
            if not ok:
                raise InvalidValue("%r is not a valid %r value"
                                   % (value, key))

        self.connect(key, validator)

        frame = self.add_frame(key)
        ttk.Label(frame, text=text).pack(side='left')
        ttk.Combobox(frame, values=choices,
                     textvariable=self.get_var(key)).pack(side='right')

    def add_spinbox(self, key, minimum, maximum, text):
        # Add a utils.Spinbox that sets an option to an integer.

        def validator(value):
            if value < minimum:
                raise InvalidValue("%r is too small" % value)
            if value > maximum:
                raise InvalidValue("%r is too big" % value)

        self.connect(key, validator)

        frame = self.add_frame(key)
        ttk.Label(frame, text=text).pack(side='left')
        utils.Spinbox(frame, textvariable=self.get_var(key, tkinter.IntVar),
                      from_=minimum, to=maximum).pack(side='right')


def _needs_reset():
    for section in _sections.values():
        for key, info in section._info.items():
            if info.default != section[key]:
                return True
    return False


def _do_reset():
    if not _needs_reset:
        messagebox.showinfo("Reset Settings",
                            "You are already using the default settings.")
        return

    if not messagebox.askyesno(
            "Reset Settings", "Are you sure you want to reset all settings?",
            parent=_dialog):
        return

    for section in _sections.values():
        for key, info in section._infos.items():
            if info.reset:
                section[key] = info.default
    messagebox.showinfo(
        "Reset Settings", "All settings were reset to defaults.",
        parent=_dialog)


def _validate_encoding(name):
    try:
        codecs.lookup(name)
    except LookupError as e:
        raise InvalidValue from e

def _init():
    global _dialog
    global _notebook

    if _dialog is not None:
        # already initialized
        return

    _dialog = tkinter.Toplevel()
    _dialog.withdraw()        # hide it for now
    _dialog.title("Settings")
    _dialog.protocol('WM_DELETE_WINDOW', _dialog.withdraw)
    _dialog.geometry('500x350')

    big_frame = ttk.Frame(_dialog)
    big_frame.pack(fill='both', expand=True)
    _notebook = ttk.Notebook(big_frame)
    _notebook.pack(fill='both', expand=True)
    ttk.Separator(big_frame).pack(fill='x')
    buttonframe = ttk.Frame(big_frame)
    buttonframe.pack(fill='x')
    for text, command in [("Reset", _do_reset), ("OK", _dialog.withdraw)]:
        ttk.Button(buttonframe, text=text, command=command).pack(side='right')

    assert not _loaded_json
    try:
        with open(os.path.join(dirs.configdir, 'settings.json'), 'r') as file:
            _loaded_json.update(json.load(file))
    except FileNotFoundError:
        pass      # use defaults everywhere

    general = get_section('General')   # type: _ConfigSection

    fixedfont = tkfont.Font(name='TkFixedFont', exists=True)
    font_families = sorted(family for family in tkfont.families()
                     # i get weird fonts starting with @ on windows
                     if not family.startswith('@'))

    general.add_option('font_family', fixedfont.actual('family'))
    general.add_combobox('font_family', font_families, "Font Family:",
                         case_sensitive=False)

    # negative font sizes have a special meaning in tk and the size is negative
    # by default, that's why the stupid hard-coded default size 10
    general.add_option('font_size', 10)
    general.add_spinbox('font_size', 3, 1000, "Font Size:")

    # when font_family changes:  fixedfont['family'] = new_family
    # when font_size changes:    fixedfont['size'] = new_size
    general.connect(
        'font_family', functools.partial(fixedfont.__setitem__, 'family'))
    general.connect(
        'font_size', functools.partial(fixedfont.__setitem__, 'size'))

    general.add_option('encoding', 'UTF-8')
    general.add_entry('encoding', "Encoding of opened and saved files:")
    general.connect('encoding', _validate_encoding)

def show_dialog():
    # Show the settings dialog.
    _init()

    # hide sections with no widgets in the content_frame
    # add and hide preserve order and title texts
    for name, section in _sections.items():
        if section.content_frame.winfo_children():
            _notebook.add(section.content_frame)
        else:
            _notebook.hide(section.content_frame)

    _dialog.transient(_run.get_main_window())
    _dialog.deiconify()


def save():
    # Save the settings to the config file.
    if _loaded_json:
        # there's something to save
        # if two apps are running and the user changes settings
        # differently in them, the settings of the one that's closed
        # first are discarded
        with open(os.path.join(dirs.configdir, 'settings.json'), 'w') as file:
            json.dump(_loaded_json, file)
