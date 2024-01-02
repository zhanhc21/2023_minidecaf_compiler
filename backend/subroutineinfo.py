from typing import List
from utils.label.funclabel import FuncLabel
from utils.tac.temp import Temp

"""
SubroutineInfo: collect some info when selecting instr which will be used in SubroutineEmitter
"""


class SubroutineInfo:
    def __init__(self, funcLabel: FuncLabel, temps: List[Temp]) -> None:
        self.funcLabel = funcLabel
        self.temps = temps

    def __str__(self) -> str:
        return "funcLabel: {}{}".format(
            self.funcLabel.name,
            str(self.temps)
        )
