from matrx.actions.object_actions import GrabObject
from agents1.CustomBaselineAgent import Action, CustomBaselineAgent, Phase

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

        if objects is None:
            # TODO Use correct format
            self._report_to_console("Can't find any objects in " + self._door['room_name'])
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            return

        collectables: list[dict] = list(filter(lambda e: 'CollectableBlock' in e['class_inheritance'], objects))

        for collectable in collectables:
            if collectable not in self._collectables:
                self._collectables.append(collectable)

        if len(self._collectables) == 0:
            self._report_to_console("Can't find any collectable objects")
            self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
            return

        self._report_to_console("Found collectable objects:", collectables)
        self._report_to_console("Getting the following object:", self._collectables[0])

        self._navigator.reset_full()
        self._report_to_console("Going to object location:", self._collectables[0]['location'])
        self._navigator.add_waypoints([self._collectables[0]['location']])
        self._phase = Phase.FOLLOW_PATH_TO_CLOSE_ITEMS

    def _followPathToCloseItemsPhase(self) -> Action|None:
        self._state_tracker.update(self._current_state)

        action = self._navigator.get_move_action(self._state_tracker)

        if action is not None:
            return action, {}

        if len(self._collectables) == 0:
            self._phase = Phase.FOLLOW_PATH_TO_CLOSED_DOOR
        else:
            self._report_to_console("Grabbing item from:", len(self._collectables))
            self._phase = Phase.GET_ITEM

    def _getItemPhase(self) -> Action | None:
        self._phase = Phase.FOLLOW_PATH_TO_CLOSE_ITEMS
        self._report_to_console("--> 1 Current items:", self._collectables)
        item: dict = self._collectables.pop()
        self._report_to_console("--> 2 Current items:", self._collectables)
        return GrabObject.__name__, {'object_id':item['obj_id']}
