import numpy as np
import math
import time
import matplotlib.pyplot as plt
from algorithms.dqn import DeepQNetwork

from pysc2.lib import actions
from pysc2.lib import features

_NO_OP = actions.FUNCTIONS.no_op.id
_SELECT_POINT = actions.FUNCTIONS.select_point.id
_SELECT_ARMY = actions.FUNCTIONS.select_army.id
_SELECT_UNIT = actions.FUNCTIONS.select_unit.id
_ATTACK_SCREEN = actions.FUNCTIONS.Attack_screen.id
_MOVE_SCREEN = actions.FUNCTIONS.Move_screen.id


_PLAYER_RELATIVE = features.SCREEN_FEATURES.player_relative.index
_PLAYER_ID = features.SCREEN_FEATURES.player_id.index


_PLAYER_SELF = 1
_PLAYER_HOSTILE = 4

_UNIT_ALLIANCE = 1
_UNIT_HEALTH = 2
_UNIT_X = 12
_UNIT_Y = 13
_UNIT_RADIUS = 15 # find range
_UNIT_HEALTH_RATIO = 7
_UNIT_IS_SELECTED = 17

_NOT_QUEUED = [0]
_QUEUED = [1]

ACTION_DO_NOTHING = 'donothing'
MOVE_UP = 'moveup'
MOVE_DOWN = 'movedown'
MOVE_LEFT = 'moveleft'
MOVE_RIGHT = 'moveright'
MOVE_UP_LEFT = 'moveupleft'
MOVE_DOWN_LEFT = 'movedownleft'
MOVE_UP_RIGHT = 'moveupright'
MOVE_DOWN_RIGHT = 'movedownright'
ACTION_SELECT_UNIT_1 = 'selectunit1'
ACTION_SELECT_UNIT_2 = 'selectunit2'
ATTACK_TARGET = 'attacktarget'

smart_actions = [
    ATTACK_TARGET,
    MOVE_UP,
    MOVE_DOWN,
    MOVE_LEFT,
    MOVE_RIGHT,
    ACTION_SELECT_UNIT_1,
    ACTION_SELECT_UNIT_2
]

# Change this if using a different map
DEFAULT_ENEMY_COUNT = 1
DEFAULT_PLAYER_COUNT = 2

