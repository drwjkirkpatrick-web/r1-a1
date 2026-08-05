"""R1-A1 spacecraft repair framework: extensible diagnostic and repair knowledge base."""

from .registry import SpacecraftRegistry, SpacecraftType, Subsystem, SPACECRAFT_CATALOG
from .diagnostics import DiagnosticEngine, RepairProcedure

__all__ = [
    "SpacecraftRegistry",
    "DiagnosticEngine",
    "RepairProcedure",
    "SpacecraftType",
    "Subsystem",
]