import csv
import os
from _csv import writer
from typing import Callable, Dict
import enum
import random
import re

from matrx.actions.move_actions import MoveNorth, MoveWest
from matrx.actions.object_actions import GrabObject, DropObject

from bw4t.BW4TBrain import BW4TBrain
from matrx.agents.agent_utils.state import State
from matrx.agents.agent_utils.navigator import Navigator
from matrx.agents.agent_utils.state_tracker import StateTracker
from matrx.actions.door_actions import OpenDoorAction
from matrx.messages.message import Message

Action = tuple[str, dict] | None


class Phase(enum.Enum):
    PLAN_PATH_TO_CLOSED_DOOR = 1
    FOLLOW_PATH_TO_CLOSED_DOOR = 2
    OPEN_DOOR = 3

    ENTER_ROOM = 4
    PLAN_ROOM_CHECK = 10
    FOLLOW_ROOM_CHECK = 11

    PLAN_PATH_TO_TARGET_ITEMS = 5
    FOLLOW_PATH_TO_TARGET_ITEMS = 6
    GET_ITEM = 7

    PLAN_PATH_TO_GOAL = 8
    FOLLOW_PATH_TO_GOAL = 9
    CANCEL_GOAL = 12


class CustomBaselineAgent(BW4TBrain):
    """
    Agent that contains all non-agent specific logic
    """

    def __init__(self, settings: Dict[str, object]):
        super().__init__(settings)
        self._phase: Phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        self._teamMembers = []

        self._capacity: int = 1
        self._collectables: list[dict] = []
        self._target_items: list[dict] = []
        self._is_carrying: list[dict] = []
        self._last_grab_action_succesful: bool = True

        self._goal_blocks: list[dict] = []

        # dropping items on the goals has to go in the right order
        # this corresponds to a goal in the self._goal_blocks attribute
        self._target_goal_index: int = 0

        # is true when acting on second-hand information
        self._acting_on_trust: bool = False
        self._trusting_agent: dict[str, bool] = {}
        self._trustBeliefs: dict = {}

        self._prev_phase: Phase|None = None

        self._memory: dict[Phase, dict] = {
            Phase.PLAN_PATH_TO_CLOSED_DOOR: {},
            Phase.FOLLOW_PATH_TO_CLOSED_DOOR: {},
            Phase.OPEN_DOOR: {},

            Phase.ENTER_ROOM: {},
            Phase.PLAN_ROOM_CHECK: {},
            Phase.FOLLOW_ROOM_CHECK: {},

            Phase.PLAN_PATH_TO_TARGET_ITEMS: {},
            Phase.FOLLOW_PATH_TO_TARGET_ITEMS: {},
            Phase.GET_ITEM: {},

            Phase.PLAN_PATH_TO_GOAL: {},
            Phase.FOLLOW_PATH_TO_GOAL: {},
        }

        self._agent_name: None | str = None
        self._current_state: State
        self._repeat_action: int = 0

        self._switchPhase: dict[Phase, Callable[[], Action | None]] = {
            Phase.PLAN_PATH_TO_CLOSED_DOOR: self._planPathToClosedDoorPhase,
            Phase.FOLLOW_PATH_TO_CLOSED_DOOR: self._followPathToClosedDoorPhase,
            Phase.OPEN_DOOR: self._openDoorPhase,

            Phase.ENTER_ROOM: self._enterRoomPhase,
            Phase.PLAN_ROOM_CHECK: self._planRoomCheckPhase,
            Phase.FOLLOW_ROOM_CHECK: self._followRoomCheckPhase,

            Phase.PLAN_PATH_TO_TARGET_ITEMS: self._planPathToTargetItemsPhase,
            Phase.FOLLOW_PATH_TO_TARGET_ITEMS: self._followPathToTargetItemsPhase,
            Phase.GET_ITEM: self._getItemPhase,

            Phase.PLAN_PATH_TO_GOAL: self._planPathToGoalPhase,
            Phase.FOLLOW_PATH_TO_GOAL: self._followPathToGoalPhase,
            Phase.CANCEL_GOAL: self._cancelGoalPhase,
        }

    def initialize(self) -> None:
        super().initialize()
        self._state_tracker = StateTracker(agent_id=self.agent_id)
        self._navigator = Navigator(agent_id=self.agent_id,
                                    action_set=self.action_set, algorithm=Navigator.A_STAR_ALGORITHM)

    def filter_on_bw4t_observations(self, state: State) -> State:
        return state

    def decide_on_bw4t_action(self, state: State) -> tuple[str, dict]:
        assert state is not None

        self._current_state = state
        self._agent_name = self._current_state[self.agent_id]['obj_id']

        if len(self._goal_blocks) == 0:
            self._init_goal_targets()

        # Add team members
        for member in self._current_state['World']['team_members']:
            if member != self._agent_name and member not in self._teamMembers:
                self._teamMembers.append(member)

        # Process messages from team members
        received_messages = self._processMessages(self._teamMembers)

        # Update trust beliefs for team members
        self._updateTrustBelief(self._teamMembers, received_messages)
        self._act_on_trust(self._teamMembers, received_messages)

        while True:
            assert self._phase is not None
            self._prev_phase = self._phase
            action_and_subject = self._switchPhase[self._phase]()

            if action_and_subject is not None and action_and_subject[0] is not None:
                return action_and_subject

    # ==== DOOR PHASE ====

    def _planPathToClosedDoorPhase(self) -> Action | None:
        self._navigator.reset_full()
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        closed_doors = [door for door in all_doors if not door['is_open']]

        # TODO maybe separate state?
        if len(closed_doors) == 0:
            if self._checkForPossibleGoal():
                return None
            self._door = random.choice(all_doors)
        else:
            self._door = random.choice(closed_doors)

        door_loc = self._door['location']
        # Location in front of door is south from door
        door_loc = door_loc[0], door_loc[1] + 1

        # Send message of current action
        self._sendMessage('Moving to ' + self._door['room_name'])
        self._navigator.add_waypoints([door_loc])

        self._phase = Phase.FOLLOW_PATH_TO_CLOSED_DOOR

    def _followPathToClosedDoorPhase(self) -> Action | None:
        self._state_tracker.update(self._current_state)

        # Follow path to door
        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        self._phase = Phase.OPEN_DOOR

    def _openDoorPhase(self) -> Action | None:
        self._sendMessage('Opening door of ' + self._door['room_name'])
        self._phase = Phase.ENTER_ROOM

        # Open door
        return OpenDoorAction.__name__, {'object_id': self._door['obj_id']}

    def _enterRoomPhase(self) -> Action | None:
        self._repeat_then(1, Phase.PLAN_ROOM_CHECK)

        return MoveNorth.__name__, {}

    # ==== ROOM PHASE ====

    def _planRoomCheckPhase(self) -> Action | None:
        current_x, current_y = self._current_state[self.agent_id]['location']
        next_locations: list[tuple[int, int]] = \
            [(current_x, current_y - 1), (current_x - 1, current_y - 1), (current_x - 1, current_y)]

        self._navigator.reset_full()
        self._navigator.add_waypoints(next_locations)
        self._phase = Phase.FOLLOW_ROOM_CHECK

    def _followRoomCheckPhase(self) -> Action | None:
        self._sendMessage('Searching through ' + self._door['room_name'])
        self._saveObjectsAround()

        self._state_tracker.update(self._current_state)
        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        if len(self._collectables) == 0:
            self._target_items.clear()
        else:
            goal_target_items, all_found_goal_items = self._check_collectables()
            for goal in all_found_goal_items:
                self._sendMessage(
                    'Found goal block ' + str(goal['visualization']) + ' at location ' + str(goal['location'])
                )

            self._target_items = goal_target_items[0:self._capacity]
            self._collectables.clear()

        self._phase = Phase.PLAN_PATH_TO_TARGET_ITEMS

    def _planPathToTargetItemsPhase(self) -> Action | None:
        if len(self._target_items) == 0:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            self._planPathToClosedDoorPhase()
        else:
            self._navigator.reset_full()
            for i in range(len(self._target_items)):
                self._navigator.add_waypoints([self._target_items[i]['location']])

            self._phase = Phase.FOLLOW_PATH_TO_TARGET_ITEMS

    def _followPathToTargetItemsPhase(self) -> Action | None:
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        if len(self._target_items) == 0:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        else:
            self._phase = Phase.GET_ITEM

    def _getItemPhase(self) -> Action | None:
        # TODO: probably doesn't need to be its own phase
        self._phase = Phase.PLAN_PATH_TO_GOAL

        if not self._checkTargetItemsIfHint():
            # Hint wasn't corrent
            # TODO Penalize lying agent
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            return

        self._is_carrying.append(self._target_items[0])
        self._target_items.clear()

        self._sendMessage(
            'Picking up goal block ' + str(self._is_carrying[-1]['visualization']) + ' at location ' + str(
                self._is_carrying[-1][
                    'location'])
        )

        return GrabObject.__name__, {'object_id': self._is_carrying[0]['obj_id']}

    def _checkTargetItemsIfHint(self):
        # HACK Why do we need to check for this?
        # if len(self._target_items) == 0:
        #     return False

        # if target item is only a hint by another agent
        if not 'obj_id' in self._target_items[0]:
            close_items = self._current_state.get_objects_in_area(
                top_left=self._current_state[self.agent_id]['location'], width=1, height=1)
            close_collectables = self._filter_collectables(close_items)

            # check if the item under you matches the description
            if len(close_collectables) > 0 and self._compare_blocks(self._target_items[0], close_collectables[0]):
                self._target_items[0]['obj_id'] = close_collectables[0]['obj_id']
            else:
                # TODO Penalize lying agent
                # if not the case, remove current item as considerable goal collectable match for goal object
                self._goal_blocks[self._target_items[0]['goal_index']].pop('collectable_match')
                self._target_items.clear()
                return False

        return True

    # ==== GOAL PHASE ====

    def _planPathToGoalPhase(self) -> Action | None:
        # Could possibly be done a bit more elegantly
        target_locations: list[tuple] = map(lambda e: self._goal_blocks[e['goal_index']]['location'], self._is_carrying)

        if len(self._is_carrying) == 0:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            return

        else:  # Drop off goal object to its correct location
            self._navigator.reset_full()
            self._navigator.add_waypoints(target_locations)
            self._phase = Phase.FOLLOW_PATH_TO_GOAL

    def _followPathToGoalPhase(self) -> Action | None:
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        if self._verify_goal_index():
            # TODO Also update trust
            self._target_goal_index += 1
            return self._dropBlockIfCarrying()

        self._target_goal_index -= 1
        self._phase = Phase.CANCEL_GOAL

    def _cancelGoalPhase(self) -> Action | None:
        if self._current_state[self.agent_id]['location'] != self._goal_blocks[self._target_goal_index]['location']:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            return self._dropBlockIfCarrying()

        return MoveWest.__name__, {}

    def _verify_goal_index(self) -> bool:
        current_location = self._current_state[self.agent_id]['location']
        # south of us should be a collectable
        current_location = current_location[0], current_location[1] + 1
        objects = self._current_state.get_objects_in_area(top_left=current_location, width=1, height=1)

        return self._target_goal_index == 0 or len(self._filter_collectables(objects)) > 0

    def _dropBlockIfCarrying(self, check_for_goal: bool = True) -> Action | None:
        if len(self._is_carrying) == 0:
            return None

        block: dict = self._is_carrying.pop()
        current_location: tuple = self._current_state[self.agent_id]['location']

        self._sendMessage(
            'Dropped goal block ' + str(block['visualization']) + ' at drop location ' + str(current_location))

        if check_for_goal and not self._checkForPossibleGoal():
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

        return DropObject.__name__, {'object_id': block['obj_id']}

    def _checkForPossibleGoal(self, set_target_and_phase: bool = True) -> bool:
        match = self._check_for_current_target_goal()

        if match is not None and set_target_and_phase:
            self._target_items = [match]
            self._phase = Phase.PLAN_PATH_TO_TARGET_ITEMS

        return match is not None

    # ==== MESSAGES ====

    def _sendMessage(self, mssg) -> None:
        '''
        Enable sending messages in one line of code
        '''
        msg = Message(content=mssg, from_id=self._agent_name)
        if msg.content not in self.received_messages:
            self.send_message(msg)

    def _processMessages(self, teamMembers) -> dict:
        '''
        Process incoming messages and create a dictionary with received messages from each team member.
        '''
        receivedMessages = {}
        for member in teamMembers:
            receivedMessages[member] = []
        for mssg in self.received_messages:
            for member in teamMembers:
                if mssg.from_id == member:
                    receivedMessages[member].append(mssg.content)
        return receivedMessages

    # ==== TRUST ====

    def _act_on_trust(self, member, received) -> Action | None:
        for member in received.keys():
            # Ignore messages from agents we don't trust
            if self._trustBeliefs[member] <= 0.2 and self._trusting_agent[member]:
                self._sendMessage("I don't trust " + member)
                self._trusting_agent[member] = False
            else:
                for message in received[member]:
                    if member != self.agent_id and self._trusting_agent[member]:
                        # TODO if picking up object, remove from considered collectable goals
                        if 'Found' in message:
                            item = self.__object_from_message(message)
                            self.__check_item_and_add_if_goal(item)

                        if 'Dropped' in message:
                            item = self.__object_from_message(message)
                            self.__check_item_and_add_if_goal(item)
                            item_goal_index = self.__get_matching_goal_index(item)

                            current_goal_block = self._goal_blocks[item_goal_index]
                            # If the item matches the current goal and the drop location matches the target location
                            if self._compare_blocks(item, current_goal_block) and item['location'] == current_goal_block[
                                'location']:
                                # set next goal as target, capping at the last
                                next_goal_index = self._target_goal_index + 1

                                if not next_goal_index > 2:
                                    self._target_goal_index = next_goal_index
                                    # and look for collectable goal item
                                    if self._checkForPossibleGoal():
                                        # drop everything we're doing now if it knows one exists
                                        return self._dropBlockIfCarrying()
                                else:
                                    # TODO liar liar
                                    pass

    def _updateTrustBelief(self, members, received) -> None:
        if members[0] not in self._trustBeliefs:
            self.__initTrust(members)

        # Keep track of all the updates
        updated_trust: list[str] = []

        for member in members:
            for message in received[member]:
                if 'Found' in message and '#00000' in message:
                    self._trustBeliefs[member] -= 0.1
                elif 'Found' in message:
                    item = self.__object_from_message(message)
                    index = self.__get_matching_goal_index(item)
                    if index < 0:
                        self._trustBeliefs[member] -= 0.1
                    else:
                        self._trustBeliefs[member] += 0.1
                if 'Opening' in message:
                    self._door_trust_positive(message, member)
                if 'Searching' in message:
                    self._door_trust(message, member)
                if 'Dropped' in message:
                    item = self.__object_from_message(message)
                    index = self.__get_matching_goal_index(item)
                    # This is just the messages receive by colorblind agent
                    if item['visualization']['colour'] == '#000000':
                        break
                    if index < 0:
                        self._trustBeliefs[member] -= 0.1
                    else:
                        self._trustBeliefs[member] += 0.1
                if 'trust' in message:
                    target_agent:str = message.split()[-1].strip()

                    if self._trustBeliefs[member] > 0.5:
                        if not self._agent_name == target_agent:
                            self._trustBeliefs[target_agent] -= .1

            clamped_trust: float = max(0.0, min(round(self._trustBeliefs[member], 1), 1.0))
            updated_trust.append(str(clamped_trust))

        # Update the agent's csv with the latest values
        read_path = 'agents1/trust_%s.csv' % str(self._agent_name)
        with open(read_path, 'a') as read_obj:
            csv_writer = writer(read_obj)
            csv_writer.writerow(updated_trust)

    def __initTrust(self, members, default=.5):
        # Open file or create a new one (one for each agent)
        write_path = 'agents1/trust_%s.csv' % str(self._agent_name)
        mode = 'r' if os.path.exists(write_path) else 'w'

        # Initialize values for self and for their file
        self._trustBeliefs = {}
        headers = []
        trust = []

        for member in members:
            headers.append(str(member))
            self._trustBeliefs[member] = default
            trust.append(self._trustBeliefs[member])
            self._trusting_agent[member] = True

        # If file doesn't exist, create and initialize it
        if mode == 'w':
            with open(write_path, mode) as file:
                w = csv.writer(file)
                w.writerow(headers)
                w.writerow(trust)

        # Otherwise, initiate the agent's trust to the last known trust value
        else:
            with open(write_path, mode) as file:
                trust: list[dict[str, str]] = list(csv.DictReader(file))

                for member in members:
                    self._trustBeliefs[member] = float(trust[-1][member])

                    if self._trustBeliefs[member] <= .2:
                        self._trusting_agent[member] = False

        print(self._trustBeliefs)

    # ==== UTILS ====

    def _repeat_then(self, repeats: int, nextPhase: Phase) -> None:
        if self._repeat_action == 0:
            self._repeat_action = repeats
            return

        if self._repeat_action > 0:
            self._repeat_action -= 1

        if self._repeat_action == 0:
            self._phase = nextPhase

    def _report_to_console(self, *args) -> None:
        print(self._agent_name, "reporting:", *args)

    def _object_as_shape(self, obj) -> str:
        if 'CollectableBlock' in obj['class_inheritance'] or 'GhostBlock' in obj['class_inheritance']:
            return obj['visualization']['colour'] + " " + str(obj['visualization']['shape'])
        else:
            return 'not a shape'

    def _init_goal_targets(self) -> None:
        temp = self._current_state.as_dict()

        # Get all the Collect_Blocks
        self._goal_blocks = [val for key, val in temp.items() if 'Collect_Block' in key]
        self._collectable_goal_blocks = [None] * len(self._goal_blocks)

    def _saveObjectsAround(self) -> None:
        objects: list[dict] | None = self._current_state.get_room_objects(self._door['room_name'])
        # TODO: if index doesn't equal current target goal index, drop off point should be around the goal
        if objects is None:
            return

        collectables: list[dict] = self._filter_collectables(objects)

        for collectable in collectables:
            if collectable not in self._collectables:
                self._collectables.append(collectable)

    def _check_collectables(self) -> tuple[list[dict], list[dict]]:
        target_blocks: list[dict] = []
        goal_blocks: list[dict] = []

        for block in self._collectables:
            for index, goal_block in enumerate(self._goal_blocks):
                if self._compare_blocks(block, goal_block):
                    if index == self._target_goal_index:
                        target_blocks.append(block)
                    else:
                        # If it's not an index-match, keep it in mind for later
                        # TODO maybe carry it close to the goal location?
                        if 'collectable_match' in goal_block:
                            goal_block['collectable_match'] = \
                                self.__return_closest_to(goal_block['collectable_match'], block, goal_block['location'])
                        else:
                            goal_block['collectable_match'] = block

                    # Not sure if this is the best solution, but this way it's quite simple to go
                    # from carrying an item to matching it to a goal
                    block['goal_index'] = index
                    goal_blocks.append(block)

        return target_blocks, goal_blocks

    def _check_for_duplicates(self) -> None:
        for i in range(len(self._target_items)):
            carrying = self._is_carrying
            for j in range(len(carrying)):
                if self._compare_blocks(self._target_items[i], carrying[j]):
                    del (self._target_items[i])

    def _compare_blocks(self, a, b) -> bool:
        return a['visualization']['colour'] == b['visualization']['colour'] and \
               a['visualization']['shape'] == b['visualization']['shape']

    def _check_for_current_target_goal(self) -> dict | None:
        if self._target_goal_index >= len(self._goal_blocks):
            return None

        current_goal = self._goal_blocks[self._target_goal_index]

        if 'collectable_match' in current_goal:
            return current_goal['collectable_match']
        else:
            return None

    def __get_matching_goal_index(self, item):
        for index, goal in enumerate(self._goal_blocks):
            if self._compare_blocks(goal, item):
                return index
        return -1

    def __object_from_message(self, message):
        location_string = str(re.findall(r'\(.*?\)', message)[0][1:-1])
        location = tuple(map(lambda e: int(e), location_string.split(", ")))
        found_object = re.findall(r'\{.*?\}', message)[0]
        colour = re.findall(r"'colour':\s'#\w+'", found_object)[0].split(": ")[-1][1:-1]
        shape = int(re.findall(r"\'shape\': \d+", found_object)[0].split(": ")[-1])

        return {
            "location": location,
            "visualization": {
                "colour": colour,
                "shape": shape
            },
        }

    def __check_item_and_add_if_goal(self, item: dict):
        old_collectables = self._collectables
        self._collectables = [item]
        self._check_collectables()
        self._collectables = old_collectables

    def __return_closest_to(self, a: dict, b: dict, location: tuple) -> dict:
        if self.__distance(a['location'], location) < self.__distance(b['location'], location):
            return a
        return b

    def _filter_collectables(self, objects):
        return list(filter(lambda e: 'CollectableBlock' in e['class_inheritance'], objects))

    def __distance(self, a: tuple, b: tuple) -> int:
        x_a, y_a = a
        x_b, y_b = b
        return abs(x_a - x_b) + abs(y_a - y_b)

    def _door_trust_positive(self, message, member):
        room_name = message.split()[-1]
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        closed_rooms = [door['room_name'] for door in all_doors if not door['is_open']]

        if room_name in closed_rooms:
            self._trustBeliefs[member] -= 0.1
        else:
            self._trustBeliefs[member] += 0.1

    def _door_trust(self, message, member):
        room_name = message.split()[-1]
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        closed_rooms = [door['room_name'] for door in all_doors if not door['is_open']]

        if room_name in closed_rooms:
            self._trustBeliefs[member] -= 0.1


