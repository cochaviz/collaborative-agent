import csv
import os
from _csv import writer
from typing import Callable, Dict, Optional
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
        self._trusting_agent: str = ""
        self._trustBeliefs: dict = {}

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

    def filter_observations(self, state: State) -> State:
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
        self._memorize(self._teamMembers, received_messages)

        while True:
            assert self._phase is not None
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

        # if target item is only a hint by another agent
        if not 'obj_id' in self._target_items[0]:
            close_items = self._current_state.get_objects_in_area(
                top_left=self._current_state[self.agent_id]['location'], width=1, height=1)
            close_collectables = self._filter_collectables(close_items)

            # check if the item under you matches the description
            if len(close_collectables) > 0 and self._compare_blocks(self._target_items[0], close_collectables[0]):
                self._target_items[0]['obj_id'] = close_collectables[0]['obj_id']
            else:
                # if not the case, remove current item as considerable goal collectable match for goal object
                self._goal_blocks[self._target_items[0]['goal_index']].pop('collectable_match')
                self._target_items.clear()
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

    def _memorize(self, member, received) -> Action | None:
        for member in received.keys():
            for message in received[member]:
                if True or member != self.agent_id:
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
        temp: list[str] = []

        for member in members:
            for message in received[member]:
                if 'Found' in message and '#00000' in message:
                    self._trustBeliefs[member] -= 0.1
                if 'Opening' in message:
                    room_name = message.split()[-1]
                    all_doors = [door for door in self._current_state.values()
                                 if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
                    closed_rooms = [door['room_name'] for door in all_doors if not door['is_open']]

                    if room_name in closed_rooms:
                        self._trustBeliefs[member] -= 0.1
                if 'Dropped' in message:
                    item = self.__object_from_message(message)
                    count: int = 0
                    for location in self._target_items:
                        self._report_to_console("Location: " + str(location['location']))
                        self._report_to_console("Said loc: " + str(item['location']))
                        if item['location'] == location['location']:
                            count += 1
                    if count == 1:
                        self._trustBeliefs[member] += 0.2
                    else:
                        self._trustBeliefs[member] -= 0.3

            temp.append(round(self._trustBeliefs[member], 2))

        # Update the agent's csv with the latest values
        read_path = 'agents1/trust_%s.csv' % str(self._agent_name)
        with open(read_path, 'a') as read_obj:
            csv_writer = writer(read_obj)
            csv_writer.writerow(temp)

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

        # If file doesn't exist, create and initialize it
        if mode == 'w':
            with open(write_path, mode) as t:
                w = csv.writer(t)
                w.writerow(headers)
                w.writerow(trust)
            t.close()

        # Otherwise, initiate the agent's trust to the last known trust value
        else:
            with open(write_path, mode) as t:
                final_line = t.readlines()[-1].strip().split(',')
                t.seek(0)
                first_line = t.readlines()[0].strip().split(',')
                trust_dict = dict(zip(first_line, final_line))
                print(str(trust_dict))
                for member in members:
                    self._trustBeliefs[member] = float(trust_dict[member])

            t.close()

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
