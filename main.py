from agents1.CustomBaselineAgent import CustomBaselineAgent
from agents1.LazyAgent import LazyAgent
from agents1.LiarAgent import LiarAgent
from agents1.StrongAgent import StrongAgent
from agents1.ColorblindAgent import ColorblindAgent
from bw4t.BW4TWorld import BW4TWorld
from bw4t.statistics import Statistics
from agents1.BW4THuman import Human


"""
This runs a single session. You have to log in on localhost:3000 and 
press the start button in god mode to start the session.
"""

if __name__ == "__main__":
    runs: int = 10

    agents = [
        {'name': 'strong', 'botclass': StrongAgent, 'settings': {}},
        # {'name': 'agent3', 'botclass': CustomBaselineAgent, 'settings': {}},
        {'name': 'colorblind', 'botclass': ColorblindAgent, 'settings': {}},
        {'name': 'liar', 'botclass': LiarAgent, 'settings': {}},
        {'name': 'lazy', 'botclass': LazyAgent, 'settings': {}},
        {'name': 'human', 'botclass': Human, 'settings': {}}
        ]

    print("Starting", runs, "runs...")

    for i in range(runs):
        print("Started world", i ,"...")
        world=BW4TWorld(agents).run()
        print("Done, running next...")
        print(Statistics(world.getLogger().getFileName()))

    print("Finished runs")
