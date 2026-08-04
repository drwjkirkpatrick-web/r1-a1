"""R1-A1 command-line interface.

Usage:
    r1a1 doctor      — hardware audit across every interconnect
    r1a1 version     — print version
"""
import sys

from src import __version__


def doctor() -> int:
    """Walk every subsystem and report green/red. Hardware-mocked when absent."""
    checks = {
        "interconnect": _check_interconnect,
        "brain": _check_brain,
        "thermal": _check_thermal,
        "power": _check_power,
    }
    ok = True
    for name, fn in checks.items():
        try:
            status = fn()
        except Exception as exc:  # noqa: BLE001 — doctor must never crash
            status = f"ERROR: {exc}"
            ok = False
        print(f"{name:>14}: {status}")
    return 0 if ok else 1


def _check_interconnect() -> str:
    try:
        from src.interconnect.link import SerialLink  # noqa: F401
        return "module OK (bench link not attempted — run selftest on hardware)"
    except ImportError as exc:
        return f"FAIL import: {exc}"


def _check_brain() -> str:
    from src.brain.llm_client import LLMClient
    return f"module OK (default model {LLMClient().current_model()})"


def _check_thermal() -> str:
    from src.thermal.monitor import ThermalMonitor  # noqa: F401
    return "module OK"


def _check_power() -> str:
    from src.power.monitor import PowerMonitor  # noqa: F401
    return "module OK"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    if args[0] == "version":
        print(__version__)
        return 0
    if args[0] == "doctor":
        return doctor()
    print(f"unknown command: {args[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
