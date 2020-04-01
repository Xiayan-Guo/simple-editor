import collections
import tkinter
import warnings

import tabs
import utils
import _run

# associate paths(for example: File/New, File/Open) with actions,
# which are instances of the class _Action.
_actions = collections.OrderedDict()


class _Action:

    def __init__(self, path, kind, callback_or_choices, binding, var):
        self.path = path
        self.kind = kind
        self.binding = binding
        self._enabled = True

        # this is less crap than subclassing would be
        if kind == 'command':
            self.callback = callback_or_choices
        elif kind == 'choice':
            self.var = var
            self.choices = callback_or_choices
            self.var.trace('w', self._var_set_check)
        elif kind == 'yesno':
            self.var = var
        else:
            raise AssertionError("this shouldn't happen")

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, is_enabled):
        # omitting this check might cause confusing behavior
        if not isinstance(is_enabled, bool):
            raise TypeError("enabled should be True or False, not %r"
                            % (is_enabled,))

        if self._enabled != is_enabled:
            self._enabled = is_enabled
            # if is_enabled is True, event is '<<ActionEnabled>>', otherwise it's '<<ActionDisabled>>'
            event = '<<ActionEnabled>>' if is_enabled else '<<ActionDisabled>>'
            # the 'data' words in event_generate are extral information to deal with
            _run.get_main_window().event_generate(event, data=self.path)

    def _var_set_check(self, *junk):
        value = self.var.get()
        if value not in self.choices:
            warnings.warn("the var of %r was set to %r which is not one "
                          "of the choices" % (self, value), RuntimeWarning)


def _add_any_action(path, kind, callback_or_choices, binding, var, *,
                    filetype_names=None, tabtypes=None):
    if path.startswith('/') or path.endswith('/'):
        raise ValueError("action paths must not start or end with /")
    if filetype_names is not None and tabtypes is not None:
        # python raises TypeError when it comes to invalid arguments
        raise TypeError("only one of filetype_names and tabtypes can be used")
    if path in _actions:
        raise RuntimeError("there's already an action with path %r" % path)

    # event_generate must be before setting action.enabled, this way
    # plugins get a chance to do something to the new action before it's
    # disabled
    action = _Action(path, kind, callback_or_choices, binding, var)
    _actions[path] = action
    _run.get_main_window().event_generate('<<NewAction>>', data=path)

    if tabtypes is not None or filetype_names is not None:
        if tabtypes is not None:
            tabtypes = tuple(
                # None is the only type(None) object
                type(None) if cls is None else cls
                for cls in tabtypes
            )
            # find whether the type of 'current tab' is among given types(tabtypes)
            def enable_or_disable(junk_event=None):
                tab = _run.get_tab_manager().select()
                action.enabled = isinstance(tab, tabtypes)

        if filetype_names is not None:
            # the noqa comment is needed because flake8 thinks this is
            # a "redefinition of unused 'enable_or_disable'"
            def enable_or_disable(junk_event=None):     # noqa
                tab = _run.get_tab_manager().select()
                if isinstance(tab, tabs.FileTab):
                    action.enabled = tab.filetype.name in filetype_names
                else:
                    action.enabled = False

            def on_new_tab(event):
                tab = event.data_widget
                if isinstance(tab, tabs.FileTab):
                    tab.bind('<<FiletypeChanged>>', enable_or_disable,
                             add=True)

            utils.bind_with_data(_run.get_tab_manager(),
                                 '<<NewTab>>', on_new_tab, add=True)

        enable_or_disable()
        _run.get_tab_manager().bind(
            '<<NotebookTabChanged>>', enable_or_disable, add=True)

    if binding is not None:
        assert kind in {'command', 'yesno'}, repr(kind)

        def bind_callback(event):
            if action.enabled:
                if kind == 'command':
                    action.callback()
                if kind == 'yesno':
                    action.var.set(not action.var.get())
                # try to allow binding keys that are used for other
                # things by default
                return 'break'

        widget = _run.get_main_window()    # any widget would do
        widget.bind_all(binding, bind_callback, add=True)

        widget.tk.call('bind', 'Text', binding, '')

    return action


def add_command(path, callback, keyboard_binding=None, **kwargs):
    # Add a simple action that runs callback()
    return _add_any_action(path, 'command', callback,
                           keyboard_binding, None, **kwargs)


def get_action(action_path):
    # Look up and return an existing action object by its path.
    return _actions[action_path.rstrip('/')]


def get_all_actions():
    # Return a list of all existing action objects in arbitrary order.
    return list(_actions.values())
