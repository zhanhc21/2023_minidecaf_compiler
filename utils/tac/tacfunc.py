from typing import List
from utils.label.funclabel import FuncLabel
from utils.tac.temp import Temp

from .tacinstr import TACInstr


class TACFunc:
    def __init__(self, entry: FuncLabel, numArgs: int) -> None:
        self.entry = entry
        self.numArgs = numArgs
        self.instrSeq = []
        self.tempUsed = 0
        self.temps: List[Temp] = []


    def getInstrSeq(self) -> list[TACInstr]:
        return self.instrSeq


    def getUsedTempCount(self) -> int:
        return self.tempUsed


    def add(self, instr: TACInstr) -> None:
        self.instrSeq.append(instr)


    def printTo(self) -> None:
        for instr in self.instrSeq:
            if instr.isLabel():
                print(instr)
            else:
                print("    " + str(instr))


    def addTemp(self, temp: Temp) -> None:
        self.temps += [temp]