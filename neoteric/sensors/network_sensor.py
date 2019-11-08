from enum import Enum
from neoteric.enums import Board, Action, Direction, SensorType
from dataclasses import dataclass
from neoteric.utils import move_in_direction
import torch
import queue
import random
import functools
from collections import Counter
from neoteric.sensors.sensor import Sensor, Option
import itertools

UNREACHABLE = 100
BOARD_SIZE = 11

@dataclass
class Node:
    position : any
    isOccupiable : bool = False
    enemyNeighbour : bool = False
    teammateNeighbour : bool = False
    fogNeighbour : bool = False
    isPowerup : bool = False  
    isBomb : bool = False
    degree : int = 0
    isSafe : bool = False
    flares : int = 0
    breach : float = 0
    reach : int = UNREACHABLE
    reach_value : float = 0
    isLeaf : bool = True
    parent : any = None
    action : Action = Action.STOP
        
    def reset(self):
        self.isOccupiable = False
        self.enemyNeighbour = False
        self.teammateNeighbour = False
        self.fogNeighbour = False
        self.isPowerup = False  
        self.isBomb = False
        self.degree = 0
        self.isSafe = False
        self.flares = 0
        self.breach = 0
        self.reach = UNREACHABLE
        self.reach_value = 0
        self.isLeaf = True
        self.parent = self.position
        self.action = Action.STOP
        
    def clone(self):
        return Node(
        self.position,
        self.isOccupiable,
        self.enemyNeighbour,
        self.teammateNeighbour,
        self.fogNeighbour,
        self.isPowerup, 
        self.isBomb,
        self.degree,
        self.isSafe,
        self.flares,
        self.breach,
        self.reach,
        self.reach_value,
        self.isLeaf,
        self.parent,
        self.action
        )
    
    def reachable(self):
        return (self.reach<UNREACHABLE)

@dataclass
class State:
    currentlyNotSafe: bool
    sittingOnBomb: bool
    flares: int
    nextToTeammate: bool
    totalSafe : int
    totalTurns : int
    canKick : bool
    isTeammateAlive: bool
    isFollower: bool
    aligned_bomb_pos : any

