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
