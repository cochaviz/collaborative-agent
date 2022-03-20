from agents1.CustomBaselineAgent import CustomBaselineAgent


class LazyAgent(CustomBaselineAgent):
    """
    Less willing to use energy and thus sometimes stops what it is doing. This agent does not complete the
    action they say they will do 50% of the time, and start another task/action instead (and communicate
    this new action, therefore they do not lie). For example, this agent may stop searching room X after
    a few moves, and move to another room instead.

    TODO Implement described behavior
    """
    def __init__(self, settings):
        super().__init__(settings)
