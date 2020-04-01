from _run import get_main_window
import settings


config = settings.get_section('General')
config.add_option('default_geometry', '650x600', reset=False)


def save_geometry(event):
    config['default_geometry'] = event.widget.geometry()


def setup():
    get_main_window().geometry(config['default_geometry'])
    get_main_window().bind('<<SimpleEditorQuit>>', save_geometry, add=True)
