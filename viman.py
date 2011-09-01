#!/usr/bin/env python
## 2011-08-30

# TODO:
# - Deletion of associated files
# - Editing of entries
# - Mark entries as read/unread

import curses
import fnmatch
import os
import os.path
import cPickle


## SETTINGS ############################################################
BROWSEDIR = '~/www'
HANDLESTR = 'vlc "%s" >/dev/null 2>&1 &'
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
        self.sort_by_field(field)

    def __getitem__(self, y):
        if y >= 0 and y < self.size:
            return self.data[y]
        else:
            return None

    def append(self, y):
        self.data.append(y)
        self.size += 1
        self.sort_by_field()
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
            self.data.sort(key=lambda i:i[self.field])

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
        opt = {
            'j': self.down,
            'k': self.up,
            'n': self.pd,
            'p': self.pu,
            'e': self.sd,
            'y': self.su
        }
        try:
            c = chr(key)
            if c in opt:
                opt[c]()
                return True
        except ValueError: pass
        return False

    def top(self):
        self.select = 0
        self.scroll = 0

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
            opt = {
                'l': self.right,
                'h': self.left
            }
            try:
                c = chr(key)
                if c in opt:
                    opt[c]()
                    return True
            except ValueError: pass
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
    def my_data_insert(w, data, item):
        data.append([
                get_param(w, "Year?"),
                get_param(w, "Title?"),
                item])

    my_show_fn = lambda d, i: '(%s) %s' % (d[i][0], d[i][1])
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
                    browser.selection()))
    ####################################################################


    ## MODES ###########################################################
    modes = {
        'default'   : 'main',
        'main'      : 'space:Play a:AddNew d:Delete z:Sort '
                    + '?:Help q:Quit',
        'browser'   : 'hjkl:Navigate space:Select ?:Help q:Quit',
        'prompt'    : 'Enter to submit',
        'sort'      : 'Sort by? - y:Year t:Title',
        'delete'    : 'Really delete? - d:DeleteEntry '
                    + 'D:DeleteWithFiles q:Abort',
        'help'      : 'Press any key to return'
    }
    ####################################################################


    ## HELP ############################################################
    helpstr = '''\
Navigating:
      k       Select Up
      j       Select Down
      e       Scroll Up
      y       Scroll Down
      p       Page Up
      n       Page Down
 
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
    c = 0
    while c != ord('q'):
        draw()
        c = body.pad.getch()

        if not body.react(c):

            # Resizing
            if c == curses.KEY_RESIZE: resize()

            # File browser
            elif c == ord('a'):
                with mode('browser'):
                    while c != ord('q'):
                        browser.draw()
                        c = browser.pad.getch()
                        if not browser.react(c):
                            if c == ord(' '):
                                browser_select()
                                break
                    c = 0

            # Entry selection
            elif c in [ord(' '), ord('l')]:
                os.system(HANDLESTR % body.selection()[2])

            # Entry deletion
            elif c == ord('d'):
                with mode('delete'):
                    ans = chr(body.pad.getch())
                    if ans == 'd':
                        body.data.delete(body.select)
                    elif ans == 'D': pass

            # List sorting
            elif c == ord('z'):
                opt = { 'y': 0, 't': 1 }
                with mode('sort'):
                    ans = chr(body.pad.getch())
                    if ans in opt.keys():
                        body.data.sort_by_field(opt[ans])

            # Help
            elif c == ord('?'):
                with mode('help'):
                    sshow(browser.pad, helpstr)

    ####################################################################


    ## CLEANUP #########################################################
    curses.endwin()
    ####################################################################

if __name__ == '__main__':
    lockfile = os.path.expanduser('~/.viman.lockfile')
    if os.path.isfile(lockfile):
        print 'Lockfile found! Is another instance already running?'
        print '\nIf you know what you\'re doing, you can manually',
        print 'remove file \'%s\'.' % lockfile
    else:
        with open(lockfile, 'w'): main()
        os.remove(lockfile)
