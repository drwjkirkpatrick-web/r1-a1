"""R1-A1 command-line interface.

Usage:
    r1a1 doctor      — hardware audit across every interconnect
    r1a1 version     — print version
    r1a1 dashboard   — start the web dashboard on :9298
    r1a1 config      — show current config from config/r1a1.yaml
    r1a1 chat        — interactive REPL with the brain agent
    r1a1 selftest    — bench link check against the MCU (needs hardware)
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
        "motion": _check_motion,
        "awareness": _check_awareness,
        "eye": _check_eye,
        "hermes_node": _check_hermes_node,
        "comms": _check_comms,
        "personality": _check_personality,
        "limbic": _check_limbic,
        "dashboard": _check_dashboard,
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


def _check_motion() -> str:
    from src.motion import Drive, Dome, CenterLeg, Express  # noqa: F401
    return "module OK"


def _check_awareness() -> str:
    from src.awareness.fusion import AwarenessFusion  # noqa: F401
    try:
        from src.awareness.watchdog import Watchdog  # noqa: F401
        return "module OK (fusion + watchdog)"
    except ImportError:
        return "module OK (fusion)"


def _check_eye() -> str:
    from src.eye.camera import EyeCamera  # noqa: F401
    from src.eye.wink import Wink  # noqa: F401
    return "module OK"


def _check_hermes_node() -> str:
    try:
        from src.hermesnode import HermesNode  # noqa: F401
    except ImportError:
        return "module MISSING (hermesnode not installed)"
    # Offline probe — doctor never blocks on a network call to the dome
    # node; we only verify the module imports and can be constructed.
    node = HermesNode()
    return f"module OK (node id {node.node_id}, target {node.base_url})"


def _check_comms() -> str:
    try:
        from src.comms import CommsStack  # noqa: F401
    except ImportError:
        return "module MISSING (comms not installed)"
    stack = CommsStack()
    wan = stack.wan_status()
    return f"module OK (wan: {wan['active']})"


def _check_personality() -> str:
    from src.brain.personality import PersonalityBridge
    bridge = PersonalityBridge("bryonia_alba")
    available = PersonalityBridge.list_remedies()
    if available:
        return f"module OK ({len(available)} remedies available)"
    return "module OK (skill not installed — running neutral)"


def _check_limbic() -> str:
    from src.brain.limbic import LimbicBridge
    bridge = LimbicBridge(enabled=True)
    info = bridge.info()
    if info.get("available"):
        return f"module OK (profile {info.get('profile', '?')})"
    return "module OK (limbic-hermes not installed — running flat affect)"


def _check_dashboard() -> str:
    try:
        import flask  # noqa: F401
        return "module OK (Flask available)"
    except ImportError:
        return "module OK (Flask not installed — install with: pip install flask)"


def _start_dashboard() -> int:
    """Start the web dashboard."""
    from src.dashboard import DashboardServer
    server = DashboardServer()
    print(f"R1-A1 dashboard starting on http://{server.host}:{server.port}")
    server.run()
    return 0


def _show_config() -> int:
    """Print the current config."""
    import os
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "r1a1.yaml"
    )
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1
    with open(config_path) as f:
        print(f.read())
    return 0


def _chat() -> int:
    """Interactive REPL with the brain agent (Ctrl-D / 'quit' to exit).

    Learning: before this, the only way to exercise the Agent was a
    unit test or the dashboard — there was no user-facing path to
    actually talk to the robot from the host shell.
    """
    from src.brain.agent import Agent

    agent = Agent()
    print(f"R1-A1 brain online (model: {agent.llm.current_model()}).")
    print("Type 'quit' or Ctrl-D to exit.")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in {"quit", "exit"}:
            break
        print(f"r1a1> {agent.handle(line)}")
    return 0


def _selftest() -> int:
    """Run the interconnect selftest against a live MCU."""
    from src.interconnect.link import SerialLink
    from src.interconnect.selftest import run_selftest

    port = "/dev/ttyACM0"
    if len(sys.argv) > 2:
        port = sys.argv[2]
    print(f"Running interconnect selftest on {port} ...")
    try:
        with SerialLink(port) as link:
            results = run_selftest(link)
    except Exception as exc:
        print(f"selftest failed to open link: {exc}", file=sys.stderr)
        return 1
    for name, ok in results.items():
        print(f"  {name:>10}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(results.values()) else 1


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
    if args[0] == "dashboard":
        return _start_dashboard()
    if args[0] == "config":
        return _show_config()
    if args[0] == "chat":
        return _chat()
    if args[0] == "selftest":
        return _selftest()
    print(f"unknown command: {args[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())