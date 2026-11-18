import argparse

from living_architecture import doctor, twin
from living_architecture.cli import _argv, _root, _run


def _doctor(args: argparse.Namespace) -> int:
    if args.twin:
        print(twin.identity())
        return 0
    return doctor.run(
        root=_root(args.root),
        plugin=args.plugin,
        print_hash=args.contract_hash,
        require_config=args.require_config,
        require_plan_store=args.require_plan_store,
    )


def la_doctor(argv: list[str] | None = None) -> int:
    return _run("la-doctor", _argv(argv), _doctor)
