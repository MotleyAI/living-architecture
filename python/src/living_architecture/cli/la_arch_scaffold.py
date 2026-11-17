from living_architecture import archcheck
from living_architecture.cli import _argv, _root, _run


def la_arch_scaffold(argv: list[str] | None = None) -> int:
    return _run("la-arch-scaffold", _argv(argv), lambda args: archcheck.run_scaffold(_root(args.root)))
