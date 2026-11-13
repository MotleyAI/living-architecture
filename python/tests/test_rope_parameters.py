"""rope's function model with every parameter kind: positional binding, scope, objects and keyword lookup."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from rope.base import arguments, builtins, evaluate, libutils, pynames
from rope.base.project import Project
from rope.base.pyobjects import PyObject
from rope.base.pyobjectsdef import PyClass, PyFunction, PyModule

from living_architecture.refactor import rope_patches

SIGNATURES = [
    pytest.param("def f(a, /, b, *xs, c=0, **kw): pass\n", ["a", "b", "xs", "kw"], ["a", "b"], id="every-kind"),
    pytest.param("def f(a, /): pass\n", ["a"], ["a"], id="positional-only"),
    pytest.param("def f(b): pass\n", ["b"], ["b"], id="positional-or-keyword"),
    pytest.param("def f(*, c): pass\n", [], [], id="keyword-only"),
    pytest.param("def f(*xs): pass\n", ["xs"], [], id="args"),
    pytest.param("def f(**kw): pass\n", ["kw"], [], id="kwargs"),
]

CLASSES = "class A: pass\nclass B: pass\nclass C: pass\nclass D: pass\nclass X: pass\n"


@pytest.fixture
def module(tmp_path: Path):
    rope_patches.apply_rope_patches()
    # rope documents `ropefolder=None` (no rope folder); its signature infers `str` from the default.
    project = Project(str(tmp_path), ropefolder=None)  # pyright: ignore[reportArgumentType]
    yield lambda source: libutils.get_string_module(project, source)
    project.close()


def _function(mod: PyModule, *path: str) -> PyFunction:
    obj = mod[path[0]].get_object()
    for name in path[1:]:
        obj = obj[name].get_object()
    assert isinstance(obj, PyFunction)
    return obj


def _type(obj: PyObject | None) -> str | None:
    """`type[K]` for class `K`, `K` for its instance, `list`/`dict` for rope's builtins, None when unknown."""
    if obj is None:
        return None
    if isinstance(obj, PyClass):
        return f"type[{obj.get_name()}]"
    kind = obj.get_type()
    if isinstance(kind, builtins.List):
        return "list"
    if isinstance(kind, builtins.Dict):
        return "dict"
    return kind.get_name() if isinstance(kind, PyClass) else None


def _objects(fn: PyFunction) -> dict[str, str | None]:
    return {name: _type(pyname.get_object()) for name, pyname in fn.get_parameters().items()}


@pytest.mark.parametrize(("source", "with_special", "without_special"), SIGNATURES)
def test_positional_binding_vector(module, source: str, with_special: list[str], without_special: list[str]) -> None:
    fn = _function(module(source), "f")
    assert fn.get_param_names() == with_special
    assert fn.get_param_names(special_args=False) == without_special


@pytest.mark.parametrize(
    ("source", "names"),
    [
        ("def f(a, /, b, *xs, c=0, **kw): pass\n", {"a", "b", "xs", "c", "kw"}),
        ("def f(a, /): pass\n", {"a"}),
        ("def f(b): pass\n", {"b"}),
        ("def f(*, c): pass\n", {"c"}),
        ("def f(*xs): pass\n", {"xs"}),
        ("def f(**kw): pass\n", {"kw"}),
        ("async def f(a, /, *, c): pass\n", {"a", "c"}),
    ],
    ids=["every-kind", "positional-only", "positional-or-keyword", "keyword-only", "args", "kwargs", "async"],
)
def test_parameters_hold_every_kind(module, source: str, names: set[str]) -> None:
    assert set(_function(module(source), "f").get_parameters()) == names


@pytest.mark.parametrize(
    "call",
    ["f(A(), B(), X(), c=C(), d=D())", "f(A(), b=B())", "f(A(), B(), a=X())"],
    ids=["positional-then-keywords", "keyword-for-positional-or-keyword", "keyword-named-like-positional-only"],
)
def test_call_arguments_bind_their_parameters(module, call: str) -> None:
    mod = module(f"{CLASSES}def f(a, /, b, *xs, c=0, **kw): pass\n{call}\n")
    fn = _function(mod, "f")
    node = mod.get_ast().body[-1]
    assert isinstance(node, ast.Expr)
    assert isinstance(node.value, ast.Call)
    params = fn.get_param_names(special_args=False)
    bound = arguments.create_arguments(None, fn, node.value, mod.get_scope()).get_arguments(params)
    assert {name: _type(obj) for name, obj in zip(params, bound)} == {"a": "A", "b": "B"}


def test_returned_positional_only_argument_ignores_a_same_named_keyword(module) -> None:
    mod = module(f"{CLASSES}def identity(value, /, **kw):\n    return value\nx = identity(A(), value=B())\n")
    assert _type(mod["x"].get_object()) == "A"


