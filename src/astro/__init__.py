"""R1-A1 astro navigation: celestial navigation, solar system body tracking, star catalogs, and astronomical data bridge."""

# ``Navigation`` is implemented in this module and is always available.
from .navigation import Navigation

# ``SolarSystem`` lives in the sibling ``solar_system`` module.
from .solar_system import SolarSystem

# ``StarCatalog`` lives in the sibling ``star_catalog`` module.
from .star_catalog import StarCatalog

# ``AstroBridge`` lives in the sibling ``bridge`` module.
from .bridge import AstroBridge

# ``MilkyWay`` is part of the planned astro-package public API but its backing
# module has not been authored yet.  It is imported *defensively* so that
# ``import astro`` keeps working while the module is developed; once
# ``milky_way.py`` exists its class is picked up automatically.
try:  # pragma: no cover - guarded import for a not-yet-written module
    from .milky_way import MilkyWay
except ImportError:  # pragma: no cover
    MilkyWay = None  # type: ignore[assignment]

__all__ = ['Navigation', 'SolarSystem', 'StarCatalog', 'MilkyWay', 'AstroBridge']