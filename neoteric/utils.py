import operator
from dataclasses import dataclass
import time
import torch

move_in_direction = lambda pos, direction : tuple(map(operator.add, pos, direction.value))

def play(env):
    state = env.reset()
    done = False
    while not done:
        time.sleep(0.5)
        env.render()
        actions = env.act(state)
        state, reward, done, info = env.step(actions)
        
def evaluate(env, episodes):
    for e in range(episodes):
        state = env.reset()
        done = False
        while not done:
            actions = env.act(state)
            state, reward, done, info = env.step(actions)
            
@dataclass
class Result:
    wins : int = 0
    ties : int  = 0
    losses : int  = 0
    binary_wins : any = None
        
    def update(self, reward, timedOut = False):
        if self.binary_wins is None:
            self.binary_wins = []
        if reward > 0:
            self.wins += 1
            self.binary_wins.append(1)
        elif timedOut:
            self.ties += 1
            self.binary_wins.append(0)
        else:
            self.losses += 1
            self.binary_wins.append(0)
            

