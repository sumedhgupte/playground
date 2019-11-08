from dataclasses import dataclass
from neoteric.enums import SensorType, Board, Direction
import torch
from abc import abstractmethod
import itertools
from neoteric.utils import move_in_direction
from typing import List

BOARD_SIZE = 11

@dataclass
class Bomb:
    pos : any
    radius: any
    ticks : any
        
class Sensor:
    
    def __init__(self, sensortype = SensorType.ABSTRACT):
        self.sensortype = sensortype
        self.device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        self.flatten = lambda matrix: itertools.chain.from_iterable(matrix)   
        self.unfogged_board = torch.ones(BOARD_SIZE, BOARD_SIZE, dtype=torch.long) * Board.FOG.value
                 
            
    def _slide(self, board, curr_pos, direction, radius_val, marked_val, flares):
        if curr_pos[0] < 0. or curr_pos[1] < 0. or curr_pos[0] >= BOARD_SIZE or curr_pos[1] >= BOARD_SIZE :    # OUT OF BOUNDS
            return
        if board[curr_pos] == Board.RIGID.value or radius_val <= 0.:    # RIGID WALL or OUT OF BOMB RADIUS
            return
        if not flares[curr_pos]:                    # NOT ALREADY MARKED BY EARLIER BOMB
            flares[curr_pos] = marked_val
        if board[curr_pos] == Board.WOOD.value:
            return
        self._slide(board, move_in_direction(curr_pos, direction), direction, radius_val - 1., marked_val, flares)
    
    def _alight(self, board, radius, ticks):
        bombs_list = [Bomb((row, col), radius[row][col], ticks[row][col]) for col in range(board.shape[1]) 
                      for row in range(board.shape[0]) ]
        bombs_list.sort(key = lambda b:b.ticks)
        flares = torch.zeros(board.shape)
        for bomb in bombs_list:
            if not flares[bomb.pos]:
                flares[bomb.pos] = bomb.ticks
            self._slide(board, bomb.pos, Direction.UP, bomb.radius, bomb.ticks, flares)
            self._slide(board, bomb.pos, Direction.LEFT, bomb.radius, bomb.ticks, flares)
            self._slide(board, bomb.pos, Direction.DOWN, bomb.radius, bomb.ticks, flares)
            self._slide(board, bomb.pos, Direction.RIGHT, bomb.radius, bomb.ticks, flares)
        return flares
    
    def simpleSense(self, obs):
        board = torch.tensor(obs['board'], dtype = torch.long)
        radius = torch.tensor(obs['bomb_blast_strength'], dtype = torch.float)
        ticks = torch.tensor(obs['bomb_life'], dtype = torch.float)
        self.flares = self._alight(board, radius, ticks) 
        # Update only the non-fog cells, rest keep as it is(ols positions of enemies still remain, so duplicates are seen)
        # Nothing major of a concern, since the duplicates will always be outside of sight/range
        self.unfogged_board[board != Board.FOG.value] = board[board != Board.FOG.value]
        # Better send a clone, don't want anyone to mess up this value
        return self.unfogged_board.clone().type(torch.long), radius, ticks, self.flares.clone()
        
    @abstractmethod
    def sense(self, obs, recall_board = None): pass
    
    @abstractmethod
    def applyOption(self, option): pass


@dataclass
class Option:
    sensorType : Sensor
    filters : List[any] = lambda x : x
    choose : any = lambda x : x
        
