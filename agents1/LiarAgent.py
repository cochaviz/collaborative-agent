import random
import re

from matrx.messages.message import Message

from agents1.CustomBaselineAgent import CustomBaselineAgent


class LiarAgent(CustomBaselineAgent):
    """
    Information sharing does not always match actions and/or observations. For example, the agent can
    lie about which area an agent is moving to or where it found a goal block. Implement this agent to lie
    about actions and/or observations 80% of the time.

    """

    def __init__(self, settings):
        super().__init__(settings)

    def _sendMessage(self, mssg) -> None:
        """
        Enable sending falsified messages 80% of the time
        """
        rand: int = self.__get_number()
        if rand == 1:
            temp1 = self.__replace_color(mssg)
            temp2 = self.__replace_room(temp1)
            temp3 = self.__replace_location(temp2)

            msg = Message(content=temp3, from_id=self._agent_name)

            if msg.content not in self.received_messages:
                self.send_message(msg)
        else:
            msg = Message(content=mssg, from_id=self._agent_name)
            if msg.content not in self.received_messages:
                self.send_message(msg)

    def __get_number(self) -> int:
        """
        Generate 1 80% of the time
        """
        if random.random() <= 0.8:
            return 1
        else:
            return 0

    def __get_random_color(self) -> str:
        """
        Generate a random Hex color & replace in string
        """
        temp: str = '#%02X%02X%02X' % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        return "'colour': " + temp

    def __get_random_room(self) -> str:
        """
        Generate a random room & replace in string
        """
        # TODO (maybe): Ensure that the chosen door isn't the door it is headed to
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        door = random.choice(all_doors)
        return door['room_name']

    def __get_random_location(self) -> str:
        """
        Generate a random location & replace in string
        """
        all_doors = [door for door in self._current_state.values()
                     if 'class_inheritance' in door and 'Door' in door['class_inheritance']]
        door = random.choice(all_doors)
        return str(door['location'])

    def __replace_color(self, msg) -> str:
        """
        Check if the message contains a color
        """
        color = re.compile(r"'colour':\s'#(?:[0-9a-fA-F]{3}){1,2}\b")
        if color.search(msg):
            rand_color = self.__get_random_color()
            temp: str = re.sub(color, rand_color, msg)
            return temp
        else:
            return msg

    def __replace_room(self, msg) -> bool:
        """
        Check if the message contains a room name
        """
        room = re.compile(r'room_\d')
        if room.search(msg):
            rand_room = self.__get_random_room()
            temp: str = re.sub(room, rand_room, msg)
            return temp
        else:
            return msg

    def __replace_location(self, msg) -> bool:
        """
        Check if the message contains a location
        """
        location = re.compile(r'\([0-9]+,\s[0-9]+\)')
        if location.search(msg):
            rand_loc = self.__get_random_location()
            temp: str = re.sub(location, rand_loc, msg)
            return temp
        else:
            return msg
