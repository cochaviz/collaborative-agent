from agents1.CustomBaselineAgent import CustomBaselineAgent


class ColorblindAgent(CustomBaselineAgent):
    """
    Cannot see colors.

    TODO Implement described behavior
    """

    def __init__(self, settings):
        super().__init__(settings)
