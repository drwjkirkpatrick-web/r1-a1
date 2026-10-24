"""Mission and task model for R1-A1's long-horizon work.

An astromech gets told to do things that take far longer than one
control loop: "map the workshop", "charge then patrol", "wait for the
parts order". A Mission bundles one of those goals — a title, a
priority, an ordered list of named steps, and optionally other missions
that must finish first (dependencies) plus a soft deadline in days.

Everything here is pure logic. No clock is read unless you call
is_overdue(), and even then the clock is injected, so tests control
time. No hardware is touched anywhere.

Legal status transitions:

    PENDING   -> ACTIVE | BLOCKED | CANCELLED | FAILED
    ACTIVE    -> COMPLETE | FAILED | CANCELLED
    BLOCKED   -> PENDING | FAILED | CANCELLED
    COMPLETE / FAILED / CANCELLED -> (terminal)

    COMPLETE is reachable only from ACTIVE: you must actually start a
    mission before you may claim it finished.

Learning annotation:
    Dependencies are stored as mission_ids, not object references, so
    missions serialize cleanly and the queue can reason about chains
    with plain sets. Blocking is explicit (BLOCKED status) rather than
    implicit ("pending but not eligible") so progress_report() can show
    an operator *why* work is stuck. transition() is the single gate
    through which status changes flow — audit one method and you have
    audited every lifecycle path.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional, Sequence

SECONDS_PER_DAY = 86400.0


class MissionStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


# From each status, the statuses it may legally move to.
LEGAL_TRANSITIONS = {
    MissionStatus.PENDING: frozenset(
        {
            MissionStatus.ACTIVE,
            MissionStatus.BLOCKED,
            MissionStatus.CANCELLED,
            MissionStatus.FAILED,
        }
    ),
    MissionStatus.ACTIVE: frozenset(
        {
            MissionStatus.COMPLETE,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
        }
    ),
    MissionStatus.BLOCKED: frozenset(
        {
            MissionStatus.PENDING,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
        }
    ),
    MissionStatus.COMPLETE: frozenset(),
    MissionStatus.FAILED: frozenset(),
    MissionStatus.CANCELLED: frozenset(),
}


class Mission:
    """One unit of long-horizon work with steps, deps, and a deadline.

    Learning: the injected clock (``now_fn -> epoch seconds``) is only
    consulted for deadline math, captured once at construction so
    "created time" survives serialization round-trips.
    """

    def __init__(
        self,
        mission_id: str,
        title: str,
        priority: int = 5,
        depends_on: Sequence[str] = (),
        steps: Optional[Sequence[str]] = None,
        deadline_days: Optional[float] = None,
        now_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        if not isinstance(mission_id, str) or not mission_id.strip():
            raise ValueError("mission_id must be a non-empty string")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title must be a non-empty string")
        if not isinstance(priority, int) or not (1 <= priority <= 10):
            raise ValueError("priority must be an int in 1..10")
        if deadline_days is not None and deadline_days <= 0:
            raise ValueError("deadline_days must be positive when given")

        self.mission_id = mission_id
        self.title = title
        self.priority = priority
        self.depends_on = tuple(depends_on)
        if any(not isinstance(d, str) or not d for d in self.depends_on):
            raise ValueError("depends_on must contain non-empty mission_id strings")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on must not contain duplicates")
        self.deadline_days = deadline_days
        self.status = MissionStatus.PENDING

        self.steps: list[dict] = []
        names = set()
        for name in steps or ():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("step names must be non-empty strings")
            if name in names:
                raise ValueError(f"duplicate step name: {name!r}")
            names.add(name)
            self.steps.append({"name": name, "done": False})

        if now_fn is None:
            import time as _time

            now_fn = _time.time
        self._created_s = float(now_fn())

    # ------------------------------------------------------------------
    # Steps / progress
    # ------------------------------------------------------------------
    @property
    def progress_pct(self) -> float:
        """Percent of steps marked done (0.0 for a step-less mission)."""
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s["done"])
        return 100.0 * done / len(self.steps)

    def complete_step(self, name: str) -> None:
        """Mark the named step done. Raises ValueError for unknown names."""
        for step in self.steps:
            if step["name"] == name:
                step["done"] = True
                return
        raise ValueError(f"no step named {name!r} on mission {self.mission_id!r}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def transition(self, target: MissionStatus) -> MissionStatus:
        """Move to ``target`` if the transition is legal.

        Returns the new status. Raises ValueError on an illegal move
        (including any move out of a terminal state).
        """
        if not isinstance(target, MissionStatus):
            raise ValueError("target must be a MissionStatus")
        if target not in LEGAL_TRANSITIONS[self.status]:
            raise ValueError(
                f"illegal transition {self.status.value} -> {target.value}"
            )
        self.status = target
        return self.status

    def can_unblock(self, completed_ids) -> bool:
        """True when this mission is BLOCKED and every dependency is in
        ``completed_ids`` (any iterable of finished mission_ids)."""
        if self.status is not MissionStatus.BLOCKED:
            return False
        done = set(completed_ids)
        return all(dep in done for dep in self.depends_on)

    # ------------------------------------------------------------------
    # Deadline
    # ------------------------------------------------------------------
    def is_overdue(self, now_fn: Optional[Callable[[], float]] = None) -> bool:
        """True when past the deadline and still unfinished.

        Overdue only applies to live work (PENDING / ACTIVE / BLOCKED);
        completed, failed, or cancelled missions are never overdue.
        ``now_fn`` returns epoch seconds; defaults to time.time().
        """
        if self.deadline_days is None:
            return False
        if self.status in (
            MissionStatus.COMPLETE,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
        ):
            return False
        if now_fn is None:
            import time as _time

            now_fn = _time.time
        elapsed_days = (float(now_fn()) - self._created_s) / SECONDS_PER_DAY
        return elapsed_days > self.deadline_days

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "priority": self.priority,
            "depends_on": list(self.depends_on),
            "steps": [dict(s) for s in self.steps],
            "status": self.status.value,
            "deadline_days": self.deadline_days,
            "created_s": self._created_s,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Mission":
        mission = cls(
            mission_id=data["mission_id"],
            title=data["title"],
            priority=data.get("priority", 5),
            depends_on=data.get("depends_on", ()),
            steps=[s["name"] for s in data.get("steps", [])],
            deadline_days=data.get("deadline_days"),
            now_fn=lambda: data.get("created_s", 0.0),
        )
        for step, saved in zip(mission.steps, data.get("steps", [])):
            step["done"] = bool(saved.get("done", False))
        status = data.get("status")
        if status is not None:
            mission.status = MissionStatus(status)
        return mission