class StrongAgent(CustomBaselineAgent):
    """
    Can carry two objects at the same time.

    """
    def __init__(self, settings):
        super().__init__(settings)
        self._capacity = 2

    def _saveObjectsAround(self) -> None:
        objects: list[dict] | None = self._current_state.get_room_objects(self._door['room_name'])
        # TODO: if index doesn't equal current target goal index, drop off point should be around the goal
        if objects is None:
            return

        collectables: list[dict] = self._filter_collectables(objects)

        for collectable in collectables:
            if collectable not in self._collectables and collectable not in self._is_carrying:
                self._collectables.append(collectable)

    def _getItemPhase(self) -> Action | None:
        if len(self._is_carrying) == self._capacity - 1:
            self._phase = Phase.PLAN_PATH_TO_GOAL
        elif (len(self._goal_blocks) - 1) == self._target_goal_index:
            self._phase = Phase.PLAN_PATH_TO_GOAL
        else:
            if len(self._target_items) > 1:
                dist: str = self.__get_distance()

                if dist == "goal":
                    self._phase = Phase.PLAN_PATH_TO_GOAL
                else:
                    self._phase = Phase.FOLLOW_PATH_TO_TARGET_ITEMS
            else:
                self._phase = Phase.ENTER_ROOM

        assert len(self._target_items) != 0

        if not self._checkTargetItemsIfHint():
            # Hint wasn't corrent
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            return

        self._is_carrying.append(self._target_items[0])
        self._target_items.clear()
        self._target_goal_index += 1

        self._sendMessage(
            'Picking up goal block ' + str(self._is_carrying[-1]['visualization']) + ' at location ' + str(
                self._is_carrying[-1]['location'])
        )

        temp: int = 0 if len(self._is_carrying) == 1 else 1

        return GrabObject.__name__, {'object_id': self._is_carrying[temp]['obj_id']}

    def _planPathToGoalPhase(self) -> Action | None:
        # Could possibly be done a bit more elegantly
        target_locations: list[str] = self.__get_target_loc(self._is_carrying[0])

        if len(self._is_carrying) == 0:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            # TODO: Restore this by going through all the items that are not goals and removing them?
            return

        else:  # Drop off goal object to its correct location
            self._navigator.reset_full()
            self._navigator.add_waypoints([target_locations])
            self._phase = Phase.FOLLOW_PATH_TO_GOAL

    def _followPathToGoalPhase(self) -> Action | None:
        # TODO: Check if goal object has already been placed,
        #  there are multiple of the same shapes that match the goals
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        # Reverse the list because the agent picks up the items in order of goal
        self._is_carrying.reverse()

        block: dict = self._is_carrying.pop()

        if block is None:
            self._phase = Phase.PLAN_PATH_TO_TARGET_ITEMS

        if len(self._is_carrying) == 0:
            # TODO Should also be dependent on whether a message is sent
            if self._checkForPossibleGoal():
                self._phase = Phase.PLAN_PATH_TO_TARGET_ITEMS
            else:
                self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

        elif len(self._is_carrying) == 1:
            target_loc: list[str] = self.__get_target_loc(self._is_carrying[0])

            self._navigator.reset_full()
            self._navigator.add_waypoints([target_loc])
            self._phase = Phase.PLAN_PATH_TO_GOAL
        else:
            if not self._checkForPossibleGoal():
                self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

        loc = self._current_state[self.agent_id]['location']

        self._sendMessage(
            'Dropped goal block ' + str(block['visualization']) + ' at drop location ' + str(loc))

        return DropObject.__name__, {'object_id': block['obj_id']}

    def __get_target_loc(self, block) -> tuple|None:
        for goal_block in self._goal_blocks:
            if self._compare_blocks(block, goal_block):
                return goal_block['location']

    def __in_block_list(self, item, block_list) -> bool:
        for other in block_list:
            if self._compare_blocks(item, other):
                return True
        return False

    def __get_distance(self) -> str:
        self_loc: list[str] = self._current_state[self.agent_id]['location']
        goal_loc: list[str] = self.__get_target_loc(self._is_carrying[0])

        next_loc: list[str] = self.get_current_waypoint()

        dist_goal = math.sqrt(((self_loc[0] - goal_loc[0]) ** 2) + ((self_loc[1] - goal_loc[1]) ** 2))

        dist_next = math.sqrt(((self_loc[0] - next_loc[0]) ** 2) + ((self_loc[1] - next_loc[1]) ** 2))

        if dist_goal < dist_next:
            return "goal"
        else:
            return "next"

