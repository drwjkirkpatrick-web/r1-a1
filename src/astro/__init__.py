"""R1-A1 astro navigation: celestial navigation, solar system body tracking,
star catalogs, Milky Way structure, astronomical data bridge, exoplanet
catalog, and exoplanet transit detection."""

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

# ``ExoplanetCatalog`` queries the NASA Exoplanet Archive TAP API for an
# up-to-date list of all known exoplanets.  Pure stdlib (lazy ``requests``).
from .exoplanet_catalog import ExoplanetCatalog

# ``ExoplanetDetector`` runs BLS transit searches on TESS light curves.
# ``lightkurve`` / ``numpy`` are lazily imported so the module loads without them.
from .exoplanet import ExoplanetDetector

__all__ = [
    'Navigation',
    'SolarSystem',
    'StarCatalog',
    'MilkyWay',
    'AstroBridge',
    'ExoplanetCatalog',
    'ExoplanetDetector',
]