from neoteric.sensors.network_sensor import NetworkSensor
from neoteric.sensors.network_sensor import NetworkMethods as tm
from pommerman import agents
from neoteric.utils import Result
from neoteric.enums import Board, Action, Direction, SensorType
from neoteric.sensors.sensor import Option
from collections import Counter
        
class NeotericAgent(agents.BaseAgent):
    
    def __init__(self, original = True, *args, **kwargs):
        super(NeotericAgent, self).__init__(*args, **kwargs)
        self.networkSensor =  NetworkSensor()
        self.safety = Option(SensorType.NETWORK, [tm.filter_safe, tm.filter_reachable, tm.filter_occupiable], tm.choose_random_top_k(8))
        self.evade = Option(SensorType.NETWORK, [tm.filter_safe, tm.filter_reachable, tm.filter_non_enemy, tm.filter_occupiable], tm.choose_nearest)
        self.demolish = Option(SensorType.NETWORK, [tm.filter_safe, tm.filter_reachable, tm.filter_breach, tm.filter_occupiable], tm.choose_nearest)
        self.collect = Option(SensorType.NETWORK, [tm.filter_safe, tm.filter_reachable, tm.filter_powerups], tm.choose_nearest)
        self.kick = Option(SensorType.NETWORK, [tm.filter_bomb, tm.filter_root, tm.filter_reachable], 
                           tm.choose_nearest)
        self.explore = Option(SensorType.NETWORK, [tm.filter_fog, tm.filter_safe, tm.filter_reachable], tm.choose_nearest)
        self.block = Option(SensorType.NETWORK, [tm.filter_enemy, tm.filter_reachable, tm.filter_safe, tm.filter_occupiable], tm.choose_nearest)        
        self.majority_safe = Option(SensorType.NETWORK, [tm.filter_safe, tm.filter_reachable, tm.filter_occupiable, tm.filter_reach_by_k(10)], 
                                tm.choose_random_top_k(16))
        self.original = original
        self.dummy = (NeotericAgent(False) if original else None)
        self.lifespan = 0
        self.result = Result()
        self.prev_action, self.curr_action = None, None
        self.prev_position = None
        self.prev_state = False
        self.locked_for = 0
        self.state = None
        self.kick_recommendations = []
        self.powerups = [1, 2, 0]
        self.teammate_powerups = [1, 2, 0]
   
    def getState(self):
        return self.state
    
    def act(self, obs, action_space):
        try:
            if obs['ammo'] != self.powerups[0]:
                call_to_pos = (6,1)
                self.powerups[0] = 1 + self.powerups[0]
            elif obs['blast_strength'] != self.powerups[1]:
                call_to_pos = (6,2)
                self.powerups[1] = 1 + self.powerups[1]
            elif int(obs['can_kick']) != self.powerups[2]:
                call_to_pos = (6,3)
                self.powerups[2] = 1 + self.powerups[0]
            else :
                call_to_pos = obs['position']

            if obs['message'][0] == 6:
                self.teammate_powerups[obs['message'][1]-1] = 1 + self.teammate_powerups[obs['message'][1]-1]

            self.lifespan += 1 

            teammate_loc = None
            for i in range(11):
                for j in range(11):
                    if obs['board'][i][j].item() == obs['teammate'].value:
                        teammate_loc = (i,j)
                        break

            if self.original and teammate_loc and obs['board'][obs['position']].item() > Board.AGENT1.value:
                modified_obs = obs.copy()
                # SWAP yourself with Teammate
                modified_obs['board'][teammate_loc] = obs['board'][obs['position']].item()
                modified_obs['board'][obs['position']] = obs['board'][teammate_loc].item()
                modified_obs['position'] = teammate_loc
                # Swap powers
                modified_obs['ammo'] = self.teammate_powerups[0]
                modified_obs['blast_strength'] = self.teammate_powerups[1]
                modified_obs['can_kick'] = self.teammate_powerups[2]                           
                action_value = self.dummy.act(modified_obs, action_space)
                if type(action_value) is tuple:
                    leader_action = Action(action_value[0])
                else:
                    leader_action = Action(action_value)
                if leader_action is Action.BOMB:
                    obs['bomb_blast_strength'][teammate_loc] = self.teammate_powerups[1]
                    obs['bomb_life'][teammate_loc] = 10

            state = self.networkSensor.sense(obs)

            self.state = state

            safety_node, safety_action = self.networkSensor.applyOption(self.safety)
            evade_node, evade_action = self.networkSensor.applyOption(self.evade)
            majority_safe_node, majority_safe_action = self.networkSensor.applyOption(self.majority_safe)

            demolish_node, demolish_action = self.networkSensor.applyOption(self.demolish)
            collect_node, collect_action = self.networkSensor.applyOption(self.collect)
            kick_node, kick_action = self.networkSensor.applyOption(self.kick)
            block_node, block_action = self.networkSensor.applyOption(self.block)
            explore_node, explore_action = self.networkSensor.applyOption(self.explore)
            deflect = Option(SensorType.NETWORK, [tm.filter_safe, tm.filter_reachable, tm.filter_occupiable, tm.filter_not_with_action(self.prev_action)], tm.choose_nearest)
            deflect_node, deflect_action = self.networkSensor.applyOption(deflect)

            if majority_safe_action:
                action_lst = []
                for _ in range(40):
                    _, action = self.networkSensor.applyOption(self.majority_safe)
                    action_lst.append(action)
                majority_safe_action = Counter(action_lst).most_common(1)[0][0]

            enemy_loc = (self.networkSensor.network.getNearestEnemy(block_node.position) if block_action else None)
            potential_hit, recommend_kick = False, False
            if self.original and enemy_loc:
                modified_obs = obs.copy()
                # Replace enemy with self
                modified_obs['position'] = enemy_loc
                modified_obs['board'][enemy_loc] = obs['board'][obs['position']].item()
                modified_obs['board'][obs['position']] = obs['board'][enemy_loc].item()
                self.dummy.act(modified_obs, action_space)
                current_state = self.dummy.getState()
                # Replace self with Bomb
                modified_obs['board'][obs['position']] = Board.BOMB.value
                modified_obs['bomb_blast_strength'][obs['position']] = int(obs['blast_strength'])
                modified_obs['bomb_life'][obs['position']] = 10
                self.dummy.act(modified_obs, action_space)
                future_state = self.dummy.getState()
                potential_hit = (future_state.totalSafe <= 0) or (state.canKick and future_state.totalSafe <= 2 and current_state.totalSafe > 2)
                if potential_hit and future_state.totalSafe:
                    recommend_kick = True
            self.kick_recommendations.append(recommend_kick)

            teammate_safe = False
            mate_loc = self.networkSensor.network.getTeammatePosition()
            if self.original and state.isTeammateAlive and mate_loc:
                modified_obs = obs.copy()
                # Replace self with Bomb
                modified_obs['board'][obs['position']] = Board.BOMB.value
                modified_obs['bomb_blast_strength'][obs['position']] = int(obs['blast_strength'])
                modified_obs['bomb_life'][obs['position']] = 10
                # Replace teammate with self
                modified_obs['position'] = mate_loc
                self.dummy.act(modified_obs, action_space)
                future_state = self.dummy.getState()
                teammate_safe = (future_state.totalSafe > 0)

            safety_node, safety_action = self.networkSensor.applyOption(self.safety)
            evade_node, evade_action = self.networkSensor.applyOption(self.evade)
            majority_safe_node, majority_safe_action = self.networkSensor.applyOption(self.majority_safe)

            demolish_node, demolish_action = self.networkSensor.applyOption(self.demolish)
            collect_node, collect_action = self.networkSensor.applyOption(self.collect)
            kick_node, kick_action = self.networkSensor.applyOption(self.kick)
            block_node, block_action = self.networkSensor.applyOption(self.block)
            explore_node, explore_action = self.networkSensor.applyOption(self.explore)
            deflect = Option(SensorType.NETWORK, [tm.filter_safe, tm.filter_reachable, tm.filter_occupiable, tm.filter_not_with_action(self.prev_action)], tm.choose_nearest)
            deflect_node, deflect_action = self.networkSensor.applyOption(deflect)

            if majority_safe_action:
                action_lst = []
                for _ in range(40):
                    _, action = self.networkSensor.applyOption(self.majority_safe)
                    action_lst.append(action)
                majority_safe_action = Counter(action_lst).most_common(1)[0][0]

            decoded_location = (obs['message'][0]*2 - 1, obs['message'][1] * 2 - 1)
            #if original and follower and not a dummy message and location reachable, but not too close, then go
            if self.original and state.isFollower and obs['message'][0] and obs['message'][0]<6 and self.networkSensor.network._get(decoded_location).reachable() and self.networkSensor.network._get(decoded_location).reach > 3:
                self.curr_action = self.networkSensor.network._get(decoded_location).action
            if majority_safe_action and state.currentlyNotSafe and state.sittingOnBomb:
                self.curr_action = majority_safe_action
            elif state.canKick and len(self.kick_recommendations)>2 and self.kick_recommendations[-3] and kick_action:
                self.curr_action = kick_action
            elif state.canKick and state.aligned_bomb_pos and (state.flares <= 0 or state.flares > 2):
                self.curr_action = self.networkSensor.network._get(state.aligned_bomb_pos).action
            elif evade_action and state.currentlyNotSafe and state.flares < 3:
                self.curr_action = evade_action
            elif safety_action and state.currentlyNotSafe and state.flares < 8:
                self.curr_action = safety_action
            #elif safety_action and state.currentlyNotSafe: # and can-kick and enemy on the line-of-fire and teammate isn't
            elif state.currentlyNotSafe and (not safety_action) and kick_action:
                self.curr_action = kick_action
            elif block_action and ((block_action is Action.STOP) or potential_hit) and state.totalTurns > 0 and (not state.nextToTeammate or teammate_safe):
                self.curr_action = Action.BOMB
                if call_to_pos[0] != 6:
                    call_to_pos = block_node.position
            elif block_action and not (block_action is Action.STOP):
                self.curr_action = block_action
                if call_to_pos[0] != 6:
                    call_to_pos = block_node.position
            elif collect_action:
                self.curr_action = collect_action
            elif demolish_action and demolish_action is Action.STOP and state.totalTurns > 0:
                self.curr_action = Action.BOMB
            elif demolish_action and not (demolish_action is Action.STOP):
                self.curr_action = demolish_action
            elif explore_action:
                self.curr_action = explore_action
            elif safety_action:
                self.curr_action = safety_action
            else:
                self.curr_action = Action.STOP

            if safety_action and self.prev_position == obs['position'] and self.prev_action is self.curr_action and (
                not self.curr_action is Action.STOP):
                self.locked_for += 1
                if state.currentlyNotSafe and deflect_action:
                    self.curr_action = deflect_action
                elif self.locked_for > 5:
                    self.curr_action = safety_action
            else:
                self.locked_for = 0
            if self.curr_action is Action.BOMB and obs['ammo'] <= 0:
                self.locked_for = 0
                self.curr_action = Action.STOP
            self.prev_position = obs['position']
            self.prev_action = self.curr_action
            if call_to_pos[0] < 6:
                m1, m2 = self.networkSensor.network.generateMessage(call_to_pos)
            else:
                m1, m2 = call_to_pos[0], call_to_pos[1]
            return self.curr_action.value, m1, m2
        except:
            return Action.STOP
        
    def episode_end(self, reward):
        super(NeotericAgent, self).episode_end(reward)
        self.result.update(reward, (self.lifespan>=800))
        self.lifespan = 0
        self.kick_recommendations.clear()
        self.prev_action, self.curr_action = None, None
        self.prev_position = None
        self.prev_state = False
        self.locked_for = 0
        self.state = None

