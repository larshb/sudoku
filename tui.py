#!/usr/bin/env python3

from termios import *
import sys
from time import sleep
import logging as log
from typing import List
from pathlib import Path
import json
import os


# Set up logging
LOGLEVEL = log.DEBUG
FILENAME = "/tmp/tui.log"
log.basicConfig(filename=FILENAME, level=LOGLEVEL)
log.debug("Using standard logger")


# Constants
ESC = chr(27)
CSI = ESC + '['
SCRATCHPAD = Path(__file__).parent/"scratch.json"


def ascii_friendly(c):
    if 32 <= ord(c) <= 128:
        return c
    else:
        return '.'


def say(string):
    sys.stdout.write(string)


def sgr(formats):
    if type(formats) is int:
        formats = [formats]
    say(CSI + ';'.join(str(f) for f in list(formats)) + 'm')


class Cursor:

    def __init__(self):
        self.__fmts = [0]

    def formats_apply(self):
        sgr(self.__fmts)

    def formats_reset(self):
        self.__fmts = [0]
        self.formats_apply()

    def formats_set(self, formats : List[int]):
        self.__fmts = formats
        self.formats_apply()

    def formats_get(self):
        return self.__fmts

    def position(self, n, m):
        say(f"{CSI}{n};{m}H")

    def visible(self, enable : bool):
        say(f"{CSI}?25{'h' if enable else 'l'}")

    def hide(self):
        self.visible(False)

    def show(self):
        self.visible(True)


class Block:

    def __init__(self, char, formats=[0]):
        self.char_set(char)
        self.formats_set(formats)
    
    def char_get(self):
        return self.__char
    
    def char_set(self, char):
        self.__char = char
        self.drawn = False

    def formats_set(self, formats):
        self.__fmts = formats
        self.drawn = False

    def formats_get(self):
        return self.__fmts


class Canvas:
    
    def __init__(self, cursor : Cursor, text=""):
        self.cursor = cursor
        self.load(text)

    def load(self, text):
        self.blocks = []
        row = []
        for char in text:
            if char == '\n':
                self.blocks.append(row)
                row = []
            elif char == '\b':
                pass
            else:
                row.append(Block(char))
        if row != []:
            self.blocks.append(row)

    def draw(self, flush=False):
        for y, row in enumerate(self.blocks):
            for x, block in enumerate(row):
                if flush or (not block.drawn):

                    # Position cursor
                    self.cursor.position(y+1, x+1)

                    # Check format againts current cursor
                    if self.cursor.formats_get() != block.formats_get():
                        self.cursor.formats_set(block.formats_get())
                    
                    # Output character
                    say(block.char_get())

                    # Don't redraw until necessary
                    block.drawn = True


class TTY:

    def __init__(self, fd=sys.stdin):
        self.fd = fd
        self.mode = tcgetattr(self.fd)

    def __del__(self):
        self.cook()

    def raw(self, when=TCSAFLUSH):
        IFLAG, OFLAG, CFLAG, LFLAG, ISPEED, OSPEED, CC = range(7)
        mode = self.mode
        mode[IFLAG] &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON)
        mode[OFLAG] &= ~(OPOST)
        mode[CFLAG] &= ~(CSIZE | PARENB)
        mode[CFLAG] |= CS8
        mode[LFLAG] &= ~(ECHO | ICANON | IEXTEN | ISIG)
        mode[CC][VMIN] = 1
        mode[CC][VTIME] = 0
        tcsetattr(self.fd, when, mode)
        #os.system("stty raw")
    
    def cook(self, when=TCSAFLUSH):
        tcsetattr(self.fd, when, self.mode)
        #os.system("stty cooked")

    def write(self, s):
        say(s)
    
    def read(self, n=1):
        s = sys.stdin.read(n)
        log.debug(f"Read {ord(s):3d} {ascii_friendly(s)}")
        return s

    def clear(self, type=2):
        say(f"{CSI}{type}J")

    def alternative_buffer(self, enable):
        say(f"{CSI}?1049{'h' if enable else 'l'}")

