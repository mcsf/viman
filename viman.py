#!/usr/bin/env python
## 2011-08-30

# TODO:
# - Deletion of associated files
# - Editing of entries

import cPickle
import curses
import fnmatch
import os
import os.path
import shlex
import subprocess
import sys


## SETTINGS ############################################################
BROWSEDIR = '~/www'
HANDLESTR = 'vlc "%s"'
DB_PATH = 'mydb.pickle'
EXTS = ['avi', 'flv', 'iso', 'mkv', 'mov', 'mp4', 'mpeg', 'mpg', 'wmv']
#SHOW_INFO = False
########################################################################


class Data:
    def __init__(self, data=None, keyfn=None, field=0):
        if type(data) is str:
            self.path = data
            self.checkout()
        else:
            self.path = None
            self.data = data
            self.size = len(data)
        if keyfn: self.keyfn = keyfn
        else:     self.keyfn = lambda d, i: d[i]
        self.reversed = False
        self.sort_by_field(field)

    def __getitem__(self, y):
        try:
            return self.data[y]
        except IndexError:
            return None

    def append(self, y):
        self.data.append(y)
        self.size += 1
        self.sort_by_field()
        self.commit()

    def get(self, i, j):
        try:
            return self.data[i][j]
        except IndexError:
            return None
    
    def set(self, i, j, value):
        entry = self.data[i]
        if entry:
            entry.extend([None for k in range(j+1 - len(entry))])
            entry[j] = value
            self.commit()

    def delete(self, i):
        self.data.pop(i)
        self.size -= 1
        self.commit()

    def replace(self, data):
        if type(data) is list:
            self.data = data
            self.size = len(data)
            self.sort_by_field()

    def sort_by_field(self, field=None):
        if field is not None: self.field = field
        if self.field >= 0 and self.field < self.size:
            self.data.sort(key=lambda i:i[self.field],
                    reverse=self.reversed)

    def reverse(self):
        self.reversed = not self.reversed
        self.sort_by_field()

    def checkout(self):
        if not os.path.isfile(self.path):
            self.data = []
            self.size = 0
        else:
            with open(self.path, 'rb') as f:
                self.data = cPickle.load(f)
                self.size = len(self.data)

    def commit(self):
        with open(self.path, 'wb') as f:
            cPickle.dump(self.data, f)


class ScrollList:
    def __init__(self, h, w, y, x, data):
        self.data   = data
        self.height = h
        self.width  = w
        self.pad    = curses.newwin(h, w, y, x)
        self.scroll = 0
        self.select = 0

    def resize(self, h, w):
        self.height = h
        self.width  = w
        self.pad.resize(h, w)
        self.down()
        self.up()

    def show(self, i):
        return self.data.keyfn(self.data, i) if self.data[i] else '~'

    # Needs optimizing
    def draw(self):
        self.pad.clear()
        for i in range(self.height):
            if self.scroll + i == self.select: self.pad.standout()
            self.pad.addnstr(i, 0, "%s" % (self.show(self.scroll+i)),
                        self.width-1)
            if self.scroll + i == self.select: self.pad.standend()
        self.pad.refresh()

    def selection(self):
        return self.data[self.select]

    def react(self, key):
        try: c = chr(key)
        except ValueError: pass
        else:
            opt = {
                'g': self.top,
                'j': self.down,
                'k': self.up,
                'G': self.bottom,
                '\x02': self.pu, # ^B
                '\x05': self.sd, # ^E
                '\x06': self.pd, # ^F
                '\x19': self.su, # ^Y
            }
            if c in opt:
                opt[c]()
                return True
        return False

    def top(self):
        self.select = 0
        self.scroll = 0

    def bottom(self):
        self.select = self.data.size - 1
        while self.scroll + self.height <= self.data.size - 1:
            self.scroll += self.height

    def down(self):
        if self.select < self.data.size - 1:
            self.select += 1
            if self.select >= self.scroll + self.height:
                self.scroll += self.height

    def up(self):
        if self.select > 0:
            self.select -= 1
            if self.select < self.scroll:
                self.scroll -= self.height

    def pd(self):
        if self.select + self.height <= self.data.size - 1:
            self.select += self.height
            self.scroll += self.height
        else:
            if self.scroll + self.height <= self.data.size - 1:
                self.scroll += self.height
            self.select = self.data.size - 1

    def pu(self):
        if self.select >= self.height:
            self.select -= self.height
            self.scroll -= self.height
        else:
            self.select = 0
            self.scroll = 0

    def sd(self):
        if self.scroll < self.data.size - 1:
            self.scroll += 1
            if self.select < self.scroll:
                self.select = self.scroll

    def su(self):
        if self.scroll > 0:
            self.scroll -= 1
            if self.select >= self.scroll + self.height:
                self.select = self.scroll + self.height - 1
        

