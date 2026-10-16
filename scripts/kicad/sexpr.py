"""Read and write the S-expressions KiCad stores its files in.

Small on purpose. Atoms are kept as the exact text that appeared in the file,
so a quoted string stays quoted and a number keeps its spelling, which means a
library symbol read from KiCad's own library can be written back into a
schematic unchanged. Generated text goes through :func:`q` for strings and
:func:`num` for numbers.

Standard library only, so it runs on the host and inside the KiCad container.
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r'\s*(\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+)')


def parse(text: str) -> list:
    """Every top level expression in ``text``, as nested lists of atoms."""
    stack: list[list] = [[]]
    for m in _TOKEN.finditer(text):
        tok = m.group(1)
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(tok)
    if len(stack) != 1:
        raise ValueError("unbalanced parentheses")
    return stack[0]


def q(text: str) -> str:
    """A quoted string atom."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def unq(atom: str) -> str:
    """The text inside a quoted atom, or the atom itself if it is bare."""
    if len(atom) >= 2 and atom[0] == '"' and atom[-1] == '"':
        return atom[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    return atom


def num(x: float) -> str:
    """A number the way KiCad writes one: no exponent, no trailing zeros."""
    text = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def dumps(expr, indent: int = 0) -> str:
    """Tab indented, one child list per line, atoms kept on the parent line."""
    if not isinstance(expr, list):
        return expr
    pad = "\t" * indent
    atoms = []
    i = 0
    while i < len(expr) and not isinstance(expr[i], list):
        atoms.append(expr[i])
        i += 1
    rest = expr[i:]
    if not rest:
        return pad + "(" + " ".join(atoms) + ")"
    lines = [pad + "(" + " ".join(atoms)]
    for child in rest:
        if isinstance(child, list):
            lines.append(dumps(child, indent + 1))
        else:
            lines.append("\t" * (indent + 1) + child)
    lines.append(pad + ")")
    return "\n".join(lines)


def find(expr: list, head: str) -> list | None:
    """The first child list whose head atom is ``head``."""
    for child in expr:
        if isinstance(child, list) and child and child[0] == head:
            return child
    return None


def find_all(expr: list, head: str) -> list[list]:
    return [c for c in expr if isinstance(c, list) and c and c[0] == head]
