import os
import sys
import tkinter
import traceback
import functools
import webbrowser
import tkinter
from tkinter import filedialog, ttk
import operator
from operator import itemgetter

import matplotlib, numpy
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import tabs, utils, actions, dirs, settings

m_root = None
m_tab_manager = None

m_dialog = None
m_notebook = None


def init():
    global m_root
    global m_tab_manager
    if m_root is not None or m_tab_manager is not None:
        raise RuntimeError("cannot init() twice")

    #dirs.makedirs()
    m_root = tkinter.Tk()
    m_root.protocol('WM_DELETE_WINDOW', quit)
    m_root.title('simple text editor')

    m_tab_manager = tabs.TabManager(m_root)
    m_tab_manager.pack(fill='both', expand=True)
    for binding, callback in m_tab_manager.bindings:
        m_root.bind(binding, callback, add=True)

    _setup_actions()

def get_main_window():
    if m_root is None:
        raise RuntimeError("Application is not running")
    return m_root

def get_tab_manager():
    if m_tab_manager is None:
        raise RuntimeError("Application is not running")
    return m_tab_manager

def quit():
    for tab in m_tab_manager.tabs():
        if not tab.can_be_closed():
            return

    m_root.event_generate('<<SimpleEditorQuit>>')
    for tab in m_tab_manager.tabs():
        m_tab_manager.close_tab(tab)
    m_root.destroy()

def _setup_actions():
    def new_file():
        m_tab_manager.add_tab(tabs.FileTab(m_tab_manager))

    def open_files():
        paths = filedialog.askopenfilenames(
            filetypes=[("Text files", "*.txt")])

        if not paths:
            return
        for path in paths:
            try:
                tab = tabs.FileTab.open_file(m_tab_manager, path)
            except(UnicodeError, OSError) as e:
                utils.errordialog(type(e).__name__, "Opening failed!",
                        traceback.format_exc())
                continue

            m_tab_manager.add_tab(tab)

    def close_selected_tab():
        tab = m_tab_manager.select()
        if tab.can_be_closed():
            m_tab_manager.close_tab(tab)


    def tokenize_file(show=True):
        tab = m_tab_manager.select()
        start = 1
        content = tab.textwidget.get('%d.0' % start, 'end - 1 char')
        # tokenize the content and display it on a new tab
        words = []
        new_content= ''
        lines = content.split('\n')
        for line in lines:
            i = 0
            while i < len(line):
                while (i < len(line)) and (not line[i].isalpha()):
                    i += 1
                word = ''
                while (i < len(line)) and line[i].isalpha():
                    word += line[i]
                    i += 1
                if word != '':
                    words.append(word.lower())
        for word in words:
            new_content += (word + "\n")
        if show:
            # tokens should be kept as a property of FileTab
            new_tab = m_tab_manager.add_tab(tabs.FileTab(m_tab_manager))
            new_tab.textwidget.insert('1.0', new_content)
            #tab.tokens (property setter)
            new_tab.tokens = words
        #tab.tokens (property setter)
        tab.tokens = words

    # word frequency, word count, keywords(top 6)
    def get_statistics():
        #read in stopwords
        m_stop_words = []
        path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(path, 'stop_words.txt')
        config = settings.get_section('General')
        with open(path, 'r', encoding=config['encoding']) as file:
            content = file.read()
        m_stop_words = content.split('\n')

        tab = m_tab_manager.select()
        #tab.tokens (property getter)
        words = tab.tokens
        if len(words) == 0:
            tokenize_file(show=False)
            #tab.tokens (property getter)
            words = tab.tokens
        # compute word frequency via dictionary
        dict = {}
        for word in words:
            if word not in dict:
                dict[word] = 1
            else:
                dict[word] += 1

        sorted_dict = sorted(dict.items(),key=operator.itemgetter(1),reverse=True)
        new_dict = {}
        ranking_text = 'Total words: ' + str(len(words)) + "\nWord frequencies: \n"
        for key, val in sorted_dict:
            ranking_text += (key + "\t\t" + str(val) + "\n")
            if key not in m_stop_words:
                new_dict[key] = val

        # setup statistics dialog
        m_dialog = tkinter.Toplevel()
        m_dialog.withdraw()
        m_dialog.title("Statistics")
        m_dialog.protocol('WM_DELETE_WINDOW', m_dialog.withdraw)
        m_dialog.geometry('600x400')

        m_notebook = ttk.Notebook(m_dialog)
        m_notebook.pack(fill='both', expand=True)

        # add tabs to the frame
        # ranking tab in tk.Text
        ranking_frame = tkinter.Text(m_notebook)
        m_notebook.add(ranking_frame, text="Ranking")
        ranking_frame.insert('1.0', ranking_text)
        # tab show bar graph
        draw_frame = ttk.Frame(m_notebook)
        m_notebook.add(draw_frame, text="Graph")

        if len(m_stop_words) == 0:
            raise RuntimeError("stop word list is empty")

        fig = Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)
        label = []
        data = []
        i = 0
        for key, val in new_dict.items():
            if (i >= 6) or (i >= len(new_dict)):
                break
            if key in m_stop_words:
                continue
            data.append(val)
            label.append(key.lower())
            i += 1
        
        ind = numpy.arange(len(data))
        graph = ax.bar(ind, data, width=0.5)
        ax.set_ylabel('Frequency')
        ax.set_xlabel('Words')
        ax.set_xticks(ind)
        ax.set_xticklabels(label)
        # ax.set_xticklabels(label, rotation=45, ha="right")
        ax.set_title('Top used words')

        canvas = FigureCanvasTkAgg(fig, master=draw_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(side='top', fill='both', expand=True)

        m_dialog.transient(m_root)
        m_dialog.deiconify()



    actions.add_command("File/New File", new_file, '<Control-n>')
    actions.add_command("File/Open", open_files, '<Control-o>')
    actions.add_command("File/Save", (lambda: m_tab_manager.select().save()),
                        '<Control-s>', tabtypes=[tabs.FileTab])
    actions.add_command("File/Save As...",
                        (lambda: m_tab_manager.select().save_as()),
                        '<Control-S>', tabtypes=[tabs.FileTab])

    actions.add_command("File/Close", close_selected_tab, '<Control-w>',
                        tabtypes=[tabs.Tab])
    actions.add_command("File/Quit", quit, '<Control-q>')

    actions.add_command("Edit/Settings", settings.show_dialog)
    actions.add_command("Edit/Tokenize", tokenize_file)
    actions.add_command("Edit/Statistics", get_statistics)

    def add_link(path, url):
        actions.add_command(path, functools.partial(webbrowser.open, url))

    add_link("Help/163 mail",
             "http://mail.163.com/")

def run():
    if m_root is None:
        raise RuntimeError("init() wasn't called")
    m_root.mainloop()

