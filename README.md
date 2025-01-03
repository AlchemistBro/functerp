# functerp

Tiny interpreter of a FunC subset (TON smart contracts language) in Python.
Hand-written lexer and Pratt parser, no parsing libs, no dependencies.

## How to use:

```
./functerp examples/stack.fc
./functerp examples/stack.fc --ast    # AST after desugar
```

Python 3.10+. On Windows: `python functerp examples/stack.fc`.

## Example:

```C
{-
    Stack of digits packed into one int.
    `~` calls write the new value back into the variable.
-}

const BASE = 10;

int push(int s, int x) {
    return s * BASE + x;
}

(int, int) ~pop(int s) {
    return (s / BASE, s - s / BASE * BASE);
}

int is_empty(int s) {
    return s == 0;
}

(int, int) main() {
    int s = 0;
    s = s.push(3).push(4).push(5);
    int top = s~pop();
    int sum = 0;
    while (~ is_empty(s)) {
        sum += s~pop();
    }
    return (top, sum);
}
```

Output:

```
> ./functerp examples/stack.fc
result: (5, 7)
```

## What is FunC here

Not a C-like language with FunC syntax, but FunC rules:

* **`.` and `~` calls.** `x.f(y)` is `f(x, y)`. `x~f(y)` calls `f(x, y)`, which returns `(new_x, result)`, writes `new_x` back to `x` and gives `result`. `x~f` looks for `~f` first, `x.f` looks for `.f` first, then plain `f`. Done as a desugar pass before running.
* **`impure`.** A call of a function without `impure` whose result is unused is removed, like the FunC compiler does. The classic trap:

  ```C
  () check(int x) {          ;; forgot impure
      throw_if(100, x < 0);
  }
  ...
  check(-1);                 ;; removed, no exception!
  ```
* **`/` rounds to -inf**: `-7 / 2 == -4`.
* **true is -1**, false is 0. So `~` is both bitwise and logical not: `~ (1 < 2) == 0`.
* **257-bit int.** Overflow and division by zero throw exit code 4, like TVM.
* **Operators need spaces.** `x+y` is one identifier, `x + y` is addition.
* **FunC precedence.** `&` is on the `*` level, `|` on the `+` level, unary `-` is below `*`: `- a * b` is `-(a * b)`.
* **Declare before use.** A function must be defined or forward declared (`int f(int x);`) before it is called.
* Tensors: `(int, int) f()`, `(int a, int b) = f();`, nested `((int a, int b), int c)`.
* `{- nested {- comments -} -}`, `;;` comments.

## Subset

`int`, `var`, `const`, functions, recursion, tensors, `if` / `ifnot` / `elseif` / `elseifnot` / `else`, `while`, `repeat`, `do ... until`, `+ - * / & | ~`, comparisons, `+= -= *= /= &= |=`.

Builtins: `~dump(x)` (prints `#DEBUG#: s0 = x`, like TVM `DUMP`), `throw`, `throw_if`, `throw_unless`, `min`, `max`, `abs`.

No `cell` / `slice` / `builder`, no `global`, no `#include`, no `asm` functions.

## Tests:

```
pip install pytest
python -m pytest
```

Golden programs are in `tests/programs`, expected output is in the `{- out: ... -}` block at the end of each file.

## Roadmap:

* `%`, `^/`, `~/`, `<< >>`, `?:`, `<=>`
* `global`, `#include`, `asm` functions
* check results against the real FunC compiler and TVM
