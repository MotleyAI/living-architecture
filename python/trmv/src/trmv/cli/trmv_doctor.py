import argparse

from trmv import doctor, twin
from trmv.config.command import command_argv, command_root, run_command


def _doctor(args: argparse.Namespace) -> int:
    if args.twin:
        print(twin.identity())
        return 0
    return doctor.run(
        root=command_root(args.root),
        plugin=args.plugin,
        print_hash=args.contract_hash,
        require_config=args.require_config,
    )


def trmv_doctor(argv: list[str] | None = None) -> int:
    return run_command("trmv-doctor", command_argv(argv), _doctor)
