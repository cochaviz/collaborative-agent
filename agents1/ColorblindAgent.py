from __future__ import annotations

from matrx.actions import OpenDoorAction, CloseDoorAction

from agents1.CustomBaselineAgent import CustomBaselineAgent, Action, Phase

import re

class ColorblindAgent(CustomBaselineAgent):
    """
    Cannot see colors.

    TODO Implement described behavior
    """

    def __init__(self, settings):
        super().__init__(settings)

    # Have the colorblind agent open all the doors
    def _openDoorPhase(self) -> Action | None:
        '''

        '''
        self._sendMessage('Opening door of ' + self._door['room_name'])
        self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR

        # Open door
        return OpenDoorAction.__name__, {'object_id': self._door['obj_id']}

    def _processMessages(self, teamMembers) -> dict:
        '''
        Process incoming messages and create a dictionary with received messages from each team member.
        '''
        receivedMessages = {}
        for member in teamMembers:
            receivedMessages[member] = []
        for mssg in self.received_messages:
            for member in teamMembers:
                if mssg.from_id == member:
                    message = self.__filter_messages(mssg.content)
                    receivedMessages[member].append(message)
        return receivedMessages

    def __filter_messages(self, string) -> str:
        color = re.compile("'colour':\s'#(?:[0-9a-fA-F]{3}){1,2}\b'")
        match = re.search(color, string)

        self._report_to_console("Received: " + str(match))

        return string