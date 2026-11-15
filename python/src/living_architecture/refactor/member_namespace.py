"""A member rename's class namespace: the members of the new name its class, every ancestor (library bases and the
implicit root included) and every project descendant declare."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator

from pydantic import BaseModel, ConfigDict
from rope.base import evaluate
from rope.base.project import Project
from rope.base.pyobjects import PyObject
from rope.base.pyobjectsdef import PyClass, PyModule
from rope.base.pyscopes import Scope as RopeScope

from living_architecture.contract import language
from living_architecture.refactor.bindings import Conflict, Site
from living_architecture.refactor.members import classes, member_declarations
from living_architecture.refactor.python_source import SourceFile

# A project class: its file and the line of its `class` statement.
ClassKey = tuple[str, int]


class RenamedMember(BaseModel):
    """A member declaration a map entry renames: the entry, its new name, the declaration's site and its class."""

    model_config = ConfigDict(frozen=True)

    entry: int
    new_name: str
    site: Site
    cls: ClassKey


def _class_scopes(scope: RopeScope) -> Iterator[RopeScope]:
    for child in scope.get_scopes():
        if isinstance(child.pyobject, PyClass):
            yield child
        yield from _class_scopes(child)


class Hierarchy:
    """Project classes and their ancestors, as rope evaluates their bases."""

    def __init__(self, project: Project, files: list[str], source: Callable[[str], SourceFile]) -> None:
        self.project = project
        self.files = set(files)
        self.source = source
        self.root_members = frozenset(language("python")["root_members"])
        self._pyclasses: dict[str, dict[int, PyClass]] = {}
        self._bases: dict[ClassKey, tuple[list[ClassKey], list[PyObject]]] = {}

    def node(self, key: ClassKey) -> ast.ClassDef | None:
        tree = self.source(key[0]).tree
        return next((c for c in classes(tree) if c.lineno == key[1]), None) if tree is not None else None

    def _pyclass(self, key: ClassKey) -> PyClass | None:
        rel, line = key
        if rel not in self._pyclasses:
            scope = self.project.get_pymodule(self.project.get_resource(rel)).get_scope()
            found = _class_scopes(scope) if scope is not None else iter(())
            self._pyclasses[rel] = {s.pyobject.get_ast().lineno: s.pyobject for s in found}
        return self._pyclasses[rel].get(line)

    def _key(self, obj: PyObject) -> ClassKey | None:
        """A project class's key; None for a library class."""
        if not isinstance(obj, PyClass):
            return None
        module = obj.get_module()
        resource = module.get_resource() if isinstance(module, PyModule) else None
        return (resource.path, obj.get_ast().lineno) if resource is not None and resource.path in self.files else None

    def bases(self, key: ClassKey) -> tuple[list[ClassKey], list[PyObject]]:
        """A project class's direct bases: project classes, then library classes."""
        if key not in self._bases:
            project: list[ClassKey] = []
            library: list[PyObject] = []
            pyclass = self._pyclass(key)
            scope = pyclass.get_scope() if pyclass is not None else None
            for base in pyclass.get_ast().bases if pyclass is not None and scope is not None else []:
                expr = base.value if isinstance(base, ast.Subscript) else base
                pyname = evaluate.eval_node(scope.parent, expr) if scope is not None else None
                obj = pyname.get_object() if pyname is not None else None
                if obj is None:
                    continue
                found = self._key(obj)
                if found is not None:
                    project.append(found)
                else:
                    library.append(obj)
            self._bases[key] = (project, library)
        return self._bases[key]

    def ancestors(self, key: ClassKey) -> tuple[list[ClassKey], list[PyObject]]:
        """Every project and library ancestor of a project class."""
        seen: list[ClassKey] = []
        library: list[PyObject] = []
        todo = [key]
        while todo:
            current = todo.pop()
            project, libs = self.bases(current)
            library += libs
            for base in project:
                if base not in seen and base != key:
                    seen.append(base)
                    todo.append(base)
        return seen, library

    def declarations(self, key: ClassKey, name: str) -> list[Site]:
        """The sites of member `name` a project class declares."""
        node = self.node(key)
        source = self.source(key[0])
        spans = (source.name_span(n) for n in (member_declarations(node, name) if node is not None else []))
        return [(key[0], span[0]) for span in spans if span is not None]


class MemberCheck:
    """Refuses a member renamed onto a name its class's namespace already holds."""

    def __init__(self, hierarchy: Hierarchy, text: Callable[[str], str]) -> None:
        self.hierarchy = hierarchy
        self.text = text

    def _descendants(self, key: ClassKey, name: str) -> list[ClassKey]:
        """The project classes declaring member `name` that have `key` among their ancestors."""
        word = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
        out: list[ClassKey] = []
        for rel in sorted(self.hierarchy.files):
            if not word.search(self.text(rel)):
                continue
            tree = self.hierarchy.source(rel).tree
            for cls in classes(tree) if tree is not None else ():
                other = (rel, cls.lineno)
                if other != key and member_declarations(cls, name) and key in self.hierarchy.ancestors(other)[0]:
                    out.append(other)
        return out

    def conflicts(self, renamed: list[RenamedMember], renamed_sites: set[Site]) -> list[Conflict]:
        """The sites refusing each renamed member; `renamed_sites` are every declaration the renames rename."""
        out: list[Conflict] = []
        for member in renamed:
            name = member.new_name
            ancestors, library = self.hierarchy.ancestors(member.cls)
            family = [member.cls, *ancestors, *self._descendants(member.cls, name)]
            existing = [s for key in family for s in self.hierarchy.declarations(key, name) if s not in renamed_sites]
            out += [Conflict(site=s, name=name) for s in existing]
            met = [m for m in renamed if m.entry != member.entry and m.new_name == name and m.cls in family]
            if met:
                earliest = min([member, *met], key=lambda m: (m.entry, m.site))
                first = min(m.site for m in renamed if m.entry == earliest.entry)
                out.append(Conflict(site=first, name=name))
            if name in self.hierarchy.root_members or any(name in obj.get_attributes() for obj in library):
                out.append(Conflict(site=member.site, name=name))
        return out
