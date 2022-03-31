from __future__ import annotations

from matrx.actions import GrabObject

from agents1.CustomBaselineAgent import CustomBaselineAgent, Action, Phase


class StrongAgent(CustomBaselineAgent):
    """
    Can carry two objects at the same time.

    """
    def __init__(self, settings):
        super().__init__(settings)
        self._capacity = 2

    def _getItemPhase(self) -> Action | None:
        if len(self._is_carrying) + 1 == self._capacity:
            self._phase = Phase.PLAN_PATH_TO_GOAL
        else:
            if len(self._target_items) > 1:
                self._phase = Phase.FOLLOW_PATH_TO_TARGET_ITEMS
            else:
                self._phase = Phase.ENTER_ROOM

        assert len(self._target_items) != 0

        self._is_carrying.append(self._target_items[0])
        self._target_items.clear()

        self._sendMessage(
            'Picking up goal block ' + str(self._is_carrying[-1]['visualization']) + ' at location ' + str(
                self._is_carrying[-1]['location'])
        )

        temp: int = self._target_goal_index - 1

        return GrabObject.__name__, {'object_id': self._is_carrying[temp]['obj_id']}

    def __compare_blocks(self, a, b) -> bool:
        return a['visualization']['colour'] == b['visualization']['colour'] and \
               a['visualization']['shape'] == b['visualization']['shape']
    # Have agent head to the open doors

    # Ensure that they only pick up one of each goal items
