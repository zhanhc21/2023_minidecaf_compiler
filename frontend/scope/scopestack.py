from typing import Optional

from frontend.symbol.symbol import Symbol

from .scope import Scope

class ScopeStack:
    def __init__(self) -> None:
        self.scopes = []

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