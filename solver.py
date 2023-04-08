#!/usr/bin/env python3

from pathlib import Path
from typing import List
import logging as log

# Rich logging
LOGLEVEL = log.INFO
try:
    from rich.logging import RichHandler
    log.basicConfig(level=LOGLEVEL, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()])
except:
    log.basicConfig(level=LOGLEVEL)


# Constants
EMPTY = 0
OK = 0
SAME_VALUE = -1
NONE_REMOVED = -2


# Convenience functions
def string2tile(string : str) -> int:
    if string.startswith('_'):
        return 0
    return int(string)


class SudokuTile:
    def __init__(self, hpv : int):
        self.__value = EMPTY
        self.hpv = hpv
        self.reset_possible()

    def __str__(self):
        x = self.resolve()
        if x != EMPTY:
            return f"{x:2d}"
        return "__"
    
    def set(self, value : int):
        self.__possible = set([value])
        if value == self.__value:
            return False
        self.__value = value
        return True

    def reset_possible(self):
        if self.__value == EMPTY:
            self.__possible = set(range(1, self.hpv+1))
        else:
            self.__possible = set([self.__value])

    def get_possible(self):
        return self.__possible

    def get_possiblecount(self):
        return len(self.__possible)

    def remove_possible(self, value):
        if value == self.__value:
            return SAME_VALUE
        if value in self.__possible:
            self.__possible.remove(value)
            self.resolve()  # (redundant?)
            return OK
        #if self.get_possiblecount() == 1:
        #    raise RuntimeError("Trying to remove last possible")
        return NONE_REMOVED

    def resolve(self):
        if self.__value:
            return self.__value
        possible = list(self.__possible)
        if len(possible) == 1:
            self.set(possible[0])
        return self.__value


