from agents1.CustomBaselineAgent import Action, CustomBaselineAgent, Phase

from matrx.grid_world import GridWorld

from bw4t.BW4TBlocks import GhostBlock

class StrongAgent(CustomBaselineAgent):
    """
    Can carry two objects at the same time.

    TODO Implement described behavior
    """
    def __init__(self, settings):
        super().__init__(settings)

    # ==== PHASE FUNCTIONS ====

    def _planPathToCloseItemsPhase(self) -> Action|None:
        objects: list[dict]|None = self._current_state.get_room_objects(self._door['room_name'])

        if objects is None or len(objects) == 0:
            # TODO Use correct format
            self._sendMessage("Can't find any objects in " + self._door['room_name'])
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        else:
            print("Tracking objects...", objects)
            collectable: list[dict] = list(filter(lambda e: 'CollectableBlock' in e['class_inheritance'], objects))
            print("Found collectable objects:", collectable)

            self._navigator.add_waypoints(map(lambda e: e['location'], collectable))
            self._phase = Phase.FOLLOW_PATH_TO_CLOSE_ITEMS

    def _followPathToCloseItemsPhase(self) -> Action|None:
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        self._phase = Phase.GET_ITEM
