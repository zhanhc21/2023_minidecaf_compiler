from frontend.ast.node import Optional
from frontend.ast.tree import Function, Optional
from frontend.ast import node
from frontend.ast.tree import *
from frontend.ast.visitor import Visitor
from frontend.symbol.varsymbol import VarSymbol
from frontend.type.array import ArrayType
from utils.label.blocklabel import BlockLabel
from utils.label.funclabel import FuncLabel
from utils.tac import tacop
from utils.tac.temp import Temp
from utils.tac.tacinstr import *
from utils.tac.tacfunc import TACFunc
from utils.tac.tacprog import TACProg
from utils.tac.tacvisitor import TACVisitor

"""
The TAC generation phase: translate the abstract syntax tree into three-address code.
"""

class LabelManager:
    """
    A global label manager (just a counter).
    We use this to create unique (block) labels accross functions.
    """

    def __init__(self):
        self.nextTempLabelId = 0

    def freshLabel(self) -> BlockLabel:
        self.nextTempLabelId += 1
        return BlockLabel(str(self.nextTempLabelId))


class TACFuncEmitter(TACVisitor):
    """
    Translates a minidecaf (AST) function into low-level TAC function.
    """

    def __init__(
        self, entry: FuncLabel, numArgs: int, labelManager: LabelManager
    ) -> None:
        self.labelManager = labelManager
        self.func = TACFunc(entry, numArgs)
        self.visitLabel(entry)
        self.nextTempId = 0

        self.continueLabelStack = []
        self.breakLabelStack = []

    # To get a fresh new temporary variable.
    def freshTemp(self) -> Temp:
        temp = Temp(self.nextTempId)
        self.nextTempId += 1
        return temp

    # To get a fresh new label (for jumping and branching, etc).
    def freshLabel(self) -> Label:
        return self.labelManager.freshLabel()

    # To count how many temporary variables have been used.
    def getUsedTemp(self) -> int:
        return self.nextTempId

    # In fact, the following methods can be named 'appendXXX' rather than 'visitXXX'.
    # E.g., by calling 'visitAssignment', you add an assignment instruction at the end of current function.
    def visitAssignment(self, dst: Temp, src: Temp) -> Temp:
        self.func.add(Assign(dst, src))
        return src

    def visitLoad(self, value: Union[int, str]) -> Temp:
        temp = self.freshTemp()
        self.func.add(LoadImm4(temp, value))
        return temp

    def visitUnary(self, op: UnaryOp, operand: Temp) -> Temp:
        temp = self.freshTemp()
        self.func.add(Unary(op, temp, operand))
        return temp

    def visitUnarySelf(self, op: UnaryOp, operand: Temp) -> None:
        self.func.add(Unary(op, operand, operand))

    def visitBinary(self, op: BinaryOp, lhs: Temp, rhs: Temp) -> Temp:
        temp = self.freshTemp()
        self.func.add(Binary(op, temp, lhs, rhs))
        return temp

    def visitBinarySelf(self, op: BinaryOp, lhs: Temp, rhs: Temp) -> None:
        self.func.add(Binary(op, lhs, lhs, rhs))

    def visitBranch(self, target: Label) -> None:
        self.func.add(Branch(target))

    def visitCondBranch(self, op: CondBranchOp, cond: Temp, target: Label) -> None:
        self.func.add(CondBranch(op, cond, target))

    def visitReturn(self, value: Optional[Temp]) -> None:
        self.func.add(Return(value))

    def visitLabel(self, label: Label) -> None:
        self.func.add(Mark(label))

    def visitMemo(self, content: str) -> None:
        self.func.add(Memo(content))

    def visitRaw(self, instr: TACInstr) -> None:
        self.func.add(instr)

    def visitEnd(self) -> TACFunc:
        if (len(self.func.instrSeq) == 0) or (not self.func.instrSeq[-1].isReturn()):
            self.func.add(Return(None))
        self.func.tempUsed = self.getUsedTemp()
        return self.func

    # To open a new loop (for break/continue statements)
    def openLoop(self, breakLabel: Label, continueLabel: Label) -> None:
        self.breakLabelStack.append(breakLabel)
        self.continueLabelStack.append(continueLabel)

    # To close the current loop.
    def closeLoop(self) -> None:
        self.breakLabelStack.pop()
        self.continueLabelStack.pop()

    # To get the label for 'break' in the current loop.
    def getBreakLabel(self) -> Label:
        return self.breakLabelStack[-1]

    # To get the label for 'continue' in the current loop.
    def getContinueLabel(self) -> Label:
        return self.continueLabelStack[-1]