class FileBrowser(ScrollList):
    def __init__(self, h, w, y, x):
        ScrollList.__init__(self, h, w, y, x, Data([]))
        self.current = ''
        self.history = []
        self.fetch()

    def fetch(self, new=None):
        if new is not None: self.current = new
        self.data.replace(self.file_filter(os.listdir(
                os.path.expanduser(os.path.join(BROWSEDIR,
                self.current)))))

    def file_filter(self, files):
        def pred(f):
            if os.path.isdir(os.path.expanduser(os.path.join(
                BROWSEDIR, self.current, f))): return True
            for e in EXTS:
                if fnmatch.fnmatch(f.lower(), '*.' + e): return True
            return False
        return filter(pred, files)

    def react(self, key):
        if not ScrollList.react(self, key):
            try: c = chr(key)
            except ValueError: pass
            else:
                opt = {
                    'l': self.right,
                    'h': self.left
                }
                if c in opt:
                    opt[c]()
                    return True
            return False

    def hist_push(self):
        self.history.insert(0, (self.select, self.scroll))

    def hist_pop(self):
        if self.history: self.select, self.scroll = self.history.pop(0)

    def right(self):
        new = os.path.join(self.current, self.selection())
        if os.path.isdir(os.path.expanduser(
                os.path.join(BROWSEDIR, new))):
            self.hist_push()
            self.fetch(new)
            self.top()

    def left(self):
        self.hist_pop()
        self.fetch(os.path.dirname(self.current))


class Header():
    def __init__(self, h, w, y, x, modes):
        self.pad   = curses.newwin(h, w, y, x)
        self.width = w
        self.modes = modes
        self.mode  = modes.get('default', modes.keys()[0])
        self.attrs = curses.A_BOLD

    def resize(self, h, w):
        self.width  = w
        self.pad.resize(h, w)
        self.draw()

    def draw(self):
        self.pad.clear()
        self.pad.addnstr(0, 0, self.modes[self.mode], self.width-1,
                self.attrs)
        self.pad.refresh()

    def setmode(self, m):
        if m in self.modes.keys():
            self.mode = m
            self.draw()


class Footer():
    def __init__(self, h, w, y, x, fields):
        self.height = h
        self.width  = w
        self.pad    = curses.newwin(h, w, y, x)
        self.fields = fields
        self.empty  = [ '-' for f in fields ]
        self.pad.attrset(curses.A_BOLD)

    def resize(self, h, w):
        self.height = h
        self.width  = w
        self.pad.resize(h, w)

    def draw(self, values=None):
        if not values: values = self.empty
        self.pad.clear()
        self.pad.hline(0, 0, '-', self.width)
        for i in range(len(self.fields)):
            self.pad.addnstr(i+1, 0, '%s: %s' % (self.fields[i],
                values[i]), self.width-1)
        self.pad.refresh()


class Mode:
    def __init__(self, header, mode):
        self.header = header
        self.old = header.mode
        self.new = mode
    def __enter__(self):
        self.header.setmode(self.new)
    def __exit__(self, et, ev, tb):
        self.header.setmode(self.old)


def show(w, s, n=0, l=0):
    w.clear()
    try:
        if n:
            lines = s.splitlines()
            if l: lines = lines[:l]
            for i in range(len(lines)):
                w.addnstr(2+i, 2, lines[i], n)
        else: w.addstr(2, 2, s)
    except curses.error: pass
    w.border(0)
    w.refresh()
    return w.getch()

def get_param(w, prompt_string):
    w.clear()
    w.border(0)
    w.addstr(2, 2, prompt_string)
    w.refresh()
    curses.echo()
    input = w.getstr(10, 10, 60)
    curses.noecho()
    return input


