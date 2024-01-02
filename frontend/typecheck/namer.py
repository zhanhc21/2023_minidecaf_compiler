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
The namer phase: resolve all symbols defined in the abstract syntax tree and store them in symbol tables (i.e. scopes).
"""


class Namer(Visitor[ScopeStack, None]):
    def __init__(self) -> None:
        pass

    # Entry of this phase
    def transform(self, program: Program) -> Program:
        # Global scope. You don't have to consider it until Step 9.
        program.globalScope = GlobalScope
        ctx = ScopeStack(program.globalScope)

        program.accept(self, ctx)
        return program


    def visitProgram(self, program: Program, ctx: ScopeStack) -> None:
        # Check if the 'main' function is missing
        if not program.hasMainFunc():
            raise DecafNoMainFuncError

        for component in program:
            component.accept(self, ctx)


    def visitParameter(self, that: Parameter, ctx: T) -> None:
        return self.visitDeclaration(that, ctx)


    def visitFunction(self, func: Function, ctx: ScopeStack) -> None:
        # Check identifier conflict
        sym = FuncSymbol(func.ident.value, func.ret_t.type, ctx.top())
        for param in func.params:
            sym.addParaType(param.var_t.type)

        potential_sym = ctx.lookup(func.ident.value)
        if ctx.lookup(func.ident.value):
            if not (isinstance(potential_sym, FuncSymbol) and potential_sym == sym):
                raise DecafDeclConflictError(func.ident.value)
            sym = potential_sym
        else:
            ctx.globalScope.declare(sym)

        func.setattr('symbol', sym)
        if func.body is NULL:  # function decl only
            return
        sym.define()
        ctx.push(Scope(ScopeKind.LOCAL))
        for param in func.params:
            param.accept(self, ctx)
        # Visit body statements.
        # Note that visit the block directly will generate a new scope
        for stmt in func.body.children:
            stmt.accept(self, ctx)
        ctx.pop()


    def visitBlock(self, block: Block, ctx: ScopeStack) -> None:
        ctx.push(Scope(ScopeKind.LOCAL))
        for child in block:
            child.accept(self, ctx)
        ctx.pop()


    def visitReturn(self, stmt: Return, ctx: ScopeStack) -> None:
        stmt.expr.accept(self, ctx)


    def visitFor(self, stmt: For, ctx: ScopeStack) -> None:
        with ctx.local():
            stmt.init.accept(self, ctx)
            stmt.cond.accept(self, ctx)
            stmt.update.accept(self, ctx)
            with ctx.loop():
                stmt.body.accept(self, ctx)


    def visitIf(self, stmt: If, ctx: ScopeStack) -> None:
        stmt.cond.accept(self, ctx)
        stmt.then.accept(self, ctx)

        # check if the else branch exists
        if not stmt.otherwise is NULL:
            stmt.otherwise.accept(self, ctx)


    def visitWhile(self, stmt: While, ctx: ScopeStack) -> None:
        stmt.cond.accept(self, ctx)
        ctx.openLoop()
        stmt.body.accept(self, ctx)
        ctx.closeLoop()


    def visitBreak(self, stmt: Break, ctx: ScopeStack) -> None:
        if not ctx.inLoop():
            raise DecafBreakOutsideLoopError()


    def visitContinue(self, stmt: Continue, ctx: ScopeStack) -> None:
        """
        1. Refer to the implementation of visitBreak.
        """
        if not ctx.inLoop():
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
        """
        1. Refer to the implementation of visitBinary.
        """
        if not isinstance(expr.lhs, Identifier):
            raise DecafSyntaxError(f'Cannot assign to value to {type(expr.lhs).__name__}')
        self.visitBinary(expr, ctx)


    def visitUnary(self, expr: Unary, ctx: ScopeStack) -> None:
        expr.operand.accept(self, ctx)


    def visitBinary(self, expr: Binary, ctx: ScopeStack) -> None:
        expr.lhs.accept(self, ctx)
        expr.rhs.accept(self, ctx)


    def visitCondExpr(self, expr: ConditionExpression, ctx: ScopeStack) -> None:
        """
        1. Refer to the implementation of visitBinary.
        """
        expr.cond.accept(self, ctx)
        expr.then.accept(self, ctx)
        expr.otherwise.accept(self, ctx)


    def visitIdentifier(self, ident: Identifier, ctx: ScopeStack) -> None:
        """
        1. Use ctx.lookup to find the symbol corresponding to ident.
        2. If it has not been declared, raise a DecafUndefinedVarError.
        3. Set the 'symbol' attribute of ident.
        """
        symbol = ctx.lookup(ident.value)
        if symbol is None:
            raise DecafUndefinedVarError(ident.value, " is not defined")
        ident.setattr('symbol', symbol)


    def visitIntLiteral(self, expr: IntLiteral, ctx: ScopeStack) -> None:
        value = expr.value
        if value > MAX_INT:
            raise DecafBadIntValueError(value)


    def visitCall(self, call: Call, ctx: ScopeStack) -> None:
        func: FuncSymbol = ctx.lookup(call.ident.value)
        # Check if function is defined
        if func is None or func.isFunc is False:
            raise DecafUndefinedFuncError(call.ident.value)

        # Check if param_list match
        if len(call.argument_list) != func.parameterNum:
            raise DecafBadFuncCallError(str(call.argument_list))

        call.ident.setattr('symbol', func)
        for arg in call.argument_list:
            arg.accept(self, ctx)