class LiarAgent(CustomBaselineAgent):
    """
    Information sharing does not always match actions and/or observations. For example, the agent can
    lie about which area an agent is moving to or where it found a goal block. Implement this agent to lie
    about actions and/or observations 80% of the time.
    """

    def __init__(self, settings):
        super().__init__(settings)

    def _sendMessage(self, mssg) -> None:
        """
        Enable sending falsified messages 80% of the time
        """
        rand: int = self.__get_number()
        if rand == 1:
            temp1 = self.__replace_color(mssg)
            temp2 = self.__replace_room(temp1)
            temp3 = self.__replace_location(temp2)

            msg = Message(content=temp3, from_id=self._agent_name)

            if msg.content not in self.received_messages:
                self.send_message(msg)
        else:
            msg = Message(content=mssg, from_id=self._agent_name)
            if msg.content not in self.received_messages:
                self.send_message(msg)

    def __get_number(self) -> int:
        """
        Generate 1 80% of the time
        """
        if random.random() <= 0.8:
            return 1
        else:
            return 0

    def __get_random_color(self) -> str:
        """
        Generate a random Hex color & replace in string
        """
        temp: str = "'#%02x%02x%02x'" % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        return "'colour': " + temp

    def __get_random_room(self) -> str:
        """
        Generate a random room & replace in string
        """
        # TODO (maybe): Ensure that the chosen door isn't the door it is already headed to
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        door = random.choice(all_doors)
        return door['room_name']

    def __get_random_location(self) -> str:
        """
        Generate a random location & replace in string
        """
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        door = random.choice(all_doors)
        return str(door['location'])

    def __replace_color(self, msg:str) -> str:
        """
        Check if the message contains a color
        """
        color = re.compile(r"'colour':\s'#(?:[0-9a-f]{3}){1,2}\b'")
        if color.search(msg):
            rand_color = self.__get_random_color()
            temp: str = re.sub(color, rand_color, msg)
            return temp
        else:
            return msg

    def __replace_room(self, msg:str) -> str:
        """
        Check if the message contains a room name
        """
        room = re.compile(r'room_\d')
        if room.search(msg):
            rand_room = self.__get_random_room()
            temp: str = re.sub(room, rand_room, msg)
            return temp
        else:
            return msg

    def __replace_location(self, msg: str) -> str:
        """
        Check if the message contains a location
        """
        location = re.compile(r'\([0-9]+,\s[0-9]+\)')
        if location.search(msg):
            rand_loc = self.__get_random_location()
            temp: str = re.sub(location, rand_loc, msg)
            return temp
        else:
            return msg

