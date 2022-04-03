import matplotlib
import seaborn
import pandas
import matplotlib.pyplot as plt
import matplotlib
import sys

def plot(agent_name):
    matplotlib.use('tkagg')
    csv = pandas.read_csv(r'agents1/trust_' + agent_name + ".csv")
    res = seaborn.lineplot(data=csv)
    plt.show()

if __name__=="__main__":
    if len(sys.argv) <= 1:
        print("argument needs to be the agent name")
        quit(1)

    plot(sys.argv[1])
