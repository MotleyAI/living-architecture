from living_architecture import c4
from living_architecture.cli import _argv, _root, _run


def la_arch_migrate(argv: list[str] | None = None) -> int:
    return _run("la-arch-migrate", _argv(argv), lambda args: c4.run_migrate(_root(args.root)))
