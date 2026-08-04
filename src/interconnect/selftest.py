"""Startup selftest for the host <-> MCU interconnect.

run_selftest(link) exercises the three things we must trust before the
robot is allowed to move:

    1. heartbeat  — MCU is alive and answering frames.
    2. estop      — the hardware e-stop sense channel reports coherently
                    (a dead/unparseable channel fails the check; the link
                    itself fails safe by reporting estopped=True).
    3. echo       — full round-trip loopback: payload comes back intact,
                    proving framing + CRC on both directions.

Returns a dict {"heartbeat": bool, "estop": bool, "echo": bool} — never
raises for link faults; every failure is reported in the dict.
"""

from __future__ import annotations

from typing import Any, Dict

from .link import LinkError, SerialLink

_ECHO_TOKEN = "r1a1-selftest-echo"


def run_selftest(link: SerialLink, timeout: float = 1.0) -> Dict[str, bool]:
    """Run heartbeat / e-stop / loopback checks against the MCU.

    Never raises for link-level faults — a failed check is simply False in
    the returned dict. Raises only on programming errors (e.g. a link
    object that doesn't implement the API).
    """
    results: Dict[str, bool] = {}

    # 1. heartbeat: MCU liveness.
    try:
        results["heartbeat"] = bool(link.heartbeat(timeout=timeout))
    except LinkError:
        results["heartbeat"] = False

    # 2. estop sense channel: the check passes if we get a coherent reply.
    #    estop_sense() itself fails safe (returns True/estopped on link
    #    failure), so we distinguish "channel dead" from "actually estopped"
    #    by sending the query directly and validating the reply shape.
    try:
        link.send("estop_sense", {})
        frame = link.recv(timeout=timeout)
        payload = frame.get("payload")
        # Channel is healthy iff the payload carries an explicit boolean.
        results["estop"] = isinstance(payload, dict) and isinstance(
            payload.get("estop"), bool
        )
    except LinkError:
        results["estop"] = False

    # 3. loopback echo: payload must come back byte-identical.
    try:
        results["echo"] = bool(link.echo(_ECHO_TOKEN, timeout=timeout))
    except LinkError:
        results["echo"] = False

    return results
