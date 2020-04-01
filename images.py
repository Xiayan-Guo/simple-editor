"""for accessing images."""

import atexit
import os
import tkinter

file_dir = os.path.dirname(os.path.abspath(__file__))
images_dir = os.path.join(file_dir, 'images')

# used to destroy the image objects on exit of the application
_image_cache = {}
atexit.register(_image_cache.clear)

def get(name):
    #load a ``tkinter.PhotoImage`` from an image file
    if name in _image_cache:
        return _image_cache[name]

    files = [filename for filename in os.listdir(images_dir)
             if filename.startswith(name + '.')]
    if not files:
        raise FileNotFoundError("no image file named %r" % name)
    assert len(files) == 1, "there are multiple %r files" % name

    image = tkinter.PhotoImage(file=os.path.join(images_dir, files[0]))
    # cache the image objects for acceleration and management
    _image_cache[name] = image
    return image