class LazyAgent(CustomBaselineAgent):
    """
    Less willing to use energy and thus sometimes stops what it is doing. This agent does not complete the
    action they say they will do 50% of the time, and start another task/action instead (and communicate
    this new action, therefore they do not lie). For example, this agent may stop searching room X after
    a few moves, and move to another room instead.
    """
    def __init__(self, settings):
        super().__init__(settings)

    def _openDoorPhase(self) -> Action | None:
        """
        Opens doors 50% of the time.
        """
        flaky = self._be_flaky()
        if flaky is not None:
            return flaky

        return super()._openDoorPhase()

    def _followRoomCheckPhase(self) -> Action | None:
        """
        Follows room checks 50% of the time.
        """
        flaky = self._be_flaky()
        if flaky is not None:
            self._collectables.clear()
            return flaky

        return super()._followRoomCheckPhase()

    def _getItemPhase(self) -> Action | None:
        """
        Gets items 50% of the time
        """
        flaky = self._be_flaky()
        if flaky is not None:
            return flaky

        return super()._getItemPhase()

    def _followPathToGoalPhase(self) -> Action | None:
        """
        Follows path to the goal 50% of the time.
        """
        # TODO gets stuck in a loop
        # flaky = self._be_flaky()
        # if flaky is not None:
        #     self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        #     return flaky

        return super()._followPathToGoalPhase()

    def _be_flaky(self) -> Action | None:
        """
        Will stop doing whatever it is doing and default back to PLAN_PATH_TO_CLOSED_DOOR
        drops an object if it has one.
        """
        if random.random() <= 0.5:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            return self._dropBlockIfCarrying(check_for_goal=False)
        return None