@pytest.mark.parametrize("call", ["f(value=B())", "f(other=B())"], ids=["positional-only-name", "captured-keyword"])
def test_a_keyword_takes_no_positional_slot(module, call: str) -> None:
    mod = module(f"{CLASSES}def f(value, /, **kw):\n    return value\nx = {call}\n")
    assert _type(mod["x"].get_object()) is None


def test_parameter_objects_of_every_kind(module) -> None:
    source = (
        f"{CLASSES}"
        "def f(a, /, b, *xs, c, d=0, **kw):\n"
        '    """\n    :type a: A\n    :type b: B\n    :type c: C\n    """\n'
    )
    assert _objects(_function(module(source), "f")) == {
        "a": "A", "b": "B", "xs": "list", "c": "C", "d": None, "kw": "dict"
    }


METHODS = f"""{CLASSES}
class K:
    def plain(self, b, *, c):
        \"\"\"
        :type b: B
        :type c: C
        \"\"\"

    def posonly_self(self, /, b, *, c):
        \"\"\"
        :type b: B
        :type c: C
        \"\"\"

    @classmethod
    def cm(cls, a, /, b, *, c):
        \"\"\"
        :type a: A
        :type b: B
        :type c: C
        \"\"\"

    @staticmethod
    def sm(a, /, *, c):
        \"\"\"
        :type a: A
        :type c: C
        \"\"\"
"""


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("plain", {"self": "K", "b": "B", "c": "C"}),
        ("posonly_self", {"self": "K", "b": "B", "c": "C"}),
        ("cm", {"cls": "type[K]", "a": "A", "b": "B", "c": "C"}),
        ("sm", {"a": "A", "c": "C"}),
    ],
)
def test_receivers_bind_the_first_parameter(module, method: str, expected: dict[str, str | None]) -> None:
    assert _objects(_function(module(METHODS), "K", method)) == expected


@pytest.mark.parametrize(
    ("keyword", "resolves"),
    [("a", False), ("b", True), ("args", False), ("c", True), ("kwargs", False)],
    ids=["positional-only", "positional-or-keyword", "args", "keyword-only", "kwargs"],
)
def test_keyword_lookup_resolves_only_keyword_bindable_parameters(module, keyword: str, resolves: bool) -> None:
    source = "def f(a, /, b, *args, c, **kwargs): pass\nf(1, a=2, b=3, args=4, c=5, kwargs=6)\n"
    mod = module(source)
    pyname = evaluate.eval_location(mod, source.rindex(f"{keyword}="))
    if resolves:
        assert isinstance(pyname, pynames.ParameterName)
        assert pyname is _function(mod, "f").get_parameters()[keyword]
    else:
        assert pyname is None


@pytest.mark.parametrize("name", ["a", "b", "c"], ids=["positional-only", "positional-or-keyword", "keyword-only"])
def test_defaulted_header_parameter_resolves_to_its_parameter(module, name: str) -> None:
    source = "def f(a=0, /, b=0, *, c=0): pass\n"
    mod = module(source)
    assert evaluate.eval_location(mod, source.index(f"{name}=")) is _function(mod, "f").get_parameters()[name]


LAMBDAS = "def f(p, q):\n    g = lambda p, *, r=q: (p, r, q)\n    h = lambda: p\n    return g, h, p\n"


@pytest.mark.parametrize(
    ("needle", "shift", "owner"),
    [
        ("lambda p", 7, None),
        ("r=q", 0, None),
        ("(p, r", 1, None),
        (", r, ", 2, None),
        ("=q", 1, "q"),
        (", q)", 2, "q"),
        ("lambda: p", 8, "p"),
        ("h, p", 3, "p"),
    ],
    ids=[
        "lambda-parameter", "lambda-keyword-only", "lambda-use", "lambda-keyword-only-use", "lambda-default",
        "outer-use-in-lambda", "parameterless-lambda", "outer-use",
    ],
)
def test_names_a_lambda_binds_resolve_to_nothing(module, needle: str, shift: int, owner: str | None) -> None:
    mod = module(LAMBDAS)
    pyname = evaluate.eval_location(mod, LAMBDAS.index(needle) + shift)
    assert pyname is (None if owner is None else _function(mod, "f").get_parameters()[owner])


def test_keyword_of_an_unresolved_call_resolves_to_nothing(module) -> None:
    source = "def f(model_name):\n    return unknown(model_name=model_name)\n"
    assert evaluate.eval_location(module(source), source.index("model_name=")) is None


# Canary: drop the parameter patch when rope's function model lists positional-only and keyword-only parameters.
def test_unpatched_rope_still_omits_positional_only_and_keyword_only_parameters(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        "from rope.base import libutils\n"
        "from rope.base.project import Project\n"
        "mod = libutils.get_string_module(Project(sys.argv[1], ropefolder=None), 'def f(a, /, b, *, c): pass\\n')\n"
        "print(sorted(mod['f'].get_object().get_parameters()))\n"
    )
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, check=False)
    assert (result.returncode, result.stdout) == (0, "['b']\n"), result.stderr
