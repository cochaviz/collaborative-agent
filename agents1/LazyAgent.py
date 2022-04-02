from __future__ import annotations

from matrx.actions import OpenDoorAction, GrabObject, DropObject

from agents1.CustomBaselineAgent import CustomBaselineAgent, Phase, Action

import random


class LazyAgent(CustomBaselineAgent):
    """
    Less willing to use energy and thus sometimes stops what it is doing. This agent does not complete the
    action they say they will do 50% of the time, and start another task/action instead (and communicate
    this new action, therefore they do not lie). For example, this agent may stop searching room X after
    a few moves, and move to another room instead.

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
            if self._checkForPossibleGoalElse():
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

        if self.__get_number() == 1:
            self._phase = Phase.FOLLOW_PATH_TO_CLOSED_DOOR
        else:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

    def _openDoorPhase(self) -> Action | None:
        self._sendMessage('Opening door of ' + self._door['room_name'])
        self._phase = Phase.ENTER_ROOM

        # Open door
        return OpenDoorAction.__name__, {'object_id': self._door['obj_id']}

    def _followRoomCheckPhase(self) -> Action | None:
        self._sendMessage('Searching through ' + self._door['room_name'])
        self._saveObjectsAround()

        self._state_tracker.update(self._current_state)
        action = self._navigator.get_move_action(self._state_tracker)

        # Quits an action early
        if self.__get_number() == 1:
            if action is not None:
                return action, {}
        else:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

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

    def _getItemPhase(self) -> Action | None:
        # TODO: probably doesn't need to be its own phase
        self._phase = Phase.PLAN_PATH_TO_GOAL

        assert len(self._target_items) != 0

        self._is_carrying.append(self._target_items[0])
        self._target_items.clear()

        self._sendMessage(
            'Picking up goal block ' + str(self._is_carrying[-1]['visualization']) + ' at location ' + str(
                self._is_carrying[-1][
                    'location'])
        )

        if self.__get_number() == 1:
            return GrabObject.__name__, {'object_id': self._is_carrying[0]['obj_id']}
        else:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

    def _followPathToGoalPhase(self) -> Action | None:
        # TODO: Check if goal object has already been placed,
        #  there are multiple of the same shapes that match the goals
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        block: dict = self._is_carrying.pop()

        # TODO Should also be dependent on whether a message is sent
        self._checkForPossibleGoalElse(Phase.PLAN_PATH_TO_CLOSED_DOOR)

        loc = self._current_state[self.agent_id]['location']
        self._sendMessage(
            'Dropped goal block ' + str(block['visualization']) + ' at drop location ' + str(loc))

        if self.__get_number() == 1:
            return DropObject.__name__, {'object_id': block['obj_id']}
        else:
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

    def __get_number(self) -> int:
        """
        Generate 1 50% of the time
        """
        if random.random() <= 0.5:
            return 1
        else:
            return 0
