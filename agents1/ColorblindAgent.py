from matrx.actions import OpenDoorAction

from agents1.CustomBaselineAgent import CustomBaselineAgent, Action, Phase

import re, random


class ColorblindAgent(CustomBaselineAgent):
    """
    Cannot see colors.
    """

    def __init__(self, settings):
        super().__init__(settings)

    def _planPathToClosedDoorPhase(self) -> Action | None:
        self._navigator.reset_full()
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        closed_doors = [door for door in all_doors if not door['is_open']]

        # TODO maybe separate state?
        if len(closed_doors) == 0:
            self._door = random.choice(all_doors)
        else:
            self._door = random.choice(closed_doors)

        door_loc = self._door['location']
        # Location in front of door is south from door
        door_loc = door_loc[0], door_loc[1] + 1

        # Send message of current action
        self._sendMessage('Moving to ' + self._door['room_name'])
        self._navigator.add_waypoints([door_loc])

        self._phase = Phase.FOLLOW_PATH_TO_CLOSED_DOOR

    def _openDoorPhase(self) -> Action | None:
        """
        Has agent continue opening the doors
        """
        self._phase = Phase.PLAN_PATH_TO_CLOSED_DOOR
        self._sendMessage('Opening door of ' + self._door['room_name'])

        # Open door
        return OpenDoorAction.__name__, {'object_id': self._door['obj_id']}

    def _processMessages(self, teamMembers) -> dict:
        """
        Process incoming messages by filtering out the color and create a dictionary with received messages
        from each team member.
        """
        receivedMessages = {}
        for member in teamMembers:
            receivedMessages[member] = []

        # Remove color from the ColorblindAgent's received messages
        if len(self.received_messages) > 0:
            self.__filter_messages(self.received_messages)

        for mssg in self.received_messages:
            for member in teamMembers:
                if mssg.from_id == member:
                    receivedMessages[member].append(mssg.content)
        return receivedMessages

    def __filter_messages(self, strings) -> list[str]:
        """
        Replace any instance of colour in the message with black
        """
        color = re.compile(r"'colour':.*?,")
        for i in range(len(strings)):
            msg: str = strings[i].content
            if color.search(msg):
                temp: str = re.sub(color, "'colour': '#000000',", msg)
                strings[i].content = temp

        return strings

