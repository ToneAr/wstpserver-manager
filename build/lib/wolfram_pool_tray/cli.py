from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .service import ServiceError, get_service_manager


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args, remaining = parser.parse_known_args(raw_args)

    service_command = args.install_service or args.uninstall_service or args.service_status
    if service_command and remaining:
        parser.error(f"unrecognized arguments: {' '.join(remaining)}")
    if not args.install_service and (args.wstpserver_bin or args.kernel_bin):
        parser.error("--wstpserver-bin and --kernel-bin can only be used with --install-service")

    if args.install_service:
        return _install_service(args)
    if args.uninstall_service:
        return _uninstall_service()
    if args.service_status:
        return _service_status()

    from .app import main as gui_main

    if argv is None:
        return gui_main()
    return gui_main([sys.argv[0], *raw_args])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WSTPServer Manager")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    command_group = parser.add_mutually_exclusive_group()
    command_group.add_argument("--install-service", action="store_true", help="install and start the platform WSTPServer service")
    command_group.add_argument("--uninstall-service", action="store_true", help="remove the platform WSTPServer service")
    command_group.add_argument("--service-status", action="store_true", help="print the platform WSTPServer service status")
    parser.add_argument("--start-hidden", "--background", action="store_true", help="start the tray app without opening the main window")
    parser.add_argument("--wstpserver-bin", type=Path, help="path to wstpserver/wstpserver.exe for service installation")
    parser.add_argument("--kernel-bin", type=Path, help="path to WolframKernel/wolfram.exe for service installation")
    return parser


def _install_service(args: argparse.Namespace) -> int:
    manager = get_service_manager()
    try:
        print(manager.install(wstpserver_bin=args.wstpserver_bin, kernel_bin=args.kernel_bin))
    except ServiceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _uninstall_service() -> int:
    manager = get_service_manager()
    try:
        print(manager.uninstall())
    except ServiceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _service_status() -> int:
    manager = get_service_manager()
    try:
        status = manager.status()
    except ServiceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"installed={_format_bool(status.installed)}")
    print(f"running={_format_bool(status.running)}")
    print(f"enabled={_format_bool(status.enabled)}")
    print(f"detail={status.detail}")
    if status.kernel_process_count is not None:
        print(f"kernel_process_count={status.kernel_process_count}")
    return 0


def _format_bool(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"
