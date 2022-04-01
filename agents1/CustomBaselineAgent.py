from typing import Callable, Dict, Optional
import enum, random
import json
import random
import re
from os.path import exists

from matrx.actions.move_actions import MoveNorth
from matrx.actions.object_actions import GrabObject, DropObject, RemoveObject

from bw4t.BW4TBrain import BW4TBrain
from matrx.agents.agent_utils.state import State
from matrx.agents.agent_utils.navigator import Navigator
from matrx.agents.agent_utils.state_tracker import StateTracker
from matrx.actions.door_actions import OpenDoorAction
from matrx.messages.message import Message

Action = tuple[str, dict] | None

class Phase(enum.Enum):
    PLAN_PATH_TO_CLOSED_DOOR=1,
    FOLLOW_PATH_TO_CLOSED_DOOR=2,
    OPEN_DOOR=3

    ENTER_ROOM=4
    PLAN_ROOM_CHECK=10
    FOLLOW_ROOM_CHECK=11

    PLAN_PATH_TO_TARGET_ITEMS=5
    FOLLOW_PATH_TO_TARGET_ITEMS=6
    GET_ITEM=7

    PLAN_PATH_TO_GOAL = 8
    FOLLOW_PATH_TO_GOAL = 9

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

        self._goal_blocks: list[dict] = []

        # dropping items on the goals has to go in the right order
        # this corresponds to a goal in the self._goal_blocks attribute
        self._target_goal_index: int = 0

        # is true when acting on second-hand information
        self._acting_on_trust: bool = False
        self._trusting_agent: str = ""

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
            self.__init_goal_targets()

        # Add team members
        for member in self._current_state['World']['team_members']:
            if member != self._agent_name and member not in self._teamMembers:
                self._teamMembers.append(member)

        # Process messages from team members
        received_messages = self._processMessages(self._teamMembers)

        # Update trust beliefs for team members
        self._trustBlief(self._teamMembers, received_messages)
        self._memorize(self._teamMembers, received_messages)

        while True:
            assert self._phase is not None
            action_and_subject = self._switchPhase[self._phase]()

            if action_and_subject is not None and action_and_subject[0] is not None:
                return action_and_subject

    # ==== DOOR PHASE ====

    def _planPathToClosedDoorPhase(self) -> Action | None:
        # TODO: If all doors are open then send agent elsewhere?
        self._navigator.reset_full()
        all_doors = [ door for door in self._current_state.values()
                                if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        closed_doors = [door for door in all_doors if not door['is_open']]

        # TODO maybe separate state?
        if len(closed_doors) == 0:
            if self._checkForPossibleGoal():
                return None
            self._door = random.choice(all_doors)
        else:
            self._door = random.choice(closed_doors)

        # Randomly pick a closed door
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

    def _planRoomCheckPhase(self) -> Action|None:
        current_x, current_y = self._current_state[self.agent_id]['location']
        next_locations: list[tuple[int, int]] = \
            [(current_x, current_y-1), (current_x-1, current_y-1), (current_x-1, current_y)]

        self._navigator.reset_full()
        self._navigator.add_waypoints(next_locations)
        self._phase = Phase.FOLLOW_ROOM_CHECK

    def _followRoomCheckPhase(self) -> Action|None:
        self._sendMessage('Searching through ' + self._door['room_name'])
        self.__saveObjectsAround()

        self._state_tracker.update(self._current_state)
        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        if len(self._collectables) == 0:
            self._target_items.clear()
        else:
            goal_target_items, all_found_goal_items = self.__check_collectables()
            for goal in all_found_goal_items:
                self._sendMessage('Found goal block ' + str(goal['visualization']) + ' at location ' + str(goal['location']))

            # This way, the StrongAgent can just pick up all goal objects it encounters
            self._target_items = goal_target_items[0:self._capacity]
            self._collectables.clear()

        self._phase = Phase.PLAN_PATH_TO_TARGET_ITEMS

    def _planPathToTargetItemsPhase(self) -> Action|None:
        if len(self._target_items) == 0:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            return

        self._navigator.reset_full()
        # TODO: Might want to go through over all target_items, for now just visit one
        self._navigator.add_waypoints([self._target_items[0]['location']])
        self._phase = Phase.FOLLOW_PATH_TO_TARGET_ITEMS

    def _followPathToTargetItemsPhase(self) -> Action|None:
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        if len(self._target_items) == 0:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        else:
            self._phase = Phase.GET_ITEM

    def _getItemPhase(self) -> Action | None:
        # TODO probably doesn't need to be its own phase
        # Should never happen since immediately when picking up something, continue to drop off at goal
        if len(self._is_carrying) == self._capacity:
            self._phase = Phase.PLAN_PATH_TO_GOAL

        self._phase = Phase.PLAN_PATH_TO_GOAL

        # if target item is only a hint by another agent
        if not 'obj_id' in self._target_items[0]:
            self._report_to_console("cannot find object id")
            close_items = self._current_state.get_objects_in_area(top_left=self._current_state[self.agent_id]['location'], width=1, height=1)
            close_collectables = self.__filter_collectables(close_items)

            # check if the item under you matches the description
            if len(close_collectables) > 0 and self.__compare_blocks(self._target_items[0], close_collectables[0]):
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
            'Picking up goal block ' + str(self._is_carrying[-1]['visualization']) + ' at location ' + str(self._is_carrying[-1][
                'location']))

        # TODO Check if successfull
        return GrabObject.__name__, {'object_id':self._is_carrying[-1]['obj_id']}

    # ==== GOAL PHASE ====

    def _planPathToGoalPhase(self) -> Action | None:
        # Could possibly be done a bit more elegantly
        target_locations: list[tuple] = \
            map(lambda e: self._goal_blocks[e['goal_index']]['location'], self._is_carrying)

        # Not sure if this is okay, but if the agent is carrying an object that isn't a
        # goal object, then we remove it
        if len(self._is_carrying) == 0:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            # TODO: Restore this by going through all the items that are not goals and removing them?
            return

        else:  # Drop off goal object to its correct location
            self._navigator.reset_full()
            self._navigator.add_waypoints(target_locations)
            self._phase = Phase.FOLLOW_PATH_TO_GOAL

    def _followPathToGoalPhase(self) -> Action | None:
        # TODO: Check if goal object has already been placed,
        #  there are multiple of the same shapes that match the goals
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        self._target_goal_index += 1
        return self._dropBlockIfCarrying()

    def _dropBlockIfCarrying(self) -> Action | None:
        if len(self._is_carrying) == 0 :
           return None

        block: dict = self._is_carrying.pop()
        current_location: tuple = self._current_state[self.agent_id]['location']

        self._sendMessage(
            'Dropped goal block ' + str(block['visualization']) + ' at drop location ' + str(current_location))

        if not self._checkForPossibleGoal():
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

        return DropObject.__name__, {'object_id': block['obj_id']}


    def _checkForPossibleGoal(self, set_target_and_phase:bool=True) -> bool:
        match = self.__check_for_current_target_goal()

        if match is not None:
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

    def _memorize(self, member, received) -> None:
        for member in received.keys():
            for message in received[member]:
                if 'Found' in message:
                    item = self.__object_from_message(message)
                    old_collectables = self._collectables
                    self._collectables = [item]
                    self.__check_collectables()
                    self._collectables = old_collectables
                if 'Dropped' in message:
                    item = self.__object_from_message(message)
                    current_goal_block = self._goal_blocks[self._target_goal_index]

                    # If the item matches the current goal and the drop location matches the target location
                    if self.__compare_blocks(item, current_goal_block) and item['location'] == current_goal_block['location']:
                        # set next goal as target
                        self._target_goal_index += 1
                        # and look for collectable goal item
                        if self._checkForPossibleGoal():
                            # drop everything we're doing now if it we know one exists
                            # TODO might wanna literally drop an object if we're already carrying one?
                            return self._dropBlockIfCarrying()

    def _trustBlief(self, member, received) -> dict:
        '''
        Baseline implementation of a trust belief. Creates a dictionary with trust belief scores for each team member, for example based on the received messages.
        '''
        # You can change the default value to your preference
        default = 0.5
        # TODO Should be done upon init and be a property
        trustBeliefs = {}
        for member in received.keys():
            trustBeliefs[member] = default
        for member in received.keys():
            for message in received[member]:
                if 'Found' in message and 'colour' not in message:
                    trustBeliefs[member] -= 0.1
                    break
                if 'Opening' in message:
                    room_name = message.split()[-1]
                    all_doors = [ door for door in self._current_state.values()
                                            if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
                    closed_rooms = [door['room_name'] for door in all_doors if not door['is_open']]

                    if room_name in closed_rooms:
                        trustBeliefs[member] -=0.1
                        self._report_to_console("trust", trustBeliefs)


        return trustBeliefs

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

    def __init_goal_targets(self) -> None:
        temp = self._current_state.as_dict()

        # Get all the Collect_Blocks
        self._goal_blocks = [val for key, val in temp.items() if 'Collect_Block' in key]
        self._collectable_goal_blocks = [None] * len(self._goal_blocks)

    def __saveObjectsAround(self) -> None:
        objects: list[dict]|None = self._current_state.get_room_objects(self._door['room_name'])
          # TODO if index doesn't equal current target goal index, drop off point should be around the goal
        if objects is None:
            return

        collectables: list[dict] = self.__filter_collectables(objects)

        for collectable in collectables:
            if collectable not in self._collectables:
                self._collectables.append(collectable)

    def __check_collectables(self) -> tuple[list[dict], list[dict]]:
        target_blocks: list[dict] = []
        goal_blocks: list[dict] = []

        for block in self._collectables:
            for index, goal_block in enumerate(self._goal_blocks):
                if self.__compare_blocks(block, goal_block):
                    if index == self._target_goal_index:
                        target_blocks.append(block)
                    else:
                        # If it's not an index-match, keep it in mind for later
                        # TODO maybe carry it close to the goal location?
                        goal_block['collectable_match'] = block

                    # Not sure if this is best solution, but this way it's quite simple to go
                    # from carrying an item to matching it to a goal
                    block['goal_index'] = index
                    goal_blocks.append(block)

        return target_blocks, goal_blocks

    def __compare_blocks(self, a, b) -> bool:
        return a['visualization']['colour'] == b['visualization']['colour'] and \
                    a['visualization']['shape'] == b['visualization']['shape']

    def __check_for_current_target_goal(self) -> dict|None:
        if self._target_goal_index >= len(self._goal_blocks):
            return None

        current_goal = self._goal_blocks[self._target_goal_index]

        if 'collectable_match' in current_goal:
            return current_goal['collectable_match']
        else:
            return None

    def __object_from_message(self, message):
        location_string = str(re.findall(r'\(.*?\)', message)[0][1:-1])
        location = tuple(map(lambda e: int(e), location_string.split(", ")))
        found_object = re.findall(r'\{.*?\}', message)[0]
        colour = re.findall("'colour': '#\w+'", found_object)[0].split(": ")[-1][1:-1]
        shape = int(re.findall("\'shape\': \d+", found_object)[0].split(": ")[-1])

        return {
            "location": location,
            "visualization": {
                "colour": colour,
                "shape": shape
                },
            }

    def __filter_collectables(self, objects):
        return list(filter(lambda e: 'CollectableBlock' in e['class_inheritance'], objects))
