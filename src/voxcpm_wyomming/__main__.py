"""CLI entrypoint for the VoxCPM Wyoming service."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import Sequence

from .adapter import NanovllmVoxCPMAdapter
from .config import build_arg_parser, config_from_args
from .service import VoxCPMWyomingService


async def _run_service(argv: Sequence[str] | None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        config = config_from_args(args)
    except ValueError as err:
        parser.print_usage(sys.stderr)
        print(f"{parser.prog}: error: {err}", file=sys.stderr)
        raise SystemExit(2) from err

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    service = VoxCPMWyomingService(config, adapter_factory=NanovllmVoxCPMAdapter)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # pragma: no cover - platform dependent
            pass

    await service.start()
    logging.info("VoxCPM Wyoming service listening on %s", config.uri)

    try:
        await stop_event.wait()
    finally:
        await service.stop()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the VoxCPM Wyoming TCP service."""
    try:
        asyncio.run(_run_service(argv))
    except SystemExit as err:
        code = int(err.code) if err.code is not None else 1
        return code
    except KeyboardInterrupt:
        return 0
    except RuntimeError as err:
        logging.error("Service failed to start: %s", err)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