class TACGen(Visitor[TACFuncEmitter, None]):
    # Entry of this phase

    def transform(self, program: Program) -> TACProg:
        labelManager = LabelManager()
        tacFuncs = []
        for funcName, astFunc in program.functions().items():
            # in step9, you need to use real parameter count
            emitter = TACFuncEmitter(FuncLabel(funcName), 0, labelManager)
            astFunc.body.accept(self, emitter)
            tacFuncs.append(emitter.visitEnd())
        return TACProg(tacFuncs)

    def visitBlock(self, block: Block, mv: TACFuncEmitter) -> None:
        for child in block:
            child.accept(self, mv)

    def visitReturn(self, stmt: Return, mv: TACFuncEmitter) -> None:
        stmt.expr.accept(self, mv)
        mv.visitReturn(stmt.expr.getattr("val"))

    def visitBreak(self, stmt: Break, mv: TACFuncEmitter) -> None:
        mv.visitBranch(mv.getBreakLabel())

    def visitContinue(self, stmt: Continue, mv: TACFuncEmitter) -> None:
        mv.visitBranch(mv.getContinueLabel())

    def visitDeclaration(self, decl: Declaration, mv: TACFuncEmitter) -> None:
        var = decl.getattr("symbol")
        var.temp = mv.freshTemp()
        if decl.init_expr != NULL:
            decl.init_expr.accept(self, mv)
            mv.visitAssignment(var.temp, decl.init_expr.getattr("val"))

    def visitAssignment(self, expr: Assignment, mv: TACFuncEmitter) -> None:
        expr.rhs.accept(self, mv)
        r_temp = expr.rhs.getattr("val")
        l_temp = expr.lhs.getattr("symbol").temp
        mv.visitAssignment(l_temp, r_temp)
        expr.setattr("val", r_temp)
        
    def visitIdentifier(self, ident: Identifier, mv: TACFuncEmitter) -> None:
        var = ident.getattr("symbol")
        ident.setattr("val", var.temp)
    
    def visitIf(self, stmt: If, mv: TACFuncEmitter) -> None:
        stmt.cond.accept(self, mv)

        if stmt.otherwise is NULL:
            skipLabel = mv.freshLabel()
            mv.visitCondBranch(
                tacop.CondBranchOp.BEQ, stmt.cond.getattr("val"), skipLabel
            )
            stmt.then.accept(self, mv)
            mv.visitLabel(skipLabel)
        else:
            skipLabel = mv.freshLabel()
            exitLabel = mv.freshLabel()
            mv.visitCondBranch(
                tacop.CondBranchOp.BEQ, stmt.cond.getattr("val"), skipLabel
            )
            stmt.then.accept(self, mv)
            mv.visitBranch(exitLabel)
            mv.visitLabel(skipLabel)
            stmt.otherwise.accept(self, mv)
            mv.visitLabel(exitLabel)

    def visitWhile(self, stmt: While, mv: TACFuncEmitter) -> None:
        beginLabel = mv.freshLabel()
        loopLabel = mv.freshLabel()
        breakLabel = mv.freshLabel()
        mv.openLoop(breakLabel, loopLabel)

        mv.visitLabel(beginLabel)
        stmt.cond.accept(self, mv)
        mv.visitCondBranch(tacop.CondBranchOp.BEQ, stmt.cond.getattr("val"), breakLabel)

        stmt.body.accept(self, mv)
        mv.visitLabel(loopLabel)
        mv.visitBranch(beginLabel)
        mv.visitLabel(breakLabel)
        mv.closeLoop()

    def visitFor(self, stmt: For, mv: TACFuncEmitter) -> None:
        beginLabel = mv.freshLabel()
        loopLabel = mv.freshLabel()
        breakLabel = mv.freshLabel()

        # ini i
        stmt.init.accept(self, mv)
        mv.openLoop(breakLabel, loopLabel)

        mv.visitLabel(beginLabel)
        stmt.cond.accept(self, mv)
        mv.visitCondBranch(tacop.CondBranchOp.BEQ, stmt.cond.getattr("val"), breakLabel)

        stmt.body.accept(self, mv)
        mv.visitLabel(loopLabel)
        stmt.update.accept(self, mv)

        mv.visitBranch(beginLabel)
        mv.visitLabel(breakLabel)
        mv.closeLoop()

    def visitUnary(self, expr: Unary, mv: TACFuncEmitter) -> None:
        expr.operand.accept(self, mv)
        
        op = {
            node.UnaryOp.Neg: tacop.TacUnaryOp.NEG,
            node.UnaryOp.BitNot: tacop.TacUnaryOp.BITNOT,
            node.UnaryOp.LogicNot: tacop.TacUnaryOp.LOGICNOT
        }[expr.op]
        expr.setattr("val", mv.visitUnary(op, expr.operand.getattr("val")))

    def visitBinary(self, expr: Binary, mv: TACFuncEmitter) -> None:
        expr.lhs.accept(self, mv)
        expr.rhs.accept(self, mv)

        op = {
            node.BinaryOp.Add: tacop.TacBinaryOp.ADD,
            node.BinaryOp.Sub: tacop.TacBinaryOp.SUB,
            node.BinaryOp.Mul: tacop.TacBinaryOp.MUL,
            node.BinaryOp.Div: tacop.TacBinaryOp.DIV,
            node.BinaryOp.Mod: tacop.TacBinaryOp.MOD,

            node.BinaryOp.EQ: tacop.TacBinaryOp.EQU,
            node.BinaryOp.NE: tacop.TacBinaryOp.NEQ,
            node.BinaryOp.LT: tacop.TacBinaryOp.SLT,
            node.BinaryOp.GT: tacop.TacBinaryOp.SGT,
            node.BinaryOp.LE: tacop.TacBinaryOp.LEQ,
            node.BinaryOp.GE: tacop.TacBinaryOp.GEQ,

            node.BinaryOp.LogicOr: tacop.TacBinaryOp.LOR,
            node.BinaryOp.LogicAnd: tacop.TacBinaryOp.LAND,

            # assignment
            node.BinaryOp.Assign: tacop.TacBinaryOp.ASSIGN,
        }[expr.op]
        expr.setattr(
            "val", mv.visitBinary(op, expr.lhs.getattr("val"), expr.rhs.getattr("val"))
        )

    def visitCondExpr(self, expr: ConditionExpression, mv: TACFuncEmitter) -> None:
        expr.cond.accept(self, mv)

        # 分配临时变量
        temp = mv.freshTemp()
        skipLabel = mv.freshLabel()
        exitLabel = mv.freshLabel()

        mv.visitCondBranch (
            tacop.CondBranchOp.BEQ, expr.cond.getattr("val"), skipLabel
        )
        # L1
        expr.then.accept(self, mv)
        mv.visitAssignment(temp, expr.then.getattr("val"))
        mv.visitBranch(exitLabel)
        # L2
        mv.visitLabel(skipLabel)
        expr.otherwise.accept(self, mv)
        mv.visitAssignment(temp, expr.otherwise.getattr("val"))
        mv.visitLabel(exitLabel)

        expr.setattr("val", temp)

    def visitIntLiteral(self, expr: IntLiteral, mv: TACFuncEmitter) -> None:
        expr.setattr("val", mv.visitLoad(expr.value))
