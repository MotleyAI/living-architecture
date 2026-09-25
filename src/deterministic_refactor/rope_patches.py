"""Runtime fixes for rope bugs that break refactors on valid code.

rope <= 1.14 ``_PatchingASTWalker._arguments`` ignores ``posonlyargs``,
``kwonlyargs`` and ``kw_defaults``, so those signature regions are never
consumed; the walker's next token search (e.g. the signature's ``)``) can then
match inside a default or docstring string — ``def f(*, m: str = "(host)")``
raises MismatchedTokenError. Patched to walk the full signature grammar.
"""

from __future__ import annotations

from rope.refactor import patchedast


def _arguments(self, node):
    children: list = []

    def sep() -> None:
        if children:
            children.append(",")

    posonly = list(getattr(node, "posonlyargs", []))
    args = posonly + list(node.args)
    defaults = [None] * (len(args) - len(node.defaults)) + list(node.defaults)
    for index, (arg, default) in enumerate(zip(args, defaults)):
        sep()
        self._add_args_to_children(children, arg, default)
        if posonly and index == len(posonly) - 1:
            children.extend([",", "/"])
    if node.vararg is not None or node.kwonlyargs:
        sep()
        children.append("*")
        if node.vararg is not None:
            children.append(node.vararg.arg)
    for arg, default in zip(node.kwonlyargs, node.kw_defaults):
        sep()
        self._add_args_to_children(children, arg, default)
    if node.kwarg is not None:
        sep()
        children.extend(["**", node.kwarg.arg])
    self._handle(node, children)


def apply_rope_patches() -> None:
    patchedast._PatchingASTWalker._arguments = _arguments
