import sys
from .lexer import FuncError
from .nodes import *
from .parser import parse
from .desugar import desugar

# FunC int is 257-bit signed
INT_MIN = -2 ** 256
INT_MAX = 2 ** 256 - 1

# TVM exit codes
INT_OVERFLOW = 4
RANGE_CHECK = 5


class Throw(Exception):
    def __init__(self, code):
        super().__init__(f'exit code {code}')
        self.code = code


class Ret(Exception):
    def __init__(self, val):
        self.val = val


def fmt(v):
    if isinstance(v, tuple):
        return '(' + ', '.join(fmt(x) for x in v) + ')'
    return str(v)


def num(v, pos):
    if not isinstance(v, int):
        raise FuncError(f'expected int, got tensor {fmt(v)}', *pos)
    return v


def check(v):
    if not INT_MIN <= v <= INT_MAX:
        raise Throw(INT_OVERFLOW)
    return v


def b(x):
    return -1 if x else 0  # true is -1 in FunC


def div(a, c, mode='/'):
    if c == 0:
        raise Throw(INT_OVERFLOW)  # TVM: division by zero is int overflow
    match mode:
        case '/':  # to -inf, python // does the same
            return a // c
        case '^':  # to +inf
            return -(-a // c)
        case '~':  # to nearest, .5 goes to +inf: 3 ~/ 2 = 2, -3 ~/ 2 = -1
            return (2 * a + c) // (2 * c)


def mod(a, c, mode='/'):
    return a - div(a, c, mode) * c


OPS = {
    '+': lambda a, c: check(a + c),
    '-': lambda a, c: check(a - c),
    '*': lambda a, c: check(a * c),
    '/': lambda a, c: check(div(a, c)),
    '^/': lambda a, c: check(div(a, c, '^')),
    '~/': lambda a, c: check(div(a, c, '~')),
    '%': lambda a, c: mod(a, c),
    '^%': lambda a, c: mod(a, c, '^'),
    '~%': lambda a, c: mod(a, c, '~'),
    '/%': lambda a, c: (check(div(a, c)), mod(a, c)),
    '&': lambda a, c: a & c,
    '|': lambda a, c: a | c,
    '==': lambda a, c: b(a == c),
    '!=': lambda a, c: b(a != c),
    '<': lambda a, c: b(a < c),
    '>': lambda a, c: b(a > c),
    '<=': lambda a, c: b(a <= c),
    '>=': lambda a, c: b(a >= c),
}


def dump(it, v):
    it.out(f'#DEBUG#: s0 = {fmt(v)}')
    return ()


def throw(it, code):
    raise Throw(code)


def throw_if(it, code, cond):
    if cond != 0:
        raise Throw(code)
    return ()


def throw_unless(it, code, cond):
    if cond == 0:
        raise Throw(code)
    return ()


BUILTINS = {
    '~dump': dump,
    'throw': throw,
    'throw_if': throw_if,
    'throw_unless': throw_unless,
    'min': lambda it, a, c: min(a, c),
    'max': lambda it, a, c: max(a, c),
    'abs': lambda it, a: check(abs(a)),
}


class Interp:
    def __init__(self, consts, funcs, out=print):
        self.funcs = funcs
        self.out = out
        self.consts = {}
        for name, e in consts.items():
            self.consts[name] = self.eval(e, {})

    def run(self):
        return self.call('main', ())

    def call(self, name, args):
        if name in BUILTINS:
            return BUILTINS[name](self, *args)
        f = self.funcs[name]
        env = {p: a for (_, p), a in zip(f.params, args)}
        try:
            self.block(f.body, env)
        except Ret as r:
            return r.val
        if f.ret != ():
            raise FuncError(f'{name} ended without return', *f.pos)
        return ()

    # -- stmts

    def block(self, stmts, env):
        for s in stmts:
            self.stmt(s, env)

    def truth(self, e, env):
        return num(self.eval(e, env), e.pos) != 0

    def stmt(self, s, env):
        match s:
            case ExprStmt(e):
                self.eval(e, env)
            case Return(e):
                raise Ret(self.eval(e, env))
            case If(neg, cond, then, other):
                if self.truth(cond, env) != neg:
                    self.block(then, env)
                else:
                    self.block(other, env)
            case While(cond, body):
                while self.truth(cond, env):
                    self.block(body, env)
            case Repeat(count, body, pos):
                n = num(self.eval(count, env), pos)
                if not -2 ** 31 <= n < 2 ** 31:
                    raise Throw(RANGE_CHECK)
                for _ in range(n):
                    self.block(body, env)
            case DoUntil(body, cond):
                while True:
                    self.block(body, env)
                    if self.truth(cond, env):
                        break
            case Block(body):
                self.block(body, env)

    # -- exprs

    def eval(self, e, env):
        match e:
            case Num(val):
                return check(val)
            case Var(name):
                return env[name] if name in env else self.consts[name]
            case Tensor(items):
                return tuple(self.eval(x, env) for x in items)
            case Neg(x, pos):
                return check(-num(self.eval(x, env), pos))
            case Not(x, pos):
                return ~num(self.eval(x, env), pos)
            case BinOp(op, a, c, pos):
                a = num(self.eval(a, env), a.pos)
                c = num(self.eval(c, env), c.pos)
                return OPS[op](a, c)
            case Assign('=', target, value):
                v = self.eval(value, env)
                self.assign(target, v, env)
                return v
            case Assign(op, Var(name), value, pos):
                v = num(self.eval(value, env), value.pos)
                v = OPS[op[:-1]](num(env[name], pos), v)
                env[name] = v
                return v
            case Call(name, args):
                return self.call(name, tuple(self.eval(a, env) for a in args))
            case Modify(Var(name), call, pos):
                r = self.eval(call, env)
                if not isinstance(r, tuple) or len(r) != 2:
                    raise FuncError(f'{call.name} must return a pair to be used with ~', *pos)
                env[name] = r[0]
                return r[1]
        raise FuncError(f'cannot eval {e}', *e.pos)

    def assign(self, t, v, env):
        match t:
            case Var(name) | Decl('var', name):
                env[name] = v
            case Decl('int', name, pos):
                env[name] = num(v, pos)
            case Tensor(items, pos):
                if not isinstance(v, tuple) or len(v) != len(items):
                    raise FuncError(f'cannot unpack {fmt(v)} into {len(items)} values', *pos)
                for x, y in zip(items, v):
                    self.assign(x, y, env)


def load(src):
    return desugar(parse(src))


def run(src, out=print):
    # returns exit code: 0 or TVM exception code
    consts, funcs = load(src)
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))
    try:
        res = Interp(consts, funcs, out).run()
    except Throw as t:
        out(f'exit code: {t.code}')
        return t.code
    except RecursionError:
        raise FuncError('recursion is too deep', 1, 1)
    if res != ():
        out(f'result: {fmt(res)}')
    return 0
