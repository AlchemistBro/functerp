from dataclasses import replace
from .lexer import FuncError
from .nodes import *

# name -> (arity, impure)
BUILTINS = {
    '~dump': (1, True),
    'throw': (1, True),
    'throw_if': (2, True),
    'throw_unless': (2, True),
    'min': (2, False),
    'max': (2, False),
    'abs': (1, False),
}


class Desugar:
    def __init__(self):
        self.decls = {}  # all declared funcs, in FunC you must declare before use
        self.funcs = {}  # funcs with bodies, after desugar
        self.consts = {}
        self.used = {}  # name -> pos of first call
        self.scopes = []

    def program(self, items):
        for item in items:
            match item:
                case Const(name, value, pos):
                    if name in self.consts:
                        raise FuncError(f'constant {name} redefined', *pos)
                    self.scopes = []
                    self.consts[name] = self.expr(value)
                case Func():
                    self.func(item)
        for name, pos in self.used.items():
            if name not in BUILTINS and name not in self.funcs:
                raise FuncError(f'function {name} is declared but not defined', *pos)
        if 'main' not in self.funcs:
            raise FuncError('no main() function', 1, 1)
        return self.consts, self.funcs

    def func(self, f):
        if f.name in BUILTINS:
            raise FuncError(f'{f.name} is a builtin', *f.pos)
        old = self.decls.get(f.name)
        if old:
            if len(old.params) != len(f.params):
                raise FuncError(f'{f.name} redeclared with other params', *f.pos)
            if old.body is not None and f.body is not None:
                raise FuncError(f'function {f.name} redefined', *f.pos)
        if not old or f.body is not None:
            self.decls[f.name] = f
        if f.body is None:
            return
        # params first, so recursion works
        self.scopes = [set(name for _, name in f.params)]
        body = self.block(f.body)
        self.funcs[f.name] = replace(f, body=body)

    def impure(self, name):
        if name in BUILTINS:
            return BUILTINS[name][1]
        return 'impure' in self.decls[name].specs

    def arity(self, name):
        if name in BUILTINS:
            return BUILTINS[name][0]
        return len(self.decls[name].params)

    def visible(self, name):
        return any(name in s for s in self.scopes)

    # -- stmts

    def block(self, stmts):
        self.scopes.append(set())
        out = []
        for s in stmts:
            out += self.stmt(s)
        self.scopes.pop()
        return tuple(out)

    def stmt(self, s):
        match s:
            case ExprStmt(e, pos):
                e = self.expr(e)
                # FunC drops calls of non-impure funcs if result is unused
                return [ExprStmt(k, pos) for k in self.residual(e)]
            case Return(e, pos):
                return [Return(self.expr(e), pos)]
            case If(neg, cond, then, other, pos):
                return [If(neg, self.expr(cond), self.block(then), self.block(other), pos)]
            case While(cond, body, pos):
                return [While(self.expr(cond), self.block(body), pos)]
            case Repeat(count, body, pos):
                return [Repeat(self.expr(count), self.block(body), pos)]
            case DoUntil(body, cond, pos):
                # vars from body are visible in until (...)
                self.scopes.append(set())
                body = tuple(x for st in body for x in self.stmt(st))
                cond = self.expr(cond)
                self.scopes.pop()
                return [DoUntil(body, cond, pos)]
            case Block(body, pos):
                return [Block(self.block(body), pos)]
        raise FuncError(f'bad statement {s}', *s.pos)

    def residual(self, e):
        # what is left of an expression whose value nobody needs
        match e:
            case Call(name, args):
                if self.impure(name):
                    return [e]
                return [x for a in args for x in self.residual(a)]
            case Assign() | Modify():
                return [e]
            case Tensor(items):
                return [x for a in items for x in self.residual(a)]
            case Neg(x) | Not(x):
                return self.residual(x)
            case BinOp(_, a, b):
                return self.residual(a) + self.residual(b)
            case Cond(c, a, b):
                # only one branch runs, so keep the whole thing if a branch has effects
                if self.residual(a) or self.residual(b):
                    return [e]
                return self.residual(c)
        return []

    # -- exprs

    def expr(self, e):
        match e:
            case Num():
                return e
            case Var(name, pos):
                if not self.visible(name) and name not in self.consts:
                    raise FuncError(f'undefined variable {name}', *pos)
                return e
            case Decl(_, name, pos):
                raise FuncError(f'declaration of {name} without value', *pos)
            case Tensor(items, pos):
                return Tensor(tuple(self.expr(x) for x in items), pos)
            case Neg(x, pos):
                return Neg(self.expr(x), pos)
            case Not(x, pos):
                return Not(self.expr(x), pos)
            case BinOp(op, a, b, pos):
                return BinOp(op, self.expr(a), self.expr(b), pos)
            case Cond(c, a, b, pos):
                return Cond(self.expr(c), self.expr(a), self.expr(b), pos)
            case Assign(op, target, value, pos):
                value = self.expr(value)
                if op != '=' and not isinstance(target, Var):
                    raise FuncError(f'{op} needs a variable on the left', *pos)
                return Assign(op, self.target(target), value, pos)
            case Call(name, args, pos):
                return self.call(name, tuple(self.expr(a) for a in args), pos)
            case Method(obj, name, args, pos):
                return self.method(self.expr(obj), name, tuple(self.expr(a) for a in args), pos)
        raise FuncError(f'bad expression {e}', *e.pos)

    def target(self, t):
        match t:
            case Var(name, pos):
                if name in self.consts and not self.visible(name):
                    raise FuncError(f'cannot assign to constant {name}', *pos)
                return self.expr(t)
            case Decl(_, name, pos):
                # `int x = ..` for already declared x is just an assignment in FunC
                if self.visible(name):
                    return Var(name, pos)
                self.scopes[-1].add(name)
                return t
            case Tensor(items, pos):
                return Tensor(tuple(self.target(x) for x in items), pos)
        raise FuncError('cannot assign to this', *t.pos)

    def defined(self, name):
        return name in BUILTINS or name in self.decls

    def call(self, name, args, pos):
        if not self.defined(name):
            raise FuncError(f'undefined function {name}', *pos)
        n = self.arity(name)
        if len(args) != n:
            raise FuncError(f'{name} takes {n} args, got {len(args)}', *pos)
        self.used.setdefault(name, pos)
        return Call(name, args, pos)

    def method(self, obj, name, args, pos):
        # x.f(y) -> f(x, y), looks for `.f` first
        # x~f(y) -> (x, r) = f(x, y), value is r, looks for `~f` first
        fname = name if self.defined(name) else name[1:]
        if not self.defined(fname):
            raise FuncError(f'undefined function {name[1:]}', *pos)
        call = self.call(fname, (obj,) + args, pos)
        if name[0] == '.':
            return call
        if not isinstance(obj, Var) or not self.visible(obj.name):
            raise FuncError(f'{name} needs a variable on the left', *pos)
        return Modify(obj, call, pos)


def desugar(items):
    return Desugar().program(items)
