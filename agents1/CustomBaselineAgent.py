from typing import Callable, Dict
import enum, random

from matrx.actions.move_actions import MoveNorth

from bw4t.BW4TBlocks import GhostBlock
from bw4t.BW4TBrain import BW4TBrain
from matrx.agents.agent_utils.state import State
from matrx.agents.agent_utils.navigator import Navigator
from matrx.agents.agent_utils.state_tracker import StateTracker
from matrx.actions.door_actions import OpenDoorAction
from matrx.messages.message import Message

class Phase(enum.Enum):
    PLAN_PATH_TO_CLOSED_DOOR=1,
    FOLLOW_PATH_TO_CLOSED_DOOR=2,
    OPEN_DOOR=3
    ENTER_ROOM=4

    PLAN_PATH_TO_CLOSE_ITEMS=5
    FOLLOW_PATH_TO_CLOSE_ITEMS=6
    GET_ITEM=7

    PLAN_PATH_TO_GOAL=8
    FOLLOW_PATH_TO_GOAL=8

class CustomBaselineAgent(BW4TBrain):
    """
    Agent that contains all non-agent specific logic
    """
    def __init__(self, settings:Dict[str,object]):
        super().__init__(settings)
        self._phase: Phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        self._teamMembers = []

        self._agent_name: None|str = None
        self._goal_objects: list[GhostBlock] = []

        self._current_state: State
        self._repeat_action: int = 0

        self._switchPhase: dict[Phase, Callable[[], tuple|None]] = {
            Phase.PLAN_PATH_TO_CLOSED_DOOR: self._planPathToClosedDoorPhase,
            Phase.FOLLOW_PATH_TO_CLOSED_DOOR: self._followPathToClosedDoorPhase,
            Phase.OPEN_DOOR: self._openDoorPhase,
            Phase.ENTER_ROOM: self._enterRoomPhase,

            Phase.PLAN_PATH_TO_CLOSE_ITEMS: self._planPathToCloseItemsPhase,
            Phase.FOLLOW_PATH_TO_CLOSE_ITEMS: self._followPathToCloseItemsPhase,
            Phase.GET_ITEM: self._getItemPhase,

            Phase.PLAN_PATH_TO_GOAL: self._planPathToGoalPhase,
            Phase.FOLLOW_PATH_TO_GOAL: self._followPathToGoalPhase,
        }

    def initialize(self) -> None:
        super().initialize()
        self._state_tracker = StateTracker(agent_id=self.agent_id)
        self._navigator = Navigator(agent_id=self.agent_id, 
            action_set=self.action_set, algorithm=Navigator.A_STAR_ALGORITHM)

    def filter_observations(self, state) -> State:
        return state

    def decide_on_bw4t_action(self, state:State) -> tuple[str, dict]:
        assert state is not None

        self._current_state = state
        self._agent_name = self._current_state[self.agent_id]['obj_id']

        # Add team members
        for member in self._current_state['World']['team_members']:
            if member!=self._agent_name and member not in self._teamMembers:
                self._teamMembers.append(member)

        # Process messages from team members
        receivedMessages = self._processMessages(self._teamMembers)

        # Update trust beliefs for team members
        self._trustBlief(self._teamMembers, receivedMessages)
        
        while True:
            actionAndSubject = self._switchPhase[self._phase]()

            if actionAndSubject is not None and actionAndSubject[0] is not None:
                return actionAndSubject

    # ==== PHASE ====

    def _planPathToClosedDoorPhase(self) -> tuple|None:
        self._navigator.reset_full()

        closedDoors = [door for door in self._current_state.values()
            if 'class_inheritance' in door and 'Door' in door['class_inheritance'] and not door['is_open']]

        if len(closedDoors)==0:
            return None, {}

        # Randomly pick a closed door
        self._door = random.choice(closedDoors)
        doorLoc = self._door['location']

        # Location in front of door is south from door
        doorLoc = doorLoc[0],doorLoc[1]+1

        # Send message of current action
        self._sendMessage('Moving to door of ' + self._door['room_name'])
        self._navigator.add_waypoints([doorLoc])

        self._phase=Phase.FOLLOW_PATH_TO_CLOSED_DOOR

    def _followPathToClosedDoorPhase(self) -> tuple|None:
        self._state_tracker.update(self._current_state)

        # Follow path to door
        action = self._navigator.get_move_action(self._state_tracker)

        if action!=None:
            return action, {}

        self._phase=Phase.OPEN_DOOR

    def _openDoorPhase(self) -> tuple|None:
        self._phase=Phase.ENTER_ROOM

        # Open door
        return OpenDoorAction.__name__, {'object_id':self._door['obj_id']}

    def _enterRoomPhase(self) -> tuple|None:
        self._sendMessage("Trying to enter room")
        self._repeat_then(1, Phase.PLAN_PATH_TO_CLOSE_ITEMS)

        return MoveNorth.__name__, {}

    def _planPathToCloseItemsPhase(self) -> tuple|None:
        self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

    def _followPathToCloseItemsPhase(self) -> tuple|None:
        pass

    def _getItemPhase(self) -> tuple|None:
        pass

    def _planPathToGoalPhase(self) -> tuple|None:
        pass

    def _followPathToGoalPhase(self) -> tuple|None:
        pass


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

    def _trustBlief(self, member, received) -> dict:
        '''
        Baseline implementation of a trust belief. Creates a dictionary with trust belief scores for each team member, for example based on the received messages.
        '''
        # You can change the default value to your preference
        default = 0.5
        trustBeliefs = {}
        for member in received.keys():
            trustBeliefs[member] = default
        for member in received.keys():
            for message in received[member]:
                if 'Found' in message and 'colour' not in message:
                    trustBeliefs[member]-=0.1
                    break
        return trustBeliefs

    # ==== UTILS ====
    #
    def _repeat_then(self, repeats: int, nextPhase: Phase) -> None:
        if self._repeat_action == 0:
            self._repeat_action = repeats
            return

        if self._repeat_action > 0:
            self._repeat_action -= 1

        if self._repeat_action == 0:
            self._phase = nextPhase

    def _report_to_console(self, args):
        print(self._agent_name," reporting:", **args)
