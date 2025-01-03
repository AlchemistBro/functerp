import re
from pathlib import Path
import pytest
from src.lexer import tokenize, FuncError
from src.interp import run

PROGRAMS = sorted(Path(__file__).parent.glob('programs/*.fc'))
EXAMPLES = sorted((Path(__file__).parent.parent / 'examples').glob('*.fc'))


def execute(src):
    out = []
    try:
        run(src, out.append)
    except FuncError as e:
        out.append(f'error: {e}')
    return out


@pytest.mark.parametrize('path', PROGRAMS, ids=lambda p: p.stem)
def test_program(path):
    src = path.read_text(encoding='utf-8')
    expected = re.search(r'\{- out:\n(.*?)-\}\s*$', src, re.S).group(1)
    assert execute(src) == expected.splitlines()


@pytest.mark.parametrize('path', EXAMPLES, ids=lambda p: p.stem)
def test_example_runs(path):
    out = execute(path.read_text(encoding='utf-8'))
    assert not out[-1].startswith('error')


ERRORS = [
    ('int main() { return x; }', '1:21: undefined variable x'),
    ('int main() { return f(); }', '1:21: undefined function f'),
    ('int f(int a) { return a; } int main() { return f(1, 2); }',
     '1:48: f takes 1 args, got 2'),
    # must be declared before use, like in FunC
    ('int main() { return f(); } int f() { return 1; }', '1:21: undefined function f'),
    ('int f(); int main() { return f(); }', '1:30: function f is declared but not defined'),
    ('const A = 1; int main() { A = 2; return A; }', '1:27: cannot assign to constant A'),
    ('int main() { int a = 1; return a+1; }', '1:32: undefined variable a+1'),
    ('int main() { return 1 }', "1:23: expected ';', got '}'"),
    ('{- int main() {}', '1:1: unclosed comment'),
    ('int main() { (int a, int b) = (1, 2, 3); return a; }',
     '1:14: cannot unpack (1, 2, 3) into 2 values'),
    ('(int, int) f(int x) { return (x, x); } int main() { return 5~f(); }',
     '1:61: ~f needs a variable on the left'),
    ('int main() { }', '1:1: main ended without return'),
    ('() main() { int x = 1; }', None),
]


@pytest.mark.parametrize('src, err', ERRORS)
def test_errors(src, err):
    out = execute(src)
    if err is None:
        assert out == []
    else:
        assert out == [f'error: {err}']


def test_tokens():
    toks = tokenize('x+y x + -7 0x1F s~pop() .f ~ a ;; c\n{- a {- b -} -}')
    assert [(t.kind, t.val) for t in toks] == [
        ('id', 'x+y'), ('id', 'x'), ('op', '+'), ('num', -7), ('num', 31),
        ('id', 's'), ('method', '~pop'), ('punct', '('), ('punct', ')'),
        ('method', '.f'), ('op', '~'), ('id', 'a'), ('eof', None),
    ]