class Network:
    def __init__(self):
        self.grid = [
            [
                Node((i,j)) for j in range(BOARD_SIZE)
            ]
            for i in range(BOARD_SIZE)
        ]
        self.occupiables = [
            Board.PASSAGE, Board.POWER_BOMB, Board.POWER_RANGE, Board.POWER_KICK
        ]
        self.powerups = [
            Board.POWER_BOMB, Board.POWER_RANGE, Board.POWER_KICK
        ]
        self.spare = []
        self.flatten = lambda matrix: itertools.chain.from_iterable(matrix)
        self.enemy_positions = []
        self.teammate_position = None
        self.prev_ticks = torch.zeros(11,11)
        
    def _get(self, position):
        return self.grid[position[0]][position[1]]
    
    def getAction(self, node):
        ref_node = node
        final_action = node.action
        while ref_node.position != ref_node.parent:
            final_action = ref_node.action
            ref_node = self._get(ref_node.parent)
        return final_action
            
    def choose_majority(self, lst):
        if lst:
            actions = [self.getAction(node) for node in lst]
            ctr = Counter(actions)
            if random.random() < 0.3 and len(ctr) > 1:
                return ctr.most_common(2)[-1][0]
            else:
                return ctr.most_common(1)[0][0]
        return None
    
    def _distance(self, p1, p2):
        return (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2
    
    def getNearestEnemy(self, position):
        ans, d = None, 9999
        for pos in self.enemy_positions:
            if self._distance(position, pos) < d:
                ans, d = pos, self._distance(position, pos)
        return ans
    
    def generateMessage(self, location):
        nearest_cell = (1,1)
        for i in range(1,11,2):
            for j in range(1,11,2):
                if self._distance((i,j),location) < self._distance(nearest_cell,location):
                    nearest_cell = (i,j)
        return ((nearest_cell[0]+1)//2, (nearest_cell[1]+1)//2)
    
        
    def getTeammatePosition(self):
        return self.teammate_position
    
    def hasTurns(self, node):
        ref_node = node
        final_action = node.action
        action_list = [final_action]
        while ref_node.position != ref_node.parent:
            final_action = ref_node.action
            action_list.append(final_action)
            ref_node = self._get(ref_node.parent)
        return (len(Counter(action_list)) > 1)
        
    def _reset(self):
        for i in range(BOARD_SIZE):
            for j in range(BOARD_SIZE):
                self.grid[i][j].reset()
        self.spare.clear()
        self.enemy_positions.clear()
        self.teamamte_position = None
                
    def _exists(self, position):
        return (position[0] >= 0 and position[1] >= 0 and position[0] < BOARD_SIZE and position[1] < BOARD_SIZE)
                
    def reflect(self, position, board, radius, ticks, flares, enemies, teammate, alive, canKick):
        # Update nodes
        self._reset()
        '''
        # Check for moving bombs and update
        for i in range(BOARD_SIZE):
            for j in range(BOARD_SIZE):
                # there was a bomb at t-1, but vanished now, without flames
                if self.prev_ticks[i][j] and (ticks[i][j] <= 0.) and not (Board(board[i][j].item()) is Board.FLAMES):
                    for direction in [Direction.UP, Direction.LEFT, Direction.DOWN, Direction.RIGHT]:
                        if self._exists(move_in_direction((i,j), direction)):
                            n_i, n_j = move_in_direction((i,j), direction)
                            next_cell = Board(board[n_i][n_j].item())
                            if (next_cell is Board.BOMB) and (self.prev_ticks[n_i][n_j] <= 0):
                                #identified direction, check if further advance possible
                                if self._exists(move_in_direction((n_i,n_j), direction)):
                                    f_i, f_j = move_in_direction((n_i,n_j), direction)
                                    if Board(board[f_i][f_j].item()) is Board.PASSAGE:
                                        board[f_i][f_j] = Board.BOMB.value
                                        ticks[f_i][f_j] = ticks[n_i][n_j] - 1
                                        bomb_radius[f_i][f_j] = bomb_radius[n_i][n_j]
                                        board[n_i][n_j] = 0
                                        ticks[n_i][n_j] = 0
                                        bomb_radius[n_i][n_j] = 0 
        '''
        # Updates isOccupiable, isPowerup, degree,3 neighbours, flares, isBomb, isSafe
        for i in range(BOARD_SIZE):
            for j in range(BOARD_SIZE):
                cell, node = Board(board[i][j].item()), self._get((i,j))
                if cell in self.occupiables or (i,j) == position:
                    node.isOccupiable = True  
                    node.isPowerup = (cell in self.powerups)
                    for direction in [Direction.UP, Direction.LEFT, Direction.DOWN, Direction.RIGHT]:
                        if self._exists(move_in_direction(node.position, direction)):
                            n_i, n_j = move_in_direction(node.position, direction)
                            next_cell = Board(board[n_i][n_j].item())
                            if next_cell in self.occupiables:
                                node.degree += 1
                            elif next_cell.value in enemies:
                                self.enemy_positions.append((n_i, n_j))
                                node.enemyNeighbour = True
                            elif next_cell.value == teammate:
                                node.teammateNeighbour = True
                            elif next_cell is Board.FOG:
                                self.fogNeighbour = True
                node.isBomb = (ticks[i][j] > 0)
                node.isSafe = (flares[i][j] <= 0.)
                node.flares = flares[i][j]
        # Updates breach
        for i in range(BOARD_SIZE):
            for j in range(BOARD_SIZE):
                if Board(board[i][j].item()) is Board.WOOD and (self._get((i,j)).flares <= 0):
                    for direction in [Direction.UP, Direction.LEFT, Direction.DOWN, Direction.RIGHT]:
                        length = radius - 1
                        curr_pos = (i,j)
                        while length > 0:
                            if self._exists(move_in_direction(curr_pos, direction)):
                                curr_pos = move_in_direction(curr_pos, direction)
                                if self._get(curr_pos).isOccupiable:
                                    self._get(curr_pos).breach += 1
                                else:
                                    break                                
                            else:
                                break            
                            length -= 1
        
        # Forward
        self._forward(position)
        # Backward
        #self._backward()
        aligned_bomb_pos = None
        for enemy_pos in self.enemy_positions:
            if enemy_pos[0] == position[0]:
                for y in range(1+min(enemy_pos[1],position[1]),max(enemy_pos[1], position[1])):
                    curr_cell = Board(board[enemy_pos[0]][y].item())
                    if ticks[enemy_pos[0]][y]:
                        aligned_bomb_pos = (enemy_pos[0], y)
                    elif not (curr_cell is Board.PASSAGE):
                        aligned_bomb_pos = None
                        break
            if aligned_bomb_pos and self._distance(aligned_bomb_pos, position) > self._distance(aligned_bomb_pos, enemy_pos):
                aligned_bomb_pos = None
            elif (not aligned_bomb_pos) and enemy_pos[1] == position[1]:
                for x in range(min(enemy_pos[0],position[0]),1+max(enemy_pos[0], position[0])):
                    curr_cell = Board(board[x][enemy_pos[1]].item())
                    if ticks[x][enemy_pos[1]]:
                        aligned_bomb_pos = (x, enemy_pos[1])
                    elif not (curr_cell is Board.PASSAGE):
                        aligned_bomb_pos = None
                        break
            if aligned_bomb_pos and self._distance(aligned_bomb_pos, position) > self._distance(aligned_bomb_pos, enemy_pos):
                aligned_bomb_pos = None
                
        currentNode = self._get(position)
        totalSafe, totalTurns = self._getSafeandTurns()
        self.prev_ticks = ticks
        return State((not currentNode.isSafe),
                     currentNode.isBomb,
                     currentNode.flares,
                     currentNode.teammateNeighbour,
                     totalSafe,
                     totalTurns,
                     canKick,
                     (teammate in alive),
                     (Board(board[position].item()).value > Board.AGENT1.value),
                     aligned_bomb_pos
                    )
    
    def _forward(self, position): 
        inserted = torch.zeros(BOARD_SIZE, BOARD_SIZE).type(torch.ByteTensor)
        fque = queue.Queue() 
        root_node = self._get(position)
        root_node.parent = position
        root_node.reach = 0
        fque.put((root_node, 0))
        inserted[position] = True
        while not fque.empty():
            node, reach = fque.get()
            node.reach_value += node.degree * (0.9**reach)
            if reach and node.isBomb and (not node.isSafe):
                continue
            for direction, action in zip([Direction.UP, Direction.LEFT, Direction.DOWN, Direction.RIGHT], 
                                         [Action.UP, Action.LEFT, Action.DOWN, Action.RIGHT]):
                next_position = move_in_direction(node.position, direction)
                if self._exists(next_position) and (self._get(next_position).isOccupiable or self._get(next_position).isBomb):
                    potential_node = self._get(next_position)
                    # if both are unsafe, but you can wait out till potential becomes safe, then that is a safe node
                    #TODO
                    # if has flares and reaching at blast time, then ignore
                    if potential_node.flares and reach+1 >= potential_node.flares and reach+1 < potential_node.flares+3:
                        continue
                    # if already has a shorter path then continue
                    if inserted[next_position] and potential_node.isSafe:
                        #Found better route of same length
                        if reach+1 == potential_node.reach and node.reach_value > potential_node.reach_value:
                            potential_node.reach_value = node.reach_value
                            potential_node.parent = node.position
                            potential_node.action = action
                    # know a path but not a safe one
                    elif inserted[next_position]:
                        # found a safe one
                        if reach+1 > potential_node.flares+2:
                            cloned_potential = potential_node.clone()
                            cloned_potential.parent = node.position
                            cloned_potential.action = action
                            cloned_potential.isSafe = True
                            cloned_potential.reach = cloned_potential.flares + 3 
                            cloned_potential.reach_value = node.reach_value
                            self.spare.append(cloned_potential)
                        # found better path, albeit unsafe one
                        if reach+1 == potential_node.reach and node.reach_value > potential_node.reach_value:
                            potential_node.reach_value = node.reach_value
                            potential_node.parent = node.position
                            potential_node.action = action 
                    else:
                        # never inserted before
                        potential_node.parent = node.position
                        potential_node.action = action
                        potential_node.reach = reach + 1
                        potential_node.reach_value = node.reach_value
                        if (not potential_node.flares) or (reach+1 > potential_node.flares+2):
                            potential_node.isSafe = True
                        if (not potential_node.isBomb) or potential_node.isSafe:
                            node.isLeaf = False
                            fque.put((potential_node, reach + 1))
                            inserted[next_position] = True
        
    def _backward(self): pass
                     
    def _getSafeandTurns(self):
        reachable_safe_nodes = list(filter(lambda node : node.isSafe and node.isOccupiable and node.reach < UNREACHABLE, list(self.flatten(self.grid))+self.spare))
        return len(reachable_safe_nodes), len(list(filter(lambda node : self.hasTurns(node), reachable_safe_nodes)))

class NetworkSensor(Sensor):
    def __init__(self):
        super(NetworkSensor, self).__init__(SensorType.TREE)
        self.network = Network()
        self.position = None
        
    def sense(self, obs):
        board, bombs, ticks, flares = self.simpleSense(obs) 
        self.position = obs['position']
        alive = obs['alive']
        teammate = int(obs['teammate'].value)
        enemies = list(map( lambda item : item.value, obs['enemies']))
        radius = int(obs['blast_strength'])
        bomb_radius = obs['bomb_blast_strength']
        canKick = bool(obs['can_kick'])
        return self.network.reflect(self.position, board.type(torch.LongTensor), radius, ticks, flares, enemies, teammate, alive, canKick)
    
    def applyOption(self, option):
        init_list = [list(self.flatten(self.network.grid)) + self.network.spare]
        candidate_nodes = functools.reduce(lambda a, b : b(a), init_list + option.filters)
        if candidate_nodes:
            node = option.choose(candidate_nodes)
            if not (type(node) is Node):
                return node
            return node, self.network.getAction(node)
        return None, None
    
class NetworkMethods:
    filter_reachable = lambda lst : list(filter(lambda node : node.reach < UNREACHABLE, lst))
    filter_occupiable = lambda lst : list(filter(lambda node : node.isOccupiable, lst))
    filter_safe = lambda lst : list(filter(lambda node : node.isSafe, lst))
    filter_reach_by_k = lambda k : (lambda lst : list(filter(lambda node : node.reach <= k, lst)))
    filter_breach = lambda lst : list(filter(lambda node : node.breach > 0, lst))
    filter_powerups = lambda lst : list(filter(lambda node : node.isPowerup, lst))
    filter_enemy = lambda lst : list(filter(lambda node : node.enemyNeighbour, lst))
    filter_bomb = lambda lst : list(filter(lambda node : node.isBomb and node.flares<10, lst))
    filter_fog = lambda lst : list(filter(lambda node : node.fogNeighbour, lst))
    filter_mate = lambda lst : list(filter(lambda node : node.teammateNeighbour, lst))
    filter_root = lambda lst : list(filter(lambda node : node.reach, lst))
    filter_not_with_action = lambda action : (lambda lst : list(filter(lambda node : not (node.action is action), lst)))
    filter_non_enemy = lambda lst : list(filter(lambda node : not node.enemyNeighbour, lst))
    
    choose_random = lambda lst : random.choice(lst)
    choose_random_top_k = lambda k: (lambda lst : random.choice(sorted(lst, key = lambda node:node.reach)[:k]))
    choose_nearest = lambda lst : sorted(sorted(lst, key = lambda node:node.reach_value, reverse = True), 
                                     key = lambda node:node.reach)[0]
    choose_maximum_breach = lambda lst : sorted(lst, key = lambda node:node.breach, reverse = True)[0]
    
    count_all = lambda lst : len(lst) 
    
    
    '''
    elif Board(board[i][j].item()) is Board.BOMB:
                    bomb_blasted = (ticks[i][j] <= 0.)
                    radius = bomb_radius[i][j]
                    if bomb_blasted:
                        self._get((i,j)).isOccupiable = False
                    for direction in [Direction.UP, Direction.LEFT, Direction.DOWN, Direction.RIGHT]:
                        length = radius - 1
                        curr_pos = (i,j)
                        while length > 0:
                            if self._exists(move_in_direction(curr_pos, direction)):
                                curr_pos = move_in_direction(curr_pos, direction)
                                node = self._get(curr_pos)
                                if bomb_blasted:
                                    node.isOccupiable = False
                                else:
                                    node.flares = ticks[i][j]
                                node.isSafe = False
                                if not (Board(board[curr_pos[0]][curr_pos[1]].item()) is Board.PASSAGE):
                                    break                                
                            else:
                                break            
                            length -= 1
    '''
