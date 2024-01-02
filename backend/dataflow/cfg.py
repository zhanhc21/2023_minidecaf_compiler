from backend.dataflow.basicblock import BasicBlock

"""
CFG: Control Flow Graph

nodes: sequence of basicblock
edges: sequence of edge(u,v), which represents after block u is executed, block v may be executed
links: links[u][0] represent the Prev of u, links[u][1] represent the Succ of u,
"""


class CFG:
    def __init__(self, nodes: list[BasicBlock], edges: list[(int, int)]) -> None:
        self.nodes = nodes
        self.edges = edges
        self.reachable = set()
        self.links = []

        for i in range(len(nodes)):
            self.links.append((set(), set()))

        for (u, v) in edges:
            self.links[u][1].add(v)
            self.links[v][0].add(u)

        """
        You can start from basic block 0 and do a DFS traversal of the CFG
        to find all the reachable basic blocks.
        """
        stack = []
        stack.append(0)
        while stack:
            top = stack.pop()
            self.reachable.add(top)
            for node in self.links[top][1]:
                if node not in self.reachable:
                    stack.append(node)       
    

    def getBlock(self, id):
        return self.nodes[id]


    def getPrev(self, id):
        return self.links[id][0]


    def getSucc(self, id):
        return self.links[id][1]


    def getInDegree(self, id):
        return len(self.links[id][0])


    def getOutDegree(self, id):
        return len(self.links[id][1])


    def iterator(self):
        reachableNodes = []
        for n in self.reachable:
            reachableNodes.append(self.nodes[n])
        return iter(reachableNodes)
