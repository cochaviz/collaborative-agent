from agents1.CustomBaselineAgent import CustomBaselineAgent

class StrongAgent(CustomBaselineAgent):
    """
    Can carry two objects at the same time.

    TODO Implement described behavior
    """
    def __init__(self, settings):
        self._collectables: list[dict] = list()

        super().__init__(settings)
