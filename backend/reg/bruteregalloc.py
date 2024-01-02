import random

from backend.dataflow.basicblock import BasicBlock, BlockKind
from backend.dataflow.cfg import CFG
from backend.dataflow.loc import Loc
from backend.reg.regalloc import RegAlloc
from backend.riscv.riscvasmemitter import RiscvAsmEmitter
from backend.subroutineemitter import SubroutineEmitter
from backend.subroutineinfo import SubroutineInfo
from utils.riscv import Riscv
from utils.tac.nativeinstr import NativeInstr
from utils.tac.reg import Reg
from utils.tac.tacop import InstrKind
from utils.tac.temp import Temp

"""
BruteRegAlloc: one kind of RegAlloc

bindings: map from temp.index to Reg

we don't need to take care of GlobalTemp here
because we can remove all the GlobalTemp in selectInstr process

1. accept：根据每个函数的 CFG 进行寄存器分配，寄存器分配结束后生成相应汇编代码
2. bind：将一个 Temp 与寄存器绑定
3. unbind：将一个 Temp 与相应寄存器解绑定
4. localAlloc：根据数据流对一个 BasicBlock 内的指令进行寄存器分配
5. allocForLoc：每一条指令进行寄存器分配
6. allocRegFor：根据数据流决定为当前 Temp 分配哪一个寄存器
"""

class BruteRegAlloc(RegAlloc):
    def __init__(self, emitter: RiscvAsmEmitter) -> None:
        super().__init__(emitter)
        self.bindings = {}
        for reg in emitter.allocatableRegs:
            reg.used = False


    def accept(self, graph: CFG, info: SubroutineInfo) -> None:
        subEmitter = self.emitter.emitSubroutine(info)

        for temp, argReg in zip(subEmitter.info.temps, Riscv.ArgRegs):
            self.bind(temp, argReg)
        if len(graph.reachable) > 0:
            for tempIndex in graph.nodes[0].liveIn:
                if tempIndex in self.bindings:
                    subEmitter.emitStoreToStack(self.bindings.get(tempIndex))
        subEmitter.printer.printComment("store1 " + str(subEmitter.offsets))

        for bb in graph.iterator():
            if bb.label is not None:
                subEmitter.emitLabel(bb.label)
            self.localAlloc(bb, subEmitter)
        subEmitter.emitEnd()


    def bind(self, temp: Temp, reg: Reg):
        reg.used = True
        self.bindings[temp.index] = reg
        reg.occupied = True
        reg.temp = temp


    def unbind(self, temp: Temp):
        if temp.index in self.bindings:
            self.bindings[temp.index].occupied = False
            self.bindings.pop(temp.index)


    def localAlloc(self, bb: BasicBlock, subEmitter: SubroutineEmitter):
        self.bindings.clear()
        for reg in self.emitter.allocatableRegs:
            reg.occupied = False

        # in step9, you may need to think about how to store callersave regs here
        for loc in bb.allSeq():
            if loc.instr.isCall:
                # Call
                self.allocForCall(loc, bb.liveIn, subEmitter)
            else:
                subEmitter.emitComment(str(loc.instr))
                self.allocForLoc(loc, subEmitter)
            # bb.liveOut不更新???
            for tempindex in loc.liveOut:
                if tempindex in self.bindings:
                    subEmitter.emitStoreToStack(self.bindings.get(tempindex))
           
            subEmitter.emitComment("store3 "+ str(subEmitter.offsets))
        if (not bb.isEmpty()) and (bb.kind is not BlockKind.CONTINUOUS):
            self.allocForLoc(bb.locs[len(bb.locs) - 1], subEmitter)


    def allocForCall(self, loc: Loc, liveIn: set[int], subEmitter: SubroutineEmitter):
        # 保存活跃临时变量
        for i in range(len(Riscv.CallerSaved)):
            temp = Riscv.CallerSaved[i].temp
            if temp != None:
                if temp.index in liveIn:
                    subEmitter.emitComment(
                        "store {} to {}".format(
                            str(temp), str(self.bindings.get(temp.index))
                        )
                    )
                    if self.bindings.get(temp.index) is not None:
                        subEmitter.emitStoreToStack(self.bindings.get(temp.index))
                self.unbind(temp)

        # 参数/寄存器绑定
        call = loc.instr
        for temp, argReg in zip(call.srcs, Riscv.ArgRegs):
            subEmitter.emitComment(
                "CALL allocate {} to {}".format(
                    str(temp), str(argReg)
                )
            )
            if temp.index in self.bindings:
                self.unbind(temp)
            subEmitter.printer.printComment("load " + str(subEmitter.offsets))
            subEmitter.emitLoadFromStack(argReg, temp)
            self.bind(temp, argReg)

        # 函数调用
        subEmitter.emitComment(str(call))
        subEmitter.emitNative(NativeInstr(InstrKind.SEQ, call.dsts, call.dsts, call.label, call.__str__()))

        # 处理函数返回值, target绑定a0
        self.bind(call.dsts[0], Riscv.A0)
        subEmitter.emitStoreToStack(Riscv.A0)
        subEmitter.printer.printComment("store2 " + str(subEmitter.offsets))


    def allocForLoc(self, loc: Loc, subEmitter: SubroutineEmitter):
        instr = loc.instr
        srcRegs: list[Reg] = []
        dstRegs: list[Reg] = []

        for i in range(len(instr.srcs)):
            temp = instr.srcs[i]
            if isinstance(temp, Reg):
                srcRegs.append(temp)
            else:
                srcRegs.append(self.allocRegFor(temp, True, loc.liveIn, subEmitter))

        for i in range(len(instr.dsts)):
            temp = instr.dsts[i]
            if isinstance(temp, Reg):
                dstRegs.append(temp)
            else:
                dstRegs.append(self.allocRegFor(temp, False, loc.liveIn, subEmitter))

        subEmitter.emitNative(instr.toNative(dstRegs, srcRegs))


    def allocRegFor(
        self, temp: Temp, isRead: bool, live: set[int], subEmitter: SubroutineEmitter
    ):
        if temp.index in self.bindings:
            return self.bindings[temp.index]

        for reg in self.emitter.allocatableRegs:
            if (not reg.occupied) or (not reg.temp.index in live):
                subEmitter.emitComment(
                    "allocate {} to {}  (read: {}):".format(
                        str(temp), str(reg), str(isRead)
                    )
                )
                if isRead:
                    subEmitter.emitLoadFromStack(reg, temp)
                if reg.occupied:
                    self.unbind(reg.temp)
                self.bind(temp, reg)
                return reg

        reg = self.emitter.allocatableRegs[
            random.randint(0, len(self.emitter.allocatableRegs) - 1)
        ]
        subEmitter.emitStoreToStack(reg)
        subEmitter.printer.printComment("store4 " + str(subEmitter.offsets))
        subEmitter.emitComment("  spill {} ({})".format(str(reg), str(reg.temp)))
        self.unbind(reg.temp)
        self.bind(temp, reg)
        subEmitter.emitComment(
            "  allocate {} to {} (read: {})".format(str(temp), str(reg), str(isRead))
        )
        if isRead:
            subEmitter.emitLoadFromStack(reg, temp)
        return reg
