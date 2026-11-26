import argparse

from living_architecture import doctor
from living_architecture.config import run_command
from living_architecture.contract import identity
from trmv import twin
from trmv.config.command import command_argv, command_root


def _doctor(args: argparse.Namespace) -> int:
    if args.twin:
        print(twin.identity(identity()))
        return 0
    return doctor.run(
        root=command_root(args.root),
        plugin=args.plugin,
        print_hash=args.contract_hash,
        require_config=args.require_config,
        require_plan_store=args.require_plan_store,
    )


def la_doctor(argv: list[str] | None = None) -> int:
    return run_command("la-doctor", command_argv(argv), _doctor)
