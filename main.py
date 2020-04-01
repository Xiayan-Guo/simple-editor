import _run

def main():

    _run.init()

    import find, geometry, menubar
    find.setup()
    geometry.setup()
    menubar.setup()

    _run.run()
    
if __name__ == '__main__':
    main()
