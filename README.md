# TU-Delft-Collaborative-AI-Trust
This is the repository for the Trust Assignment of the course on Collaborative AI at the TU Delft. 
The repository contains the Block Worlds for Teams (BW4T) test bed, an agent coordination and communication test bed, using the MATRX software package. 
The BW4T test-bed consists of multiple rooms containing coloured blocks. 
Two or more agents need to collect these blocks and deliver them to a drop off point that dictates the block colour and order of collection.

## Overview
- directories:
    - 'agents1': Contains the example baseline agent only moving to doors and opening them, and the human agent which can be controlled by humans. 
    For the assignment students are expected to extend the baseline agent. The human agent can be controlled using the following keys of the keyboard:
        - 'w': Move up
        - 'd': Move right
        - 's': Move down
        - 'a': Move left
        - 'q': Grab object
        - 'e': Drop object
        - 'r': Open door
        - 'f': Close door
    - 'bw4t': Contains all the required files to build the environment, task, and agents, and log all relevant data.
    - 'images': Contains some example images which can be used to visualize agents.
    - 'world_1': Will be added after running 'main.py' with the output log files (.csv) containing agent's actions and number of messages sent. 
- files:
    - 'main.py': Running this file launches the BW4T world. Currently, it launches a world with 2 agents and 1 human. 
    This can be changed by adding or removing elements from the 'agents' list in this file.
    - 'requirements.txt': All required dependencies.
    
## Installation
Download or clone this repository and the required dependencies listed in the 'requirements.txt' file. We recommend using Python 3.8 or higher. 
The required dependencies can be installed through 'pip install -r requirements.txt'. 

## Quickstart
- Read through the code to familiarize yourself with its workings. The baseline agent is very limited but provides useful insights.
- Explore the world/environment, task, and agents through 'main.py'. It is also possible to control the human agent.
- Complete the task using the human agent and check the outputted logs. 

### Beyond Moving around
A couple of things:

1. Automatic navigation should be done through the `self._state_tracker`,
   gathering information about the world from the `State` object passed in
   through `BW4TBaselineAgent.decide_on_bw4t_action`. (pro-tip: make the state an attribute, e.g.
   `self._state`)

2. An action should be a `tuple[str, dict]`, where the `str` constitutes the 
   action, and the `dict` the object id onto which the action is performed. In 
   the case that no action is performed on anything, the dict is empty:
```python
# becuase a move doesn't perform on anything
return MoveNorth.__name__, {} 
```
```python
# we open the door, so we store its 'obj_id' in the dict
return OpenDoorAction.__name__, {'object_id':self._door['obj_id']}
```
3. Actions are only performed _after_ another action is submitted. This means
   that if the agent were to be told 'please move up', you will only see this
   reflected in the interface after it has been told to 'pick up the box'.
   
4. TODO: How to look for and pick up objects

## More information
[More documentation can be found 
here](https://tracinsy.ewi.tudelft.nl/pubtrac/BW4T-Matrx-CollaborativeAI/wiki). 
