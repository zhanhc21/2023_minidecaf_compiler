from typing import Optional

from frontend.symbol.symbol import Symbol
from frontend.symbol.funcsymbol import FuncSymbol

from .scope import Scope

class ScopeStack:
    def __init__(self, globalScope: Scope) -> None:
        self.scopes = [globalScope]
        self.globalScope = globalScope
        self.loopNum = 0

    def push(self, scope: Scope) -> None:
        self.scopes.append(scope)
        
    def pop(self) -> None:
        self.scopes.pop()

    def top(self) -> Scope:
        return self.scopes[-1]

    def lookup(self, name: str) -> Optional[Symbol]:
        for scope in self.scopes[::-1]:
            if scope.containsKey(name):
                return scope.get(name)
        return None

    def openLoop(self) -> None:
        self.loopNum += 1
    
    def closeLoop(self) -> None:
        self.loopNum -= 1

    def checkLoop(self) -> int:
        return self.loopNum