class TUI:

    def __init__(self):
        self.tty = TTY()
        self.tty.raw()
        self.cursor = Cursor()
        self.canvas = Canvas(self.cursor)
        self.keepAlive = True
        self.write = self.tty.write
        self.read = self.tty.read

    def __del__(self):
        self.tty.alternative_buffer(False)
        self.cursor.show()
    
    def parse_keyboard(self):
        c = self.read()
        if c == 'q':
            self.keepAlive = False
        elif c == chr(3): # Interrupt?
            self.keepAlive = False
        elif c == chr(27): # ESC
            c = self.read()
            if c == '[': # CSI
                c = self.read()
                if c in "ABCD": # Cursor movement
                    row, col = self.selected
                    row, col = {
                        'A': ((row-1)%(self.N*self.N), (col+0)%(self.N*self.N)), # Up
                        'B': ((row+1)%(self.N*self.N), (col+0)%(self.N*self.N)), # Down
                        'C': ((row+0)%(self.N*self.N), (col+1)%(self.N*self.N)), # Right
                        'D': ((row+0)%(self.N*self.N), (col-1)%(self.N*self.N)), # Left
                    }.get(c)
                    self.sudoku_select(row, col)
                else:
                    log.error(f"Unhandled CSI")
            else:
                log.error(f"Unhandled ESC")
        elif c in "0123456789":
            row, col = self.selected
            val = self.board[row][col]
            val *= 10
            val += int(c)
            if val <= self.N*self.N:
                self.board[row][col] = val
            elif int(c) <= (self.N*self.N):
                self.board[row][col] = int(c)
            self.sudoku_draw(row, col, selected=True)
        elif c == chr(126): # delete
            row, col = self.selected
            self.board[row][col] = 0
            self.sudoku_draw(row, col, selected=True)
        elif c == chr(127): # backspace
            row, col = self.selected
            self.board[row][col] //= 10
            self.sudoku_draw(row, col, selected=True)
        elif c == 'v': # validate
            self.tty.clear()
            self.cursor.position(1, 1)
            say("Please wait...")
            logpath = "/tmp/sudoku_validate.log"
            call = "python3 "
            call += str((Path(__file__).parent/"solver.py").absolute())
            call += f" > {logpath}"
            os.system(call)
            self.tty.clear()
            #sgr(7)
            sgr(0)
            padding = '\r\n'
            self.cursor.position(1, 1)
            for line in open(logpath).read().splitlines():
                say(padding + line)
            say("Press any key to continue...")
            sgr(0)
            self.read()
            self.tty.clear()
            self.canvas.draw(flush=True)
        else:
            log.error(f"Unhandled keypress")
            pass

    def sudoku_select(self, r, c):
        r0, c0 = self.selected
        self.sudoku_draw(r0, c0, selected=False)
        self.sudoku_draw(r, c, selected=True)
        self.selected = r, c

    def sudoku_draw(self, r, c, selected=False):
        v = self.board[r][c]
        if v == 0:
            s = f"   "
        else:
            s = f"{v:2d} "
        for off in range(3):
            block = self.canvas.blocks[r*2+1][c*4+1+off]
            block.char_set(s[0+off])
            if selected:
                block.formats_set([7])
            else:
                block.formats_set([0])

    def sudoku_scratchload(self):
        scr = json.load(open(SCRATCHPAD))
        self.N = scr['N']
        self.board = scr['board']

    def sudoku_scratchsave(self):
        json.dump({
            'N': self.N,
            'board': self.board
        }, open(SCRATCHPAD, 'w'))

    def sudoku_setup(self):
        try:
            self.sudoku_scratchload()
        except Exception as exc:
            log.exception(exc)
            self.N = 4
            self.board = [[0]*(self.N*self.N) for _ in range(self.N*self.N)]
        self.selected = 0, 0
        for r in range(self.N*self.N):
            for c in range(self.N*self.N):
                self.sudoku_draw(r, c)
        r, c = self.selected
        self.sudoku_draw(r, c, selected=True)

    def mainloop(self):
        self.tty.alternative_buffer(True)
        self.tty.clear()
        self.cursor.hide()
        self.canvas.load('\n'.join(line.lstrip() for line in '''
            ┏━━━┯━━━┯━━━┯━━━┳━━━┯━━━┯━━━┯━━━┳━━━┯━━━┯━━━┯━━━┳━━━┯━━━┯━━━┯━━━┓
            ┃ 1 │ 2 │ 3 │ 4 ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃ 5 │ 6 │ 7 │ 8 ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃ 9 │10 │11 │12 ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃13 │14 │15 │16 ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┣━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━┫
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┣━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━┫
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┣━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━╋━━━┿━━━┿━━━┿━━━┫
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┠───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───╂───┼───┼───┼───┨
            ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃   │   │   │   ┃
            ┗━━━┷━━━┷━━━┷━━━┻━━━┷━━━┷━━━┷━━━┻━━━┷━━━┷━━━┷━━━┻━━━┷━━━┷━━━┷━━━┛
        '''.strip().splitlines()))
        
        #for r in range(1):
        #    for c in range(3):
        #        self.canvas.blocks[r+3][c+5].formats_set([7])
        
        self.sudoku_setup()
        
        while self.keepAlive:
            self.canvas.draw()
            self.sudoku_scratchsave()
            #sys.stdout.buffer.flush()
            print('')
            self.parse_keyboard()
        self.tty.cook()


if __name__ == "__main__":

    tui = TUI()
    try:
        tui.mainloop()
    # except KeyboardInterrupt:
    #     print("CTRL+C")
    except KeyboardInterrupt:
        pass
    except Exception as err:
        log.exception(err)
        tui.tty.cook()
        raise
    finally:
        tui.tty.cook()
        os.system("stty cooked")