class SudokuSolver:

    '''Simple sudoku solver'''

    def __init__(self, **kwargs):

        if 'load' in kwargs:
            self.load_file(kwargs['load'])

    def __str__(self):
        ret = ""
        for y1 in range(self.N):
            if y1 != 0:
                for x in range(self.N*self.N*3+(self.N-1)*2+1):
                    ret += '-'
                ret += '\n'
            for y0 in range(self.N):
                for x1 in range(self.N):
                    for x0 in range(self.N):
                        y = y1*self.N + y0
                        x = x1*self.N + x0
                        tile = self.get_tile(y, x)
                        ret += str(tile) + ' '
                    ret += "| "
                ret += '\n'
        return ret
    
    def get_tile(self, row : int, col : int) -> SudokuTile:
        return self.__board[row][col]
    
    def all_tiles(self):
        #return [self.get_tile(r, c) for r, c in self.indices]
        for r, c in self.indices:
            yield self.get_tile(r, c)
    
    def remove_possible(self, row : int, col : int, val : int):
        stat = self.__board[row][col].remove_possible(val)
        if stat == SAME_VALUE:
            err = "Removed possibility of actual value"
            log.error(err)
            print(str(self))
            raise RuntimeError(err)
        #print(row, col, self.__board[row][col].get_possiblecount())
        return stat == OK
    
    def box_indices(self, row : int, col : int) -> List[int]:
        r0 = (row // self.N) * self.N
        c0 = (col // self.N) * self.N
        return [(r, c) for r in range(r0, r0+self.N) for c in range(c0, c0+self.N)]
    
    def reset_possible(self):
        for tile in self.all_tiles():
            tile.reset_possible()

    def commit(self, row, col, val):
        tile = self.get_tile(row, col)
        if tile.set(val):
            if self.verbose:
                log.debug(f"Set [{row:2d}, {col:2d}] {val}")
            tile.resolve()
        #todo("Remove adjacent possible")
        n = 0
        for x in range(self.N*self.N):
            if x != col:
                n += self.remove_possible(row, x, val)
            if x != row:
                n += self.remove_possible(x, col, val)
        for r, c in self.box_indices(row, col):
            if (r, c) != (row, col):
                n += self.remove_possible(r, c, val)
        return n

    def load(self, text : str):

        # Container for original puzzle
        self.puzzle = []
        
        # Determine size
        self.N = len(text.splitlines()[0].split('|'))
        log.debug(f"Determined size {self.N}")

        # Generate indices
        self.indices = []
        for r in range(self.N*self.N):
            for c in range(self.N*self.N):
                self.indices.append((r, c))

        # Traverse lines in text
        for line in text.splitlines():
            
            # Skip cosmetic lines
            if line.startswith('-'):
                continue

            # Construct puzzle
            row = []
            for subrow in line.split('|'):
                row += [string2tile(s) for s in subrow.split()]
            self.puzzle.append(row)

        # Construct board
        self.verbose = False
        self.__board = [[SudokuTile(self.N*self.N) for _ in row] for row in self.puzzle]
        for row, line in enumerate(self.puzzle):
            for col, val in enumerate(line):
                if val != EMPTY:
                    self.commit(row, col, val)
        self.verbose = True


    def refresh_possible(self) -> int:
        '''Remove impossibilities'''
        n = 0
        
        # Using solved values
        for r, c in self.indices:
            v = self.get_tile(r, c).resolve()
            if v != EMPTY:
                n += self.commit(r, c, v)

        # Remove candidates where boxes dictate value in specific row or col
        # TODO
        for br in range(self.N):
            for bc in range(self.N):
                bids = self.box_indices(br*self.N, bc*self.N)
                for val in range(1, self.N*self.N+1):
                    rows = set()
                    cols = set()
                    count = 0
                    for row, col in bids:
                        possible = list(self.get_tile(row, col).get_possible())
                        #if (len(possible) > 1) and (val in possible):
                        if val in possible:
                            rows.add(row)
                            cols.add(col)
                            count += 1
                    #if count == 0:
                    #    continue
                    rows, cols = list(rows), list(cols)
                    r, c = rows[0], cols[0]
                    if count == 1:
                        if self.get_tile(r, c).resolve() == EMPTY:
                            log.debug(f"[{r:2d}, {c:2d}] must be {val}")
                            n += self.commit(r, c, val)
                    elif len(rows) == 1:
                        #r = rows[0]
                        removed = 0
                        for c in range(self.N*self.N):
                            if (r, c) not in bids:
                                removed += self.remove_possible(r, c, val)
                            if removed:
                                n += removed
                                log.debug(f"[{br*self.N:2d}.., {bc*self.N}..] {val} must be on row {r} {str(cols)}")
                    elif len(cols) == 1:
                        #c = cols[0]
                        removed = 0
                        for r in range(self.N*self.N):
                            if (r, c) not in bids:
                                removed += self.remove_possible(r, c, val)
                            if removed:
                                n += removed
                                log.debug(f"[{br*self.N:2d}.., {bc*self.N}..] {val} must be on col {c} {str(rows)}")

        # Manually check if row/col candidate is lonesome
        for a in range(self.N*self.N):
            for b in range(1, self.N*self.N+1):
                rows = []
                cols = []
                for b in range(self.N*self.N):
                    if val in self.get_tile(a, b).get_possible():
                        cols.append(b)
                    if val in self.get_tile(b, a).get_possible():
                        rows.append(b)
                if len(cols) == 1:
                    row, col = a, cols[0]
                    if self.get_tile(row, col).resolve() == EMPTY:
                        log.info(f"{val} must be at [{row:2d}, {col:2d}] (lonesome at col)")
                        n += self.commit(row, col, val)
                if len(rows) == 1:
                    row, col = rows[0], a
                    if self.get_tile(row, col).resolve() == EMPTY:
                        log.info(f"{val} must be at [{row:2d}, {col:2d}] (lonesome at row)")
                        n += self.commit(row, col, val)

        # Manually check if box candidate is lonesome
        # TODO

        return n

    def solve_count(self) -> int:
        count = 0
        for r in range(self.N*self.N):
            for c in range(self.N*self.N):
                if self.get_tile(r, c).resolve():
                    count += 1
        return count

    def load_file(self, path : Path):
        self.load(open(path).read())

    def solve_step(self):
        log.debug("Step")
        removed = self.refresh_possible()
        log.debug(f"Removed {removed} possible")
        return removed, self.solve_count()

    def validate(self):
        for a in range(self.N*self.N):
            ab, ba = set(), set()
            for b in range(self.N*self.N):
                
                # Row-scan
                v = self.get_tile(a, b).resolve()
                if v != EMPTY and v in ab:
                    return False
                else:
                    ab.add(v)

                # Col-scan
                v = self.get_tile(b, a).resolve()
                if v != EMPTY and v in ba:
                    return False
                else:
                    ba.add(v)

        # TODO: Boxes
        return True

    def solve(self):

        prev, solved, removed = 0, self.solve_count(), 0
        while prev != solved or removed > 0:
            prev = solved
            removed, solved = self.solve_step()
            log.info(f"{removed} removals, {solved} solved")

        if self.validate():
            log.info("Solution valid")
        else:
            log.error("Solution invalid")


if __name__ == "__main__":
    
    solver = SudokuSolver(load=Path(__file__).parent/"puzzle_4x4.txt")

    solver.commit( 0,  0,  8)
    solver.commit( 0,  6,  4)
    solver.commit( 1,  3,  2)

    solver.solve()
    
    print(str(solver))

