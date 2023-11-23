from typing import Protocol, TypeVar, cast

from frontend.ast.node import Node, NullType
from frontend.ast.tree import *
from frontend.ast.visitor import RecursiveVisitor, Visitor
from frontend.scope.globalscope import GlobalScope
from frontend.scope.scope import Scope, ScopeKind
from frontend.scope.scopestack import ScopeStack
from frontend.symbol.funcsymbol import FuncSymbol
from frontend.symbol.symbol import Symbol
from frontend.symbol.varsymbol import VarSymbol
from frontend.type.array import ArrayType
from frontend.type.type import DecafType
from utils.error import *
from utils.riscv import MAX_INT

"""
The namer phase: resolve all symbols defined in the abstract 
syntax tree and store them in symbol tables (i.e. scopes).
"""


class Namer(Visitor[ScopeStack, None]):
    def __init__(self) -> None:
        pass

    # Entry of this phase
    def transform(self, program: Program) -> Program:
        # Global scope. You don't have to consider it until Step 6.
        ctx = ScopeStack()
        program.accept(self, ctx)
        return program

    def visitProgram(self, program: Program, ctx: ScopeStack) -> None:
        # Check if the 'main' function is missing
        if not program.hasMainFunc():
            raise DecafNoMainFuncError

        for func in program.functions().values():
            func.accept(self, ctx)

    def visitFunction(self, func: Function, ctx: ScopeStack) -> None:
        func.body.accept(self, ctx)

    def visitBlock(self, block: Block, ctx: ScopeStack) -> None:
        # 新建一个局部作用域并入栈
        ctx.push(Scope(ScopeKind.LOCAL))
        for child in block:
            child.accept(self, ctx)
        # 出栈
        ctx.pop()    

    def visitReturn(self, stmt: Return, ctx: ScopeStack) -> None:
        stmt.expr.accept(self, ctx)

    def visitIf(self, stmt: If, ctx: ScopeStack) -> None:
        stmt.cond.accept(self, ctx)
        stmt.then.accept(self, ctx)

        # check if the else branch exists
        if not stmt.otherwise is NULL:
            stmt.otherwise.accept(self, ctx)

    def visitCondExpr(self, expr: ConditionExpression, ctx: ScopeStack) -> None:
        expr.cond.accept(self, ctx)
        expr.then.accept(self, ctx)
        expr.otherwise.accept(self, ctx)

    def visitWhile(self, stmt: While, ctx: ScopeStack) -> None:
        stmt.cond.accept(self, ctx)
        
        ctx.openloop()
        stmt.body.accept(self, ctx)
        ctx.closeloop()

    def visitFor(self, stmt: For, ctx: ScopeStack) -> None:
        ctx.push(Scope(ScopeKind.LOCAL))
        
        stmt.init.accept(self, ctx)
        stmt.cond.accept(self, ctx)
        stmt.update.accept(self, ctx)

        ctx.openloop()
        stmt.body.accept(self, ctx)
        ctx.closeloop()
        ctx.pop()

    def visitBreak(self, stmt: Break, ctx: ScopeStack) -> None:
        if ctx.checkLoop() == 0:
            raise DecafBreakOutsideLoopError()
    
    def visitContinue(self, stmt: Continue, ctx: Scope) -> None:
        if ctx.checkLoop() == 0:
            raise DecafBreakOutsideLoopError()

    def visitDeclaration(self, decl: Declaration, ctx: ScopeStack) -> None:
        if ctx.top().lookup(decl.ident.value) == None:
            var = VarSymbol(decl.ident.value, decl.var_t.type)
            ctx.top().declare(var)
            decl.setattr("symbol", var)
            if decl.init_expr != NULL:
                decl.init_expr.accept(self, ctx)
        else:
            raise DecafDeclConflictError(str(decl.ident.value)) 

    def visitAssignment(self, expr: Assignment, ctx: ScopeStack) -> None:
        expr.lhs.accept(self, ctx)
        expr.rhs.accept(self, ctx)

    def visitUnary(self, expr: Unary, ctx: ScopeStack) -> None:
        expr.operand.accept(self, ctx)

    def visitBinary(self, expr: Binary, ctx: ScopeStack) -> None:
        expr.lhs.accept(self, ctx)
        expr.rhs.accept(self, ctx)

    def visitIdentifier(self, ident: Identifier, ctx: ScopeStack) -> None:
        if ctx.lookup(ident.value) == None:
            raise DecafUndefinedVarError(str(ident.value))
        ident.setattr("symbol", ctx.lookup(ident.value))

    def visitIntLiteral(self, expr: IntLiteral, ctx: ScopeStack) -> None:
        value = expr.value
        if value > MAX_INT:
            raise DecafBadIntValueError(value)
