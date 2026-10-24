"""ToolBay: the astromech's weight-limited tool rack and selection logic.

The bay enforces two real constraints of the physical robot:

    max_weight_kg   the utility rack sits ahead of the drive motors;
                    overloading it shifts the center of gravity forward
                    and the dome tips on hard braking
    one of each     the rack has one slot per tool type

Selection heuristic (select_tool): among tools that service the target
subsystem, prefer the highest-condition operational tool — wear, not
charge, is what makes a weld fail mid-repair. Urgency (0..1) relaxes
the charge reserve: routine work keeps RESERVE_CHARGE_PCT in the tank
so the tool can stow itself afterward; a full emergency (urgency=1.0)
drains to the last percent.

service_plan() spreads a multi-step repair across tools best-first so a
single tool isn't drained dry when a backup is sitting in the rack.

Learning annotation: planning simulates consumption against *current*
charge without mutating the tools — the plan is a commitment the caller
executes via tool.use(), and stale plans are detectable because a real
execution changes bay_status().
"""

from __future__ import annotations

from .tool import Tool, ToolType, VALID_SUBSYSTEMS

#: Charge kept in reserve during routine (urgency=0) work.
RESERVE_CHARGE_PCT = 10.0

#: Charge consumed by one step of a service plan.
STEP_CHARGE_PCT = 5.0


class ToolBay:
    """A weight-constrained rack of Tool objects."""

    def __init__(self, max_weight_kg: float) -> None:
        if max_weight_kg <= 0:
            raise ValueError("max_weight_kg must be positive")
        self.max_weight_kg = float(max_weight_kg)
        self._tools: list[Tool] = []

    # ------------------------------------------------------------------
    # Rack management
    # ------------------------------------------------------------------
    def current_weight_kg(self) -> float:
        return sum(t.weight_kg for t in self._tools)

    def tools(self) -> list[Tool]:
        """Snapshot of the rack, in load order."""
        return list(self._tools)

    def add_tool(self, tool: Tool) -> None:
        if not isinstance(tool, Tool):
            raise ValueError("add_tool expects a Tool instance")
        if any(t.tool_type is tool.tool_type for t in self._tools):
            raise ValueError(f"bay already holds a {tool.tool_type.value}")
        if self.current_weight_kg() + tool.weight_kg > self.max_weight_kg:
            raise ValueError(
                f"adding {tool.tool_type.value} would exceed bay weight limit "
                f"({self.current_weight_kg():.1f} + {tool.weight_kg:.1f} "
                f"> {self.max_weight_kg:.1f} kg)"
            )
        self._tools.append(tool)

    def remove_tool(self, tool_type: ToolType | str) -> Tool:
        """Unrack and return the tool; ValueError if not present."""
        if isinstance(tool_type, str):
            try:
                tool_type = ToolType(tool_type)
            except ValueError:
                raise ValueError(f"unknown tool type: {tool_type!r}") from None
        for i, t in enumerate(self._tools):
            if t.tool_type is tool_type:
                return self._tools.pop(i)
        raise ValueError(f"no {tool_type.value} in bay")

    def get_tool(self, tool_type: ToolType) -> Tool | None:
        for t in self._tools:
            if t.tool_type is tool_type:
                return t
        return None

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def _candidates(self, subsystem: str) -> list[Tool]:
        if subsystem not in VALID_SUBSYSTEMS:
            raise ValueError(f"unknown subsystem: {subsystem!r}")
        return [t for t in self._tools if t.services(subsystem)]

    def select_tool(self, subsystem: str, urgency: float = 0.0) -> Tool | None:
        """Best tool for ``subsystem``, or None if nothing is usable.

        urgency in [0, 1] linearly relaxes the charge reserve from
        RESERVE_CHARGE_PCT down to 0. None means: nothing in the rack
        services this subsystem in a usable state — caller should
        escalate (request recharge, maintenance, or a different droid).
        """
        urgency = float(urgency)
        if not 0.0 <= urgency <= 1.0:
            raise ValueError("urgency must be within 0-1")
        charge_floor = RESERVE_CHARGE_PCT * (1.0 - urgency)
        usable = [
            t
            for t in self._candidates(subsystem)
            if t.is_operational() and t.charge_pct > charge_floor
        ]
        if not usable:
            return None
        return max(usable, key=lambda t: (t.condition_pct, t.charge_pct))

    def service_plan(self, subsystem: str, steps: int) -> list[Tool]:
        """Ordered tool sequence for a ``steps``-long repair.

        Each step consumes STEP_CHARGE_PCT of charge on the tool that
        performs it. Steps are allocated to the best tool first, rolling
        to the next tool when the first would drop below its reserve.
        Raises ValueError if the rack cannot cover all steps.
        """
        if not isinstance(steps, int) or steps <= 0:
            raise ValueError("steps must be a positive integer")
        candidates = sorted(
            (t for t in self._candidates(subsystem) if t.is_operational()),
            key=lambda t: (t.condition_pct, t.charge_pct),
            reverse=True,
        )
        plan: list[Tool] = []
        remaining = steps
        for tool in candidates:
            # Keep the routine reserve: usable charge is what sits above
            # the floor, same rule select_tool applies at urgency=0.
            usable_charge = max(0.0, tool.charge_pct - RESERVE_CHARGE_PCT)
            available = int(usable_charge // STEP_CHARGE_PCT)
            take = min(remaining, available)
            plan.extend([tool] * take)
            remaining -= take
            if remaining == 0:
                return plan
        raise ValueError(
            f"bay cannot cover {steps} step(s) on {subsystem}: "
            f"{steps - remaining} planned, {remaining} uncovered"
        )

    # ------------------------------------------------------------------
    # Reporting / serialization
    # ------------------------------------------------------------------
    def bay_status(self) -> dict:
        """Snapshot report for dashboards and diagnostics."""
        return {
            "max_weight_kg": self.max_weight_kg,
            "current_weight_kg": self.current_weight_kg(),
            "tool_count": len(self._tools),
            "operational_count": sum(1 for t in self._tools if t.is_operational()),
            "tools": [t.to_dict() for t in self._tools],
        }

    def to_dict(self) -> dict:
        return {
            "max_weight_kg": self.max_weight_kg,
            "tools": [t.to_dict() for t in self._tools],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolBay":
        try:
            bay = cls(max_weight_kg=data["max_weight_kg"])
            for raw in data["tools"]:
                bay.add_tool(Tool.from_dict(raw))
        except KeyError as exc:
            raise ValueError(f"missing bay field: {exc}") from None
        return bay
