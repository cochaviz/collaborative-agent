from agents1.CustomBaselineAgent import CustomBaselineAgent

class StrongAgent(CustomBaselineAgent):
    """
    Can carry two objects at the same time.

    TODO Implement described behavior
    """
    def __init__(self, settings):
        super().__init__(settings)
        self._capacity = 2

    # Have agent head to the open doors

    # Ensure that they only pick up one of each goal items

