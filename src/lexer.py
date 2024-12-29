import re
from dataclasses import dataclass


class FuncError(Exception):
    def __init__(self, msg, line, col):
        super().__init__(f'{line}:{col}: {msg}')
        self.msg = msg
        self.line = line
        self.col = col


@dataclass
class Token:
    kind: str  # num, id, method, kw, op, punct, eof
    val: object
    line: int
    col: int


KEYWORDS = {
    'int', 'var', 'const', 'return',
    'if', 'ifnot', 'else', 'elseif', 'elseifnot',
    'while', 'repeat', 'do', 'until',
    'impure', 'inline', 'inline_ref',
}

OPS = {
    '+', '-', '*', '/', '&', '|',
    '==', '!=', '<', '>', '<=', '>=',
    '=', '+=', '-=', '*=', '/=', '&=', '|=',
}

PUNCT = set('()[]{},;')

# in FunC an identifier is anything without spaces and ;,()[]~.
# so `x+y` is one identifier, operators need spaces around
WORD = re.compile(r'[^\s;,()\[\]{}~.]+')
NUM = re.compile(r'-?(0x[0-9a-fA-F]+|[0-9]+)$')


def tokenize(src):
    toks = []
    i, line, col = 0, 1, 1

    def move(n):
        nonlocal i, line, col
        for c in src[i:i + n]:
            if c == '\n':
                line, col = line + 1, 1
            else:
                col += 1
        i += n

    while i < len(src):
        c = src[i]
        if c.isspace():
            move(1)
        elif src.startswith(';;', i):
            end = src.find('\n', i)
            move((len(src) if end == -1 else end) - i)
        elif src.startswith('{-', i):
            # {- -} comments can be nested
            start_line, start_col = line, col
            depth = 0
            while True:
                if i >= len(src):
                    raise FuncError('unclosed comment', start_line, start_col)
                if src.startswith('{-', i):
                    depth += 1
                    move(2)
                elif src.startswith('-}', i):
                    depth -= 1
                    move(2)
                    if depth == 0:
                        break
                else:
                    move(1)
        elif c in PUNCT:
            toks.append(Token('punct', c, line, col))
            move(1)
        elif c in '.~':
            m = WORD.match(src, i + 1)
            if not m and c == '~':
                # `~ x` is bitwise not, `~f` is a name
                toks.append(Token('op', '~', line, col))
                move(1)
                continue
            if not m:
                raise FuncError(f'expected name after {c!r}', line, col)
            toks.append(Token('method', c + m.group(), line, col))
            move(1 + len(m.group()))
        else:
            m = WORD.match(src, i)
            if not m:
                raise FuncError(f'unexpected {c!r}', line, col)
            w = m.group()
            toks.append(Token(word_kind(w), word_val(w), line, col))
            move(len(w))
    toks.append(Token('eof', None, line, col))
    return toks


def word_kind(w):
    if NUM.match(w):
        return 'num'
    if w in KEYWORDS:
        return 'kw'
    if w in OPS:
        return 'op'
    return 'id'


def word_val(w):
    if NUM.match(w):
        neg = w.startswith('-')
        w = w.lstrip('-')
        n = int(w[2:], 16) if w.startswith('0x') else int(w)
        return -n if neg else n
    return w
