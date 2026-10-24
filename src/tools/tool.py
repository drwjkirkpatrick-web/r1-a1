"""Tool definitions for the astromech's utility arm / tool bay.

An R-series unit carries a rack of swappable tools (arc welder, scomp
link, manipulator arm, ...) behind its front panels. Each tool is a
small state machine with two consumable resources:

    charge_pct    energy reservoir (rechargeable, 0-100)
    condition_pct mechanical wear (restorable via maintenance, 0-100)

Both deplete with use; both must be above their floors for the tool to
be considered field-operational. Pure logic only — the motor drivers
that actually extend the arm live in the motion stack.

Learning annotation: separating "charge" (recoverable in minutes at a
power socket) from "condition" (recoverable only with a workbench
maintenance cycle) lets the bay's selection heuristic trade the two off
— a worn but freshly charged welder is a different risk profile than a
pristine one at 5 % charge.
"""

from __future__ import annotations

from enum import Enum

from repair.registry import SUBSYSTEM_CATEGORIES

#: Condition floor: at or below this the tool is unreliable and must be
#: benched for maintenance before it counts as operational.
MIN_OPERATIONAL_CONDITION_PCT = 20.0

#: Wear applied per unit of use, as a fraction of the charge consumed.
#: Burning 10 % charge costs 5 % condition.
WEAR_PER_CHARGE = 0.5

#: Spacecraft subsystem categories a tool can service. Single-sourced
#: from the repair registry so the two category lists can never drift
#: apart (a tools-only copy once dropped "communications").
VALID_SUBSYSTEMS = tuple(sorted(SUBSYSTEM_CATEGORIES))


class ToolType(Enum):
    """The eight canonical tools in an R-series utility rack."""

    ARC_WELDER = "arc_welder"
    MANIPULATOR_ARM = "manipulator_arm"
    SCOMP_LINK = "scomp_link"
    FIRE_EXTINGUISHER = "fire_extinguisher"
    HOLORECORDER = "holorecorder"
    FUSION_CUTTER = "fusion_cutter"
    GRASPING_CLAW = "grasping_claw"
    DIAGNOSTIC_PROBE = "diagnostic_probe"


class Tool:
    """A single bay tool with charge, wear, and service coverage."""

    def __init__(
        self,
        tool_type: ToolType | str,
        weight_kg: float,
        required_subsystems: tuple[str, ...],
        charge_pct: float = 100.0,
        condition_pct: float = 100.0,
    ) -> None:
        if isinstance(tool_type, str):
            try:
                tool_type = ToolType(tool_type)
            except ValueError:
                raise ValueError(f"unknown tool type: {tool_type!r}") from None
        if not isinstance(tool_type, ToolType):
            raise ValueError("tool_type must be a ToolType or its value string")
        if weight_kg <= 0:
            raise ValueError("weight_kg must be positive")
        if not required_subsystems:
            raise ValueError("required_subsystems must name at least one subsystem")
        unknown = [s for s in required_subsystems if s not in VALID_SUBSYSTEMS]
        if unknown:
            raise ValueError(f"unknown subsystem(s): {unknown}")
        self.tool_type = tool_type
        self.weight_kg = float(weight_kg)
        self.required_subsystems = tuple(required_subsystems)
        self.charge_pct = self._check_pct("charge_pct", charge_pct)
        self.condition_pct = self._check_pct("condition_pct", condition_pct)

    @staticmethod
    def _check_pct(name: str, value: float) -> float:
        value = float(value)
        if not 0.0 <= value <= 100.0:
            raise ValueError(f"{name} must be within 0-100, got {value}")
        return value

    def services(self, subsystem: str) -> bool:
        """True if this tool can work on the named subsystem."""
        return subsystem in self.required_subsystems

    def use(self, amount: float) -> None:
        """Consume ``amount`` percent of charge and apply wear.

        Both resources clamp at 0 — running a tool dry doesn't make its
        charge negative, it just leaves it dead and worn.
        """
        amount = float(amount)
        if amount <= 0:
            raise ValueError("use amount must be positive")
        self.charge_pct = max(0.0, self.charge_pct - amount)
        self.condition_pct = max(0.0, self.condition_pct - amount * WEAR_PER_CHARGE)

    def recharge(self) -> None:
        """Top the charge reservoir back to 100 %."""
        self.charge_pct = 100.0

    def maintenance(self) -> None:
        """Full workbench service: restore condition to 100 %."""
        self.condition_pct = 100.0

    def is_operational(self) -> bool:
        """True when the tool has any charge and condition above the floor."""
        return self.charge_pct > 0.0 and self.condition_pct > MIN_OPERATIONAL_CONDITION_PCT

    def to_dict(self) -> dict:
        return {
            "tool_type": self.tool_type.value,
            "weight_kg": self.weight_kg,
            "required_subsystems": list(self.required_subsystems),
            "charge_pct": self.charge_pct,
            "condition_pct": self.condition_pct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Tool":
        try:
            return cls(
                tool_type=data["tool_type"],
                weight_kg=data["weight_kg"],
                required_subsystems=tuple(data["required_subsystems"]),
                charge_pct=data.get("charge_pct", 100.0),
                condition_pct=data.get("condition_pct", 100.0),
            )
        except KeyError as exc:
            raise ValueError(f"missing tool field: {exc}") from None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Tool({self.tool_type.value}, charge={self.charge_pct:.0f}%, "
            f"condition={self.condition_pct:.0f}%)"
        )
