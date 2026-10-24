"""MissionQueue: priority-ordered, dependency-aware scheduling.

The queue is the brain's to-do list. It holds missions, answers "what
should I do next?" (highest priority whose dependencies are satisfied),
and propagates outcomes: finishing a mission unblocks its dependents,
failing a mission auto-fails everything downstream of it.

Two entry points keep state consistent:

    next_mission()  -> sweep the graph, then pick the best eligible
                       ACTIVE/PENDING mission.
    tick(done_id)   -> record that a mission COMPLETE'd, then sweep:
                       unblock dependents whose deps are all done and
                       cascade-fail dependents of any FAILED mission.

Learning annotation:
    The sweep runs to a fixed point (loop until nothing changes) rather
    than one pass, because one unblocking/failing can chain: A unblocks
    B whose other dep already failed, so B fails, which fails C. A
    fixed-point loop is the simplest correct way to handle arbitrary
    chains without recursion depth worries. Ties on priority break by
    insertion order (stable FIFO within a priority band) so two
    same-priority missions never fight over who goes first.
"""

from __future__ import annotations

from typing import Optional

from .mission import Mission, MissionStatus


class MissionQueue:
    def __init__(self) -> None:
        self._missions: list[Mission] = []  # insertion order preserved

    # ------------------------------------------------------------------
    # Basic management
    # ------------------------------------------------------------------
    def add(self, mission: Mission) -> Mission:
        """Insert a mission. Raises ValueError on duplicate mission_id."""
        if not isinstance(mission, Mission):
            raise ValueError("add() expects a Mission instance")
        if self.get(mission.mission_id) is not None:
            raise ValueError(f"duplicate mission_id: {mission.mission_id!r}")
        self._missions.append(mission)
        return mission

    def get(self, mission_id: str) -> Optional[Mission]:
        for m in self._missions:
            if m.mission_id == mission_id:
                return m
        return None

    def cancel(self, mission_id: str) -> Mission:
        """Cancel a live mission. Raises ValueError if unknown or terminal."""
        mission = self.get(mission_id)
        if mission is None:
            raise ValueError(f"no mission with id {mission_id!r}")
        mission.transition(MissionStatus.CANCELLED)
        self._sweep()
        return mission

    def __len__(self) -> int:
        return len(self._missions)

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def next_mission(self) -> Optional[Mission]:
        """Highest-priority mission ready to run, or None.

        Eligible means ACTIVE or PENDING with every dependency COMPLETE.
        BLOCKED missions whose deps are now satisfied are unblocked to
        PENDING first. Ties on priority resolve by insertion order.
        """
        self._sweep()
        completed = self._completed_ids()
        eligible = [
            m
            for m in self._missions
            if m.status in (MissionStatus.ACTIVE, MissionStatus.PENDING)
            and all(dep in completed for dep in m.depends_on)
        ]
        if not eligible:
            return None
        return min(eligible, key=lambda m: (-m.priority, self._missions.index(m)))

    def tick(self, completed_mission_id: str) -> None:
        """Record a completion and cascade the consequences.

        Unblocks dependents whose deps are all COMPLETE and auto-fails
        any mission depending on a FAILED mission, transitively.
        Raises ValueError for an unknown id.
        """
        if self.get(completed_mission_id) is None:
            raise ValueError(f"no mission with id {completed_mission_id!r}")
        self._sweep()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def progress_report(self) -> dict:
        """Counts by status plus average progress across all missions."""
        counts = {status.value: 0 for status in MissionStatus}
        total_progress = 0.0
        for m in self._missions:
            counts[m.status.value] += 1
            total_progress += m.progress_pct
        avg = total_progress / len(self._missions) if self._missions else 0.0
        return {"counts": counts, "avg_progress": avg}

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"missions": [m.to_dict() for m in self._missions]}

    @classmethod
    def from_dict(cls, data: dict) -> "MissionQueue":
        queue = cls()
        for saved in data.get("missions", []):
            queue._missions.append(Mission.from_dict(saved))
        return queue

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _completed_ids(self) -> set:
        return {m.mission_id for m in self._missions if m.status is MissionStatus.COMPLETE}

    def _failed_ids(self) -> set:
        return {m.mission_id for m in self._missions if m.status is MissionStatus.FAILED}

    def _sweep(self) -> None:
        """Propagate dependency state to a fixed point.

        BLOCKED + any dep FAILED   -> FAILED (cascade)
        BLOCKED + all deps COMPLETE -> PENDING (unblock)
        Also marks PENDING missions with unsatisfied deps as BLOCKED so
        the operator sees why they are not running.
        """
        changed = True
        while changed:
            changed = False
            completed = self._completed_ids()
            failed = self._failed_ids()
            for m in self._missions:
                if m.status is MissionStatus.BLOCKED:
                    if any(dep in failed for dep in m.depends_on):
                        m.transition(MissionStatus.FAILED)
                        changed = True
                    elif all(dep in completed for dep in m.depends_on):
                        m.transition(MissionStatus.PENDING)
                        changed = True
                elif m.status is MissionStatus.PENDING:
                    if m.depends_on and not all(
                        dep in completed for dep in m.depends_on
                    ):
                        m.transition(MissionStatus.BLOCKED)
                        changed = True
