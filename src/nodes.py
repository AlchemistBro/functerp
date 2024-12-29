from dataclasses import dataclass

# pos = (line, col) for error messages


# -- exprs

@dataclass(frozen=True)
class Num:
    val: int
    pos: tuple = None


@dataclass(frozen=True)
class Var:
    name: str
    pos: tuple = None


@dataclass(frozen=True)
class Decl:  # `int x` / `var x`, only on the left of =
    type: str
    name: str
    pos: tuple = None


@dataclass(frozen=True)
class Tensor:  # (a, b, c), () is Tensor(())
    items: tuple
    pos: tuple = None


@dataclass(frozen=True)
class Neg:
    expr: object
    pos: tuple = None


@dataclass(frozen=True)
class BinOp:
    op: str
    left: object
    right: object
    pos: tuple = None


@dataclass(frozen=True)
class Assign:  # op is '=' or '+=' etc
    op: str
    target: object
    value: object
    pos: tuple = None


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple
    pos: tuple = None


@dataclass(frozen=True)
class Method:  # x.f(..) / x~f(..), name keeps the . or ~
    obj: object
    name: str
    args: tuple
    pos: tuple = None


@dataclass(frozen=True)
class Modify:  # after desugar: x~f(y) -> Modify(x, Call(f, (x, y)))
    target: Var
    call: Call
    pos: tuple = None


# -- stmts

@dataclass(frozen=True)
class ExprStmt:
    expr: object
    pos: tuple = None


@dataclass(frozen=True)
class Return:
    expr: object
    pos: tuple = None


@dataclass(frozen=True)
class If:
    neg: bool  # ifnot
    cond: object
    then: tuple
    other: tuple
    pos: tuple = None


@dataclass(frozen=True)
class While:
    cond: object
    body: tuple
    pos: tuple = None


@dataclass(frozen=True)
class Repeat:
    count: object
    body: tuple
    pos: tuple = None


@dataclass(frozen=True)
class DoUntil:
    body: tuple
    cond: object
    pos: tuple = None


@dataclass(frozen=True)
class Block:
    body: tuple
    pos: tuple = None


# -- top level

@dataclass(frozen=True)
class Const:
    name: str
    value: object
    pos: tuple = None


@dataclass(frozen=True)
class Func:
    ret: object  # 'int' or tuple of types, () is unit
    name: str
    params: tuple  # ((type, name), ...)
    specs: tuple  # impure, inline, inline_ref
    body: tuple  # None for forward declaration
    pos: tuple = None
