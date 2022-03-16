from agents1.CustomBaselineAgent import CustomBaselineAgent, Phase

class StrongAgent(CustomBaselineAgent):
    """
    Can carry two objects at the same time.

    TODO Implement described behavior
    """
    def __init__(self, settings):
        super().__init__(settings)

    # ==== PHASE FUNCTIONS ====

    def _planPathToCloseItemsPhase(self) -> tuple|None:
        objects = self._current_state.get_closest_objects()

        if objects is None or len(objects) == 0:
            self._sendMessage("Can't find any objects in " + self._door['room_name'])
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        else:
            print("Tracking objects...")
            self._navigator.add_waypoints(map(lambda e: e['location'], objects))
            self._phase = Phase.FOLLOW_PATH_TO_CLOSE_ITEMS

    def _followPathToCloseItemsPhase(self) -> tuple | None:
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        self._phase = Phase.GET_ITEM
