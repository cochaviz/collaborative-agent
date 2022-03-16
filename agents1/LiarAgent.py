from agents1.CustomBaselineAgent import CustomBaselineAgent


class LiarAgent(CustomBaselineAgent):
    """
    Information sharing does not always match actions and/or observations. For example, the agent can
    lie about which area an agent is moving to or where it found a goal block. Implement this agent to lie
    about actions and/or observations 80% of the time.

    TODO Implement described behavior
    """
    def __init__(self, settings):
        super().__init__(settings)
