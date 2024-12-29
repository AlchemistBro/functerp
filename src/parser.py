from .lexer import tokenize, FuncError
from .nodes import *

# FunC precedence, bigger binds tighter:
#   =  +=  ...       1  (right)
#   == != < > <= >=  2
#   + - |            3
#   unary -          between 3 and 4: `- a * b` is `-(a * b)`
#   * / &            4
BINOPS = {
    '==': 2, '!=': 2, '<': 2, '>': 2, '<=': 2, '>=': 2,
    '+': 3, '-': 3, '|': 3,
    '*': 4, '/': 4, '&': 4,
}
ASSIGN = {'=', '+=', '-=', '*=', '/=', '&=', '|='}
NEG_PREC = 4
SPECS = ('impure', 'inline', 'inline_ref')


class Parser:
    def __init__(self, src):
        self.toks = tokenize(src)
        self.i = 0

    # -- helpers

    def peek(self, k=0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def check(self, kind, val=None, k=0):
        t = self.peek(k)
        return t.kind == kind and (val is None or t.val == val)

    def accept(self, kind, val=None):
        if self.check(kind, val):
            return self.next()
        return None

    def expect(self, kind, val=None):
        if self.check(kind, val):
            return self.next()
        t = self.peek()
        want = repr(val) if val else kind
        got = 'end of file' if t.kind == 'eof' else repr(t.val)
        raise FuncError(f'expected {want}, got {got}', t.line, t.col)

    def pos(self):
        t = self.peek()
        return (t.line, t.col)

    # -- top level

    def program(self):
        items = []
        while not self.check('eof'):
            if self.check('kw', 'const'):
                items.append(self.const())
            else:
                items.append(self.func())
        return items

    def const(self):
        pos = self.pos()
        self.expect('kw', 'const')
        self.accept('kw', 'int')
        name = self.expect('id').val
        self.expect('op', '=')
        value = self.expr()
        self.expect('punct', ';')
        return Const(name, value, pos)

    def type(self):
        if self.accept('kw', 'int'):
            return 'int'
        if self.accept('kw', 'var'):
            return 'var'
        if self.accept('punct', '('):
            types = []
            while not self.check('punct', ')'):
                types.append(self.type())
                if not self.accept('punct', ','):
                    break
            self.expect('punct', ')')
            return tuple(types)
        t = self.peek()
        raise FuncError(f'expected type, got {t.val!r}', t.line, t.col)

    def func(self):
        pos = self.pos()
        ret = self.type()
        t = self.next()
        if t.kind not in ('id', 'method'):
            raise FuncError(f'expected function name, got {t.val!r}', t.line, t.col)
        name = t.val
        self.expect('punct', '(')
        params = []
        while not self.check('punct', ')'):
            ptype = self.type()
            pname = self.accept('id')
            params.append((ptype, pname.val if pname else None))
            if not self.accept('punct', ','):
                break
        self.expect('punct', ')')
        specs = []
        while self.check('kw') and self.peek().val in SPECS:
            specs.append(self.next().val)
        if self.accept('punct', ';'):
            return Func(ret, name, tuple(params), tuple(specs), None, pos)
        for ptype, pname in params:
            if pname is None:
                raise FuncError(f'unnamed parameter in {name}', *pos)
        return Func(ret, name, tuple(params), tuple(specs), self.block(), pos)

    # -- stmts

    def block(self):
        self.expect('punct', '{')
        body = []
        while not self.accept('punct', '}'):
            if self.check('eof'):
                self.expect('punct', '}')
            body.append(self.stmt())
        return tuple(body)

    def stmt(self):
        pos = self.pos()
        t = self.peek()
        if t.kind == 'kw':
            match t.val:
                case 'return':
                    self.next()
                    e = self.expr()
                    self.expect('punct', ';')
                    return Return(e, pos)
                case 'if' | 'ifnot':
                    self.next()
                    return self.if_rest(t.val == 'ifnot', pos)
                case 'while':
                    self.next()
                    cond = self.expr()
                    return While(cond, self.block(), pos)
                case 'repeat':
                    self.next()
                    count = self.expr()
                    return Repeat(count, self.block(), pos)
                case 'do':
                    self.next()
                    body = self.block()
                    self.expect('kw', 'until')
                    cond = self.expr()
                    self.accept('punct', ';')
                    return DoUntil(body, cond, pos)
        if self.check('punct', '{'):
            return Block(self.block(), pos)
        e = self.expr()
        self.expect('punct', ';')
        return ExprStmt(e, pos)

    def if_rest(self, neg, pos):
        cond = self.expr()
        then = self.block()
        other = ()
        p = self.pos()
        if self.accept('kw', 'else'):
            other = self.block()
        elif self.check('kw', 'elseif') or self.check('kw', 'elseifnot'):
            kw = self.next().val
            other = (self.if_rest(kw == 'elseifnot', p),)
        return If(neg, cond, then, other, pos)

    # -- exprs (pratt)

    def expr(self, min_prec=1):
        left = self.unary()
        while True:
            t = self.peek()
            if t.kind != 'op':
                return left
            pos = (t.line, t.col)
            if t.val in ASSIGN:
                if min_prec > 1:
                    return left
                self.next()
                left = Assign(t.val, left, self.expr(1), pos)
            elif t.val in BINOPS and BINOPS[t.val] >= min_prec:
                self.next()
                right = self.expr(BINOPS[t.val] + 1)
                left = BinOp(t.val, left, right, pos)
            else:
                return left

    def unary(self):
        if self.check('op', '-'):
            pos = self.pos()
            self.next()
            return Neg(self.expr(NEG_PREC), pos)
        return self.postfix(self.primary())

    def postfix(self, e):
        # x.f(..)  x~f(..)  chains: x.f().g()
        while self.check('method') and self.check('punct', '(', 1):
            t = self.next()
            e = Method(e, t.val, self.args(), (t.line, t.col))
        return e

    def args(self):
        self.expect('punct', '(')
        args = []
        while not self.check('punct', ')'):
            args.append(self.expr())
            if not self.accept('punct', ','):
                break
        self.expect('punct', ')')
        return tuple(args)

    def primary(self):
        t = self.peek()
        pos = (t.line, t.col)
        match t.kind:
            case 'num':
                self.next()
                return Num(t.val, pos)
            case 'id' | 'method':
                self.next()
                if self.check('punct', '('):
                    return Call(t.val, self.args(), pos)
                if t.kind == 'method':
                    raise FuncError(f'expected ( after {t.val}', *pos)
                return Var(t.val, pos)
            case 'kw' if t.val in ('int', 'var'):
                self.next()
                name = self.expect('id').val
                return Decl(t.val, name, pos)
            case 'punct' if t.val == '(':
                self.next()
                items = []
                while not self.check('punct', ')'):
                    items.append(self.expr())
                    if not self.accept('punct', ','):
                        break
                self.expect('punct', ')')
                if len(items) == 1:
                    return items[0]
                return Tensor(tuple(items), pos)
        got = 'end of file' if t.kind == 'eof' else repr(t.val)
        raise FuncError(f'unexpected {got}', *pos)


def parse(src):
    return Parser(src).program()
