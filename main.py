from agents1.Group02Agent import *
from bw4t.BW4TWorld import BW4TWorld
from bw4t.statistics import Statistics


"""
This runs a single session. You have to log in on localhost:3000 and 
press the start button in god mode to start the session.
"""

if __name__ == "__main__":
    runs: int = 1

    agents = [
        {'name': 'strong', 'botclass': StrongAgent, 'settings': {}},
        {'name': 'colorblind', 'botclass': ColorblindAgent, 'settings': {}},
        {'name': 'liar', 'botclass': LiarAgent, 'settings': {}},
        {'name': 'lazy', 'botclass': LazyAgent, 'settings': {}},
        ]

    print("Starting", runs, "runs...")

    for i in range(runs):
        print("Started world", i ,"...")
        world=BW4TWorld(agents).run()
        print("Done, running next...")
        print(Statistics(world.getLogger().getFileName()))

    print("Finished runs")