class SmartAgent(object):
    def __init__(self):
        # from the origin base.agent
        self.reward = 0
        self.episodes = 0
        self.steps = 0
        self.obs_spec = None
        self.action_spec = None

        self.dqn = DeepQNetwork(
            len(smart_actions),
            5, # one of the most important data that needs to be update manually
            learning_rate=0.01,
            reward_decay=0.9,
            e_greedy=0.9,
            replace_target_iter=200,
            memory_size=50000,
            batch_size=320,
            e_greedy_increment=None,
            output_graph=True
        )

        # self defined vars
        self.fighting = False
        self.win = 0
        self.player_hp = []
        self.enemy_hp = []
        self.previous_enemy_hp = []
        self.previous_player_hp = []

        self.previous_action = None
        self.previous_state = None

    def step(self, obs):
        # from the origin base.agent
        self.steps += 1
        self.reward += obs.reward

        current_state, enemy_hp, player_hp, enemy_loc, player_loc, distance, selected, enemy_count, player_count = self.extract_features(obs)

        self.player_hp.append(sum(player_hp))
        self.enemy_hp.append(sum(enemy_hp))

        # scripted the few initial actions to increases the learning performance
        while not self.fighting:
            for i in range(0, player_count):
                if distance[i] < 20:
                    self.fighting = True
                    return actions.FunctionCall(_NO_OP, [])

            return actions.FunctionCall(_MOVE_SCREEN, [_NOT_QUEUED, enemy_loc[0]])

        # record the transitions to memory and learn by DQN
        if self.previous_action is not None:
            reward = self.get_reward(obs, distance, player_hp, enemy_hp, player_count, enemy_count)

            self.dqn.store_transition(np.array(self.previous_state), self.previous_action, reward, np.array(current_state))
            self.dqn.learn()

        # get the disabled actions and used it when choosing actions
        disabled_actions = self.get_disabled_actions(player_loc, selected)
        rl_action = self.dqn.choose_action(np.array(current_state), disabled_actions)
        smart_action = smart_actions[rl_action]

        self.previous_state = current_state
        self.previous_action = rl_action
        self.previous_enemy_hp = enemy_hp
        self.previous_player_hp = player_hp

        return self.perform_action(obs, smart_action, player_loc, enemy_loc, selected, player_count, enemy_count)

    def get_reward(self, obs, distance, player_hp, enemy_hp, player_count, enemy_count):
        reward = 0

        # give reward by calculating opponents units lost hp
        for i in range(0, enemy_count):
            reward += int((100 - enemy_hp[i]) * 10 / 100)

        # give reward by remaining player units hp
        for i in range(0, player_count):
            reward += int(player_hp[i] * 5 / 60)

        # get killed and lost unit reward from the map
        reward += obs.reward

        # reward only player's unit maintains a certain distance with the enemy
        # for i in range(0, DEFAULT_PLAYER_COUNT):
        #     if 25 >= distance[i] > 15:
        #         reward += 2
        #     elif distance[i] > 42:
        #         reward -= 2
        #     elif 42 >= distance[i] > 25:
        #         reward -= 1
        #     else:
        #         reward -= 5

        return reward

    # extract all the desired features as inputs for the DQN
    def extract_features(self, obs):
        var = obs.observation['feature_units']
        # get units' location and distance
        enemy, player = [], []

        # get health
        enemy_hp, player_hp = [], []

        # record the selected army
        is_selected = []

        # unit_count
        enemy_unit_count, player_unit_count = 0, 0

        for i in range(0, var.shape[0]):
            if var[i][_UNIT_ALLIANCE] == _PLAYER_HOSTILE:
                enemy.append((var[i][_UNIT_X], var[i][_UNIT_Y]))
                enemy_hp.append(var[i][_UNIT_HEALTH])
                enemy_unit_count += 1
            else:
                player.append((var[i][_UNIT_X], var[i][_UNIT_Y]))
                player_hp.append(var[i][_UNIT_HEALTH])
                is_selected.append(var[i][_UNIT_IS_SELECTED])
                player_unit_count += 1

        # append if necessary so that maintains fixed length for current state
        for i in range(player_unit_count, DEFAULT_PLAYER_COUNT):
            player.append((-1, -1))
            player_hp.append(0)
            is_selected.append(-1)

        for i in range(enemy_unit_count, DEFAULT_ENEMY_COUNT):
            enemy.append((-1, -1))
            enemy_hp.append(0)

        # get distance
        min_distance = [0 for x in range(DEFAULT_PLAYER_COUNT)]

        for i in range(0, player_unit_count):
            for j in range(0, enemy_unit_count):
                distance = int(math.sqrt((player[i][0] - enemy[j][0]) ** 2 + (
                        player[i][1] - enemy[j][1]) ** 2))

                if distance < min_distance[i]:
                    min_distance[i] = distance

        # flatten the array so that all features are a 1D array
        feature1 = np.array(enemy_hp).flatten() # enemy's hp
        feature2 = np.array(player_hp).flatten() # player's hp
        feature3 = np.array(enemy).flatten() # enemy's coordinates
        feature4 = np.array(player).flatten() # player's coordinates
        feature5 = np.array(min_distance).flatten() # distance

        # combine all features horizontally
        current_state = np.hstack((feature1, feature2, feature5))

        return current_state, feature1, feature2, enemy, player, min_distance, is_selected, enemy_unit_count, player_unit_count

    # make the desired action calculated by DQN
    def perform_action(self, obs, action, unit_locs, enemy_locs, selected, player_count, enemy_count):
        index = -1

        for i in range(0, DEFAULT_PLAYER_COUNT):
            if selected[i] == 1:
                index = i

        x = unit_locs[index][0]
        y = unit_locs[index][1]

        if action == ACTION_SELECT_UNIT_1:
            if _SELECT_POINT in obs.observation['available_actions']:
                if player_count >= 1:
                    return actions.FunctionCall(_SELECT_POINT, [_NOT_QUEUED, unit_locs[0]])

        elif action == ACTION_SELECT_UNIT_2:
            if _SELECT_POINT in obs.observation['available_actions']:
                if player_count >= 2:
                    return actions.FunctionCall(_SELECT_POINT, [_NOT_QUEUED, unit_locs[1]])

        #-----------------------
        elif action == ATTACK_TARGET:
            if _ATTACK_SCREEN in obs.observation["available_actions"]:
                if enemy_count >= 1:
                    return actions.FunctionCall(_ATTACK_SCREEN, [_NOT_QUEUED, enemy_locs[0]])  # x,y => col,row
        # ------------------------

        elif action == MOVE_UP:
            if _MOVE_SCREEN in obs.observation["available_actions"] and index != -1:
                x = x
                y = y - 8

                if 0 > x:
                    x = 0
                elif x > 83:
                    x = 83

                if 0 > y:
                    y = 0
                elif y > 83:
                    y = 83

                return actions.FunctionCall(_MOVE_SCREEN, [_NOT_QUEUED, [x, y]])  # x,y => col,row

        elif action == MOVE_DOWN:
            if _MOVE_SCREEN in obs.observation["available_actions"] and index != -1:
                x = x
                y = y + 8

                if 0 > x:
                    x = 0
                elif x > 83:
                    x = 83

                if 0 > y:
                    y = 0
                elif y > 83:
                    y = 83

                return actions.FunctionCall(_MOVE_SCREEN, [_NOT_QUEUED, [x, y]])

        elif action == MOVE_LEFT:
            if _MOVE_SCREEN in obs.observation["available_actions"] and index != -1:
                x = x - 8
                y = y

                if 0 > x:
                    x = 0
                elif x > 83:
                    x = 83

                if 0 > y:
                    y = 0
                elif y > 83:
                    y = 83

                return actions.FunctionCall(_MOVE_SCREEN, [_NOT_QUEUED, [x, y]])

        elif action == MOVE_RIGHT:
            if _MOVE_SCREEN in obs.observation["available_actions"] and index != -1:
                x = x + 8
                y = y

                if 0 > x:
                    x = 0
                elif x > 83:
                    x = 83

                if 0 > y:
                    y = 0
                elif y > 83:
                    y = 83

                return actions.FunctionCall(_MOVE_SCREEN, [_NOT_QUEUED, [x, y]])

        self.previous_action = 5
        return actions.FunctionCall(_SELECT_POINT, [_NOT_QUEUED, unit_locs[0]])

    # get_disabled_actions filters the redundant actions from the action space
    def get_disabled_actions(self, player_loc, selected):
        disabled_actions = []

        index = -1

        for i in range(0, DEFAULT_PLAYER_COUNT):
            if selected[i] == 1:
                index = i
                break

        x = player_loc[index][0]
        y = player_loc[index][1]

        # not selecting attack target if the previous actions is already attack target
        if self.previous_action == smart_actions.index(ATTACK_TARGET):
            disabled_actions.append(smart_actions.index(ATTACK_TARGET)) #0

        # not selecting a specific move action if the unit cannot move toward that direction (at the border)
        if y <= 5:
            disabled_actions.append(smart_actions.index(MOVE_UP)) #1

        if y >= 78:
            disabled_actions.append(smart_actions.index(MOVE_DOWN)) #2

        if x <= 5:
            disabled_actions.append(smart_actions.index(MOVE_LEFT)) #3

        if x >= 78:
            disabled_actions.append(smart_actions.index(MOVE_RIGHT)) #4

        # not selecting the same unit if the previous actions already attempts to select it
        if self.previous_action == smart_actions.index(ACTION_SELECT_UNIT_1):
            disabled_actions.append(smart_actions.index(ACTION_SELECT_UNIT_1)) #5

        if self.previous_action == smart_actions.index(ACTION_SELECT_UNIT_2):
            disabled_actions.append(smart_actions.index(ACTION_SELECT_UNIT_2)) #6

        return disabled_actions

    def plot_player_hp(self, path, save):
        plt.plot(np.arange(len(self.player_hp)), self.player_hp)
        plt.ylabel('player hp')
        plt.xlabel('training steps')
        if save:
            plt.savefig(path + '/player_hp.png')
        plt.show()

    def plot_enemy_hp(self, path, save):
        plt.plot(np.arange(len(self.enemy_hp)), self.enemy_hp)
        plt.ylabel('enemy hp')
        plt.xlabel('training steps')
        if save:
            plt.savefig(path + '/enemy_hp.png')
        plt.show()

    # from the origin base.agent
    def setup(self, obs_spec, action_spec):
        self.obs_spec = obs_spec
        self.action_spec = action_spec

    # from the origin base.agent
    def reset(self):
        self.episodes += 1
        # added instead of original
        self.fighting = False