class ColorblindAgent(CustomBaselineAgent):
    """
    Cannot see colors.
    """
    def __init__(self, settings):
        super().__init__(settings)

    def _planPathToClosedDoorPhase(self) -> Action | None:
        self._navigator.reset_full()
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        closed_doors = [door for door in all_doors if not door['is_open']]

        # TODO maybe separate state?
        if len(closed_doors) == 0:
            self._door = random.choice(all_doors)
        else:
            self._door = random.choice(closed_doors)

        door_loc = self._door['location']
        # Location in front of door is south from door
        door_loc = door_loc[0], door_loc[1] + 1

        # Send message of current action
        self._sendMessage('Moving to ' + self._door['room_name'])
        self._navigator.add_waypoints([door_loc])

        self._phase = Phase.FOLLOW_PATH_TO_CLOSED_DOOR

    def _openDoorPhase(self) -> Action | None:
        """
        Has agent continue opening the doors
        """
        self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        self._sendMessage('Opening door of ' + self._door['room_name'])

        # Open door
        return OpenDoorAction.__name__, {'object_id': self._door['obj_id']}

    def _processMessages(self, teamMembers) -> dict:
        """
        Process incoming messages by filtering out the color and create a dictionary with received messages
        from each team member.
        """
        receivedMessages = {}
        for member in teamMembers:
            receivedMessages[member] = []

        # Remove color from the ColorblindAgent's received messages
        if len(self.received_messages) > 0:
            self.__filter_messages(self.received_messages)

        for mssg in self.received_messages:
            for member in teamMembers:
                if mssg.from_id == member:
                    receivedMessages[member].append(mssg.content)
        return receivedMessages

    def __filter_messages(self, strings) -> list[str]:
        """
        Replace any instance of colour in the message with black
        """
        color = re.compile(r"'colour':.*?,")
        for i in range(len(strings)):
            msg: str = strings[i].content
            if color.search(msg):
                temp: str = re.sub(color, "'colour': '#000000',", msg)
                strings[i].content = temp

        return strings
