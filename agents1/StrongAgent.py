import math

from matrx.actions import GrabObject, DropObject

from agents1.CustomBaselineAgent import CustomBaselineAgent, Action, Phase


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
                    self._report_to_console("Closer")
                    self._phase = Phase.PLAN_PATH_TO_GOAL
                else:
                    self._phase = Phase.FOLLOW_PATH_TO_TARGET_ITEMS
            else:
                self._phase = Phase.ENTER_ROOM

        assert len(self._target_items) != 0

        self._is_carrying.append(self._target_items[0])
        self._target_items.clear()
        self._target_goal_index += 1

        self._sendMessage(
            'Picking up goal block ' + str(self._is_carrying[-1]['visualization']) + ' at location ' + str(
                self._is_carrying[-1]['location'])
        )

        temp: int = 0 if len(self._is_carrying) == 1 else 1
        self._report_to_console("Carrying: " + str(self._is_carrying[temp]['obj_id']))

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