def main():

    ## CUSTOMISATION ###################################################
    def my_data_insert(w, data, *items):
        data.append([
                get_param(w, "Year?"),
                get_param(w, "Title?")]
                + list(items))

    def my_show_fn(d, i):
        isread = len(d[i]) > 3 and d[i][3]
        marker = ' ' if isread else '!'
        return '%s (%s) %s' % (marker, d[i][0], d[i][1])
    ####################################################################


    ## HELPERS #########################################################
    def mode(m):
        return Mode(head, m)

    def sshow(w, s):
        'Resize-resistant version of `show()\''
        c = curses.KEY_RESIZE
        while c == curses.KEY_RESIZE:
            resize()
            _, n = stdscr.getmaxyx()
            c = show(w, s, n-1)

    def resize():
        h, w = stdscr.getmaxyx()
        body.resize(h - 5, w)
        head.resize(1, w)
        foot.resize(4, w)
        foot.pad.mvwin(h - 4, 0)
        browser.resize(h - 1, w)

    def draw():
        head.draw()
        body.draw()
        foot.draw(body.selection())

    def browser_select():
        my_data_insert(browser.pad, body.data,
                os.path.join(
                    os.path.expanduser(BROWSEDIR),
                    browser.current,
                    browser.selection()),
                False)
    ####################################################################


    ## MODES ###########################################################
    modes = {
        'default'   : 'main',
        'main'      : 'space:Play a:AddNew d:Delete z:Sort '
                    + '!:Mark ?:Help q:Quit',
        'browser'   : 'hjkl:Navigate space:Select q:Quit',
        'prompt'    : 'Enter to submit',
        'sort'      : 'Sort by? - y:Year t:Title !:Mark r:Reverse '
                    + 'q:Quit',
        'delete'    : 'Really delete? - d:DeleteEntry '
                    + 'D:DeleteWithFiles q:Abort',
        'help'      : 'Press any key to return'
    }
    ####################################################################


    ## ACTIONS #########################################################
    def file_browser():
        with mode('browser'):
            c = 0
            while c != ord('q'):
                browser.draw()
                c = browser.pad.getch()
                if not browser.react(c):
                    if c == ord(' '):
                        browser_select()
                        break

    def entry_select():
        body.data.set(body.select, 3, True)
        subprocess.Popen(shlex.split(
            HANDLESTR % body.selection()[2]),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def entry_delete():
        with mode('delete'):
            ans = chr(body.pad.getch())
            if ans == 'd':
                body.data.delete(body.select)
            elif ans == 'D': pass

    def list_sort():
        keep_sorting = False
        opt = { 'y': 0, 't': 1, '!': 3 }
        with mode('sort'):
            ans = 0
            while ans != 'q':
                ans = chr(body.pad.getch())
                if ans == 'r':
                    body.data.reverse()
                elif ans in opt.keys():
                    body.data.sort_by_field(opt[ans])
                if not keep_sorting: break
                body.draw()

    def help_show():
        with mode('help'):
            sshow(browser.pad, helpstr)

    def mark_toggle():
        i = body.select
        body.data.set(i, 3, not body.data.get(i, 3))

    ####################################################################


    ## HELP ############################################################
    helpstr = '''\
Navigating:
      k       Select Up
      j       Select Down
      ^B      Page Up
      ^F      Page Down
      ^Y      Scroll Up
      ^E      Scroll Down
      g       Jump to Top
      G       Jump to Bottom
 
  General:
      l       Go inside
      h       Go back
      space   Select
      q       Quit, Return
 '''
    ####################################################################


    ## INIT ############################################################
    stdscr = curses.initscr()
    curses.noecho()
    h, w = stdscr.getmaxyx()
    head = Header(1, w, 0, 0, modes)
    body = ScrollList(h - 5, w, 1, 0, Data(DB_PATH, my_show_fn))
    foot = Footer(4, w, h - 4, 0, [ 'Year ', 'Title', 'Path ' ])
    browser = FileBrowser(h - 1, w, 1, 0)
    ####################################################################


    ## MAIN LOOP #######################################################
    key = 0
    while key != ord('q'):
        draw()
        key = body.pad.getch()

        if not body.react(key):
            try: c = chr(key)
            except ValueError: pass
            else:
                opt = {
                    ' ': entry_select,
                    '!': mark_toggle,
                    '?': help_show,
                    'a': file_browser,
                    'd': entry_delete,
                    'l': entry_select,
                    'z': list_sort,
                }
                if c in opt: opt[c]()

    ####################################################################


    ## CLEANUP #########################################################
    curses.endwin()
    ####################################################################

if __name__ == '__main__':
    lockfile = os.path.expanduser('~/.viman.lockfile')
    delete = True
    if os.path.isfile(lockfile):
        print 'Lockfile found! Is another instance already running?'
        print 'Shall I abort (A), delete (D) the lockfile or just',
        print 'ignore (I) it?'

        while True:
            ans = raw_input('(A/D/I)? ').lower()
            if   ans == 'a': sys.exit(1)
            elif ans == 'd': break
            elif ans == 'i':
                delete = False
                break

    with open(lockfile, 'a'): main()
    if delete: os.remove(lockfile)
