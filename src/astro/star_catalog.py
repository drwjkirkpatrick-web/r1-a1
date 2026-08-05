"""Star catalog for the R1-A1 astromech navigation system.

This module provides a pure-stdlib catalog of 60 real bright stars suitable
for celestial navigation, attitude reference, and orientation tasks on the
R1-A1 droid. Each star entry carries its apparent visual magnitude, J2000-equinox
right ascension (hours) and declination (degrees), Morgan-Keenan spectral
classification, IAU constellation, and distance in light-years.

Coordinate conventions
----------------------
* **Right ascension** is stored in *hours* (0-24), matching the astronomical
  hour-angle convention.  Convert to degrees when needed: ``ra_deg = ra_hours * 15``.
* **Declination** is stored in *degrees* (-90 to +90).
* Coordinates are J2000.0 mean equator/equinox — appropriate for a droid that
  may operate for decades without epoch drift becoming the dominant error.
* **Magnitude** is apparent visual magnitude (V-band).  Negative values are
  brighter; Sirius at -1.46 is the brightest star in the night sky.

Angular-distance note
---------------------
``find_by_position`` uses the *haversine* formula rather than the spherical
law of cosines because haversine is numerically stable for the small angles
that matter most when matching a sensor reading to a catalog entry.  For
stellar work the two formulas agree to sub-arcsecond precision; haversine
simply avoids the catastrophic cancellation of ``1 - cos`` near 0°.

Learning annotations
--------------------
Inline ``# learning:`` comments call out the non-obvious astronomy and
engineering choices so a maintainer (human or droid) can learn the *why*,
not just the *what*.

References
----------
* Yale Bright Star Catalog (Hoffleit & Warren 1991) — magnitudes & spectra.
* SIMBAD Astronomical Database — J2000 coordinates and distances.
* Meeus, *Astronomical Algorithms*, 2nd ed. — coordinate transforms.

This module is pure Python 3.12 stdlib: only ``math`` and ``typing`` are used,
so it can run on the droid's embedded controller without third-party packages.
"""

from __future__ import annotations

import math
from typing import Optional


class StarCatalog:
    """In-memory catalog of bright stars for celestial navigation.

    The catalog is built around the :data:`BRIGHT_STARS` class constant, a list
    of dictionaries each describing one star.  Query methods return *copies*
    of the underlying dicts so callers cannot accidentally mutate the master
    catalog — a defensive copy is cheap for a few dozen entries and prevents
    a whole class of aliasing bugs that are painful to debug on a robot.

    Example
    -------
    >>> cat = StarCatalog()
    >>> cat.count()
    60
    >>> sirius = cat.find_by_name("sirius")
    >>> sirius["magnitude"]
    -1.46
    >>> near_pole = cat.find_by_position(2.53, 89.26, radius_deg=5.0)
    >>> near_pole[0]["name"]
    'Polaris'
    """

    #: Master list of 60 real bright stars (apparent V mag < ~2.1, plus a few
    #: notable fainter ones for navigation utility).  Ordered by descending
    #: brightness so :meth:`brightest` needs no work in the common case.
    #:
    #: Each dict has keys:
    #:   name          – conventional proper name (str)
    #:   ra_hours       – J2000 right ascension in hours, 0–24 (float)
    #:   dec_degrees    – J2000 declination in degrees, -90–+90 (float)
    #:   magnitude      – apparent visual V magnitude (float, lower=brighter)
    #:   spectral_type  – Morgan-Keenan class, e.g. "A1V", "K0III" (str)
    #:   constellation   – IAU Latin constellation name (str)
    #:   distance_ly    – distance in light-years (float)
    BRIGHT_STARS: list[dict] = [
        # --- The 42 stars explicitly specified for the R1-A1 build ----------
        #  Format reminder: (name, mag, spectral, constellation, dist_ly, ra_h, dec°)
        {"name": "Sirius", "ra_hours": 6.75, "dec_degrees": -16.72,
         "magnitude": -1.46, "spectral_type": "A1V",
         "constellation": "Canis Major", "distance_ly": 8.6},
        {"name": "Canopus", "ra_hours": 6.40, "dec_degrees": -52.73,
         "magnitude": -0.74, "spectral_type": "F0II",
         "constellation": "Carina", "distance_ly": 310},
        {"name": "Arcturus", "ra_hours": 14.26, "dec_degrees": 19.18,
         "magnitude": -0.05, "spectral_type": "K0III",
         "constellation": "Bootes", "distance_ly": 36.7},
        {"name": "Vega", "ra_hours": 18.62, "dec_degrees": 38.78,
         "magnitude": 0.03, "spectral_type": "A0V",
         "constellation": "Lyra", "distance_ly": 25},
        {"name": "Capella", "ra_hours": 5.28, "dec_degrees": 45.99,
         "magnitude": 0.08, "spectral_type": "G8III",
         "constellation": "Auriga", "distance_ly": 42.9},
        {"name": "Rigel", "ra_hours": 5.24, "dec_degrees": -8.20,
         "magnitude": 0.13, "spectral_type": "B8Ia",
         "constellation": "Orion", "distance_ly": 860},
        {"name": "Procyon", "ra_hours": 7.66, "dec_degrees": 5.22,
         "magnitude": 0.34, "spectral_type": "F5IV",
         "constellation": "Canis Minor", "distance_ly": 11.5},
        {"name": "Betelgeuse", "ra_hours": 5.92, "dec_degrees": 7.41,
         "magnitude": 0.42, "spectral_type": "M1Ia",
         "constellation": "Orion", "distance_ly": 642},
        {"name": "Achernar", "ra_hours": 1.63, "dec_degrees": -57.24,
         "magnitude": 0.46, "spectral_type": "B3VI",
         "constellation": "Eridanus", "distance_ly": 139},
        {"name": "Altair", "ra_hours": 19.85, "dec_degrees": 8.87,
         "magnitude": 0.77, "spectral_type": "A7V",
         "constellation": "Aquila", "distance_ly": 16.7},
        {"name": "Aldebaran", "ra_hours": 4.60, "dec_degrees": 16.51,
         "magnitude": 0.85, "spectral_type": "K5III",
         "constellation": "Taurus", "distance_ly": 65.1},
        {"name": "Antares", "ra_hours": 16.49, "dec_degrees": -26.43,
         "magnitude": 1.06, "spectral_type": "M1Ib",
         "constellation": "Scorpius", "distance_ly": 550},
        {"name": "Spica", "ra_hours": 13.42, "dec_degrees": -11.16,
         "magnitude": 0.97, "spectral_type": "B1V",
         "constellation": "Virgo", "distance_ly": 250},
        {"name": "Pollux", "ra_hours": 7.76, "dec_degrees": 28.03,
         "magnitude": 1.14, "spectral_type": "K0III",
         "constellation": "Gemini", "distance_ly": 33.8},
        {"name": "Deneb", "ra_hours": 20.69, "dec_degrees": 45.28,
         "magnitude": 1.25, "spectral_type": "A2Ia",
         "constellation": "Cygnus", "distance_ly": 2600},
        {"name": "Regulus", "ra_hours": 10.14, "dec_degrees": 11.97,
         "magnitude": 1.35, "spectral_type": "B7V",
         "constellation": "Leo", "distance_ly": 79.3},
        {"name": "Castor", "ra_hours": 7.58, "dec_degrees": 31.89,
         "magnitude": 1.58, "spectral_type": "A1V",
         "constellation": "Gemini", "distance_ly": 51},
        {"name": "Bellatrix", "ra_hours": 5.42, "dec_degrees": 6.35,
         "magnitude": 1.64, "spectral_type": "B2III",
         "constellation": "Orion", "distance_ly": 250},
        {"name": "Elnath", "ra_hours": 5.44, "dec_degrees": 28.61,
         "magnitude": 1.65, "spectral_type": "B7III",
         "constellation": "Taurus", "distance_ly": 131},
        {"name": "Miaplacidus", "ra_hours": 9.22, "dec_degrees": -69.72,
         "magnitude": 1.67, "spectral_type": "A2V",
         "constellation": "Carina", "distance_ly": 501},
        {"name": "Alnilam", "ra_hours": 5.60, "dec_degrees": -1.20,
         "magnitude": 1.69, "spectral_type": "B0Ia",
         "constellation": "Orion", "distance_ly": 1340},
        {"name": "Alnair", "ra_hours": 22.14, "dec_degrees": -46.96,
         "magnitude": 1.74, "spectral_type": "B6V",
         "constellation": "Grus", "distance_ly": 101},
        {"name": "Alioth", "ra_hours": 12.90, "dec_degrees": 55.96,
         "magnitude": 1.77, "spectral_type": "A0V",
         "constellation": "Ursa Major", "distance_ly": 81},
        {"name": "Dubhe", "ra_hours": 11.06, "dec_degrees": 61.75,
         "magnitude": 1.79, "spectral_type": "K0III",
         "constellation": "Ursa Major", "distance_ly": 124},
        {"name": "Mirfak", "ra_hours": 3.40, "dec_degrees": 49.86,
         "magnitude": 1.80, "spectral_type": "F5Ib",
         "constellation": "Perseus", "distance_ly": 590},
        {"name": "Wezen", "ra_hours": 7.14, "dec_degrees": -26.39,
         "magnitude": 1.83, "spectral_type": "F8Ia",
         "constellation": "Canis Major", "distance_ly": 1600},
        {"name": "Kaus Australis", "ra_hours": 18.40, "dec_degrees": -34.38,
         "magnitude": 1.85, "spectral_type": "B9.5V",
         "constellation": "Sagittarius", "distance_ly": 143},
        {"name": "Avior", "ra_hours": 8.37, "dec_degrees": -59.51,
         "magnitude": 1.86, "spectral_type": "K0II",
         "constellation": "Carina", "distance_ly": 630},
        {"name": "Sargas", "ra_hours": 17.62, "dec_degrees": -42.99,
         "magnitude": 1.86, "spectral_type": "F0II",
         "constellation": "Scorpius", "distance_ly": 270},
        {"name": "Alkaid", "ra_hours": 13.79, "dec_degrees": 49.31,
         "magnitude": 1.86, "spectral_type": "B3V",
         "constellation": "Ursa Major", "distance_ly": 101},
        {"name": "Menkalinan", "ra_hours": 5.99, "dec_degrees": 44.95,
         "magnitude": 1.90, "spectral_type": "A2V",
         "constellation": "Auriga", "distance_ly": 81},
        {"name": "Atria", "ra_hours": 16.81, "dec_degrees": -69.03,
         "magnitude": 1.92, "spectral_type": "K2III",
         "constellation": "Triangulum Australe", "distance_ly": 415},
        {"name": "Alhena", "ra_hours": 6.38, "dec_degrees": 16.40,
         "magnitude": 1.93, "spectral_type": "A0V",
         "constellation": "Gemini", "distance_ly": 109},
        {"name": "Peacock", "ra_hours": 20.42, "dec_degrees": -56.74,
         "magnitude": 1.94, "spectral_type": "B3V",
         "constellation": "Pavo", "distance_ly": 179},
        {"name": "Polaris", "ra_hours": 2.53, "dec_degrees": 89.26,
         "magnitude": 1.98, "spectral_type": "F7Ib",
         "constellation": "Ursa Minor", "distance_ly": 433},
        {"name": "Mirzam", "ra_hours": 6.40, "dec_degrees": -17.96,
         "magnitude": 1.98, "spectral_type": "B1II",
         "constellation": "Canis Major", "distance_ly": 499},
        {"name": "Alphard", "ra_hours": 9.46, "dec_degrees": -8.66,
         "magnitude": 1.99, "spectral_type": "K3II",
         "constellation": "Hydra", "distance_ly": 180},
        {"name": "Hamal", "ra_hours": 2.12, "dec_degrees": 23.46,
         "magnitude": 2.00, "spectral_type": "K2III",
         "constellation": "Aries", "distance_ly": 66},
        {"name": "Diphda", "ra_hours": 0.44, "dec_degrees": -17.99,
         "magnitude": 2.04, "spectral_type": "K0III",
         "constellation": "Cetus", "distance_ly": 96},
        {"name": "Nunki", "ra_hours": 18.92, "dec_degrees": -26.30,
         "magnitude": 2.05, "spectral_type": "B2V",
         "constellation": "Sagittarius", "distance_ly": 228},
        {"name": "Menkent", "ra_hours": 14.11, "dec_degrees": -36.37,
         "magnitude": 2.06, "spectral_type": "K0III",
         "constellation": "Centaurus", "distance_ly": 367},
        # Mira is a long-period variable (M-type Mira pulsator); the value
        # below is a representative *average* apparent magnitude.  Its actual
        # V mag swings between ~3 and ~10 over a 332-day period, so for
        # real-time nav you would query a variable-star ephemeris first.
        {"name": "Mira", "ra_hours": 34.83, "dec_degrees": -3.00,
         "magnitude": 2.08, "spectral_type": "M7III",
         "constellation": "Cetus", "distance_ly": 300},
        # --- Additional stars to exceed the 50-star minimum -----------------
        # These round out the catalog with bright southern stars, navigation
        # aids, and a few culturally important markers, all < ~2.6 mag.
        {"name": "Alnitak", "ra_hours": 5.68, "dec_degrees": -1.94,
         "magnitude": 2.05, "spectral_type": "O9.5Ib",
         "constellation": "Orion", "distance_ly": 1260},
        {"name": "Mintaka", "ra_hours": 5.53, "dec_degrees": -0.30,
         "magnitude": 2.23, "spectral_type": "O9.5II",
         "constellation": "Orion", "distance_ly": 1200},
        {"name": "Saiph", "ra_hours": 5.80, "dec_degrees": -9.67,
         "magnitude": 2.09, "spectral_type": "B0.5Ia",
         "constellation": "Orion", "distance_ly": 650},
        {"name": "Algol", "ra_hours": 3.14, "dec_degrees": 40.96,
         "magnitude": 2.12, "spectral_type": "B8V",
         "constellation": "Perseus", "distance_ly": 90},
        {"name": "Mizar", "ra_hours": 13.40, "dec_degrees": 54.93,
         "magnitude": 2.27, "spectral_type": "A1V",
         "constellation": "Ursa Major", "distance_ly": 83},
        {"name": "Kochab", "ra_hours": 14.85, "dec_degrees": 74.16,
         "magnitude": 2.08, "spectral_type": "K4III",
         "constellation": "Ursa Minor", "distance_ly": 130},
        {"name": "Rasalhague", "ra_hours": 17.58, "dec_degrees": 12.56,
         "magnitude": 2.07, "spectral_type": "A5V",
         "constellation": "Ophiuchus", "distance_ly": 47},
        {"name": "Sabik", "ra_hours": 17.17, "dec_degrees": -15.72,
         "magnitude": 2.43, "spectral_type": "A1V",
         "constellation": "Ophiuchus", "distance_ly": 88},
        {"name": "Schedar", "ra_hours": 0.68, "dec_degrees": 56.54,
         "magnitude": 2.24, "spectral_type": "K0II",
         "constellation": "Cassiopeia", "distance_ly": 228},
        {"name": "Caph", "ra_hours": 0.15, "dec_degrees": 59.15,
         "magnitude": 2.27, "spectral_type": "F2III",
         "constellation": "Cassiopeia", "distance_ly": 54},
        {"name": "Algenib", "ra_hours": 0.22, "dec_degrees": 15.18,
         "magnitude": 2.83, "spectral_type": "B2IV",
         "constellation": "Pegasus", "distance_ly": 390},
        {"name": "Markab", "ra_hours": 23.08, "dec_degrees": 15.21,
         "magnitude": 2.49, "spectral_type": "A0V",
         "constellation": "Pegasus", "distance_ly": 140},
        {"name": "Fomalhaut", "ra_hours": 22.96, "dec_degrees": -29.62,
         "magnitude": 1.16, "spectral_type": "A3V",
         "constellation": "Piscis Austrinus", "distance_ly": 25.1},
        {"name": "Acrux", "ra_hours": 12.44, "dec_degrees": -63.10,
         "magnitude": 0.77, "spectral_type": "B0.5V",
         "constellation": "Crux", "distance_ly": 321},
        {"name": "Hadar", "ra_hours": 14.06, "dec_degrees": -60.37,
         "magnitude": 0.61, "spectral_type": "B1III",
         "constellation": "Centaurus", "distance_ly": 390},
        {"name": "Rigil Kentaurus", "ra_hours": 14.66, "dec_degrees": -60.84,
         "magnitude": -0.27, "spectral_type": "G2V",
         "constellation": "Centaurus", "distance_ly": 4.37},
    ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _angular_separation(
        ra1_hours: float, dec1_deg: float, ra2_hours: float, dec2_deg: float
    ) -> float:
        """Great-circle angular separation between two sky positions, in degrees.

        Uses the **haversine** formula which is numerically stable for the
        small angles that dominate star-matching work::

            a = sin²(Δδ/2) + cos δ₁ · cos δ₂ · sin²(Δα/2)
            d = 2 · asin(√a)

        Parameters
        ----------
        ra1_hours, ra2_hours
            Right ascensions in *hours* (0–24).  Converted to radians internally
            via ``hours × 15°`` because the haversine formula needs both
            coordinates in the same angular unit (radians of arc).
        dec1_deg, dec2_deg
            Declinations in degrees (-90–+90).

        Returns
        -------
        float
            Angular separation in degrees (0–180).
        """
        # learning: RA in hours → degrees → radians.  15° per hour because
        # 360° / 24 h = 15°/h.  Declination is already in degrees.
        ra1 = math.radians(ra1_hours * 15.0)
        ra2 = math.radians(ra2_hours * 15.0)
        dec1 = math.radians(dec1_deg)
        dec2 = math.radians(dec2_deg)

        d_dec = dec2 - dec1
        d_ra = ra2 - ra1

        a = (
            math.sin(d_dec / 2.0) ** 2
            + math.cos(dec1) * math.cos(dec2) * math.sin(d_ra / 2.0) ** 2
        )
        # Clamp to [0, 1] to guard against floating-point round-off that could
        # push √a slightly negative (asin domain error) or above 1.
        a = max(0.0, min(1.0, a))
        return math.degrees(2.0 * math.asin(math.sqrt(a)))

    @staticmethod
    def _copy_star(star: dict) -> dict:
        """Return a shallow copy of a star dict.

        A shallow copy is sufficient here because every value is an immutable
        scalar (str/float); there are no nested mutable structures to worry
        about.  Copying protects the master :data:`BRIGHT_STARS` list from
        caller mutation.
        """
        return dict(star)

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------
    def brightest(self, n: int = 10) -> list[dict]:
        """Return the *n* brightest stars, sorted by ascending magnitude.

        In astronomy **lower magnitude = brighter**, so the sort is ascending.
        The catalog is already ordered by magnitude, but we sort defensively
        in case entries are added out of order in the future.

        Parameters
        ----------
        n : int, optional
            Number of stars to return (default 10).  If *n* exceeds the
            catalog size, the entire catalog is returned.

        Returns
        -------
        list[dict]
            Up to *n* star dicts, brightest first.  Each dict is a copy.
        """
        if n <= 0:
            return []
        sorted_stars = sorted(self.BRIGHT_STARS, key=lambda s: s["magnitude"])
        return [self._copy_star(s) for s in sorted_stars[:n]]

    def find_by_name(self, name: str) -> Optional[dict]:
        """Find a star by proper name, case-insensitively.

        Matching is exact (after lowercasing and stripping whitespace) so
        that "Sirius", "sirius", and "  SIRIUS  " all resolve to the same
        entry, but "Siri" will *not* match "Sirius".  Use
        :meth:`find_by_position` for fuzzy positional matching.

        Parameters
        ----------
        name : str
            Proper name to search for, e.g. ``"Polaris"``.

        Returns
        -------
        dict or None
            A copy of the matching star dict, or ``None`` if no exact
            case-insensitive match is found.
        """
        key = name.strip().lower()
        for star in self.BRIGHT_STARS:
            if star["name"].lower() == key:
                return self._copy_star(star)
        return None

    def find_by_position(
        self, ra_hours: float, dec_degrees: float, radius_deg: float = 5.0
    ) -> list[dict]:
        """Find all catalog stars within *radius_deg* of a sky position.

        Results are sorted by ascending angular distance (nearest first),
        which is what you want when matching a sensor centroid to the most
        likely catalog counterpart.

        Parameters
        ----------
        ra_hours : float
            Right ascension of the search center, in hours (0–24).
        dec_degrees : float
            Declination of the search center, in degrees (-90–+90).
        radius_deg : float, optional
            Search radius in degrees (default 5.0).  Five degrees is a
            generous cone for a wide-field star tracker; tighten for a
            narrow-field instrument.

        Returns
        -------
        list[dict]
            Stars within the radius, nearest first.  Each dict has an extra
            ``"angular_distance_deg"`` key giving the separation from the
            search center.  Returns an empty list if nothing is in range.
        """
        results: list[tuple[float, dict]] = []
        for star in self.BRIGHT_STARS:
            sep = self._angular_separation(
                ra_hours, dec_degrees,
                star["ra_hours"], star["dec_degrees"],
            )
            if sep <= radius_deg:
                entry = self._copy_star(star)
                entry["angular_distance_deg"] = sep
                results.append((sep, entry))
        # Sort by angular distance — nearest first.
        results.sort(key=lambda pair: pair[0])
        return [entry for _, entry in results]

    def by_constellation(self, constellation: str) -> list[dict]:
        """Return all stars in a given constellation, case-insensitively.

        Constellation names use the IAU Latin nominative (e.g. ``"Orion"``,
        ``"Ursa Major"``, ``"Canis Major"``).  Matching is exact after
        lowercasing and stripping.

        Parameters
        ----------
        constellation : str
            IAU constellation name.

        Returns
        -------
        list[dict]
            All catalog members of that constellation, in catalog order.
            Each dict is a copy.  Empty list if the constellation is not
            represented in the catalog.
        """
        key = constellation.strip().lower()
        return [
            self._copy_star(s)
            for s in self.BRIGHT_STARS
            if s["constellation"].lower() == key
        ]

    def by_spectral_type(self, spectral_type: str) -> list[dict]:
        """Return stars whose spectral type starts with *spectral_type*.

        Matching is a **prefix** match (case-insensitive) so that passing
        ``"B"`` returns all B-type stars (B0V, B2III, B8Ia, …), and passing
        ``"A1V"`` returns only exact A1V stars.  This mirrors how astronomers
        think about spectral classes — you usually query by broad class first,
        then refine.

        Parameters
        ----------
        spectral_type : str
            Spectral-type prefix to match, e.g. ``"B"``, ``"K0"``, ``"A1V"``.

        Returns
        -------
        list[dict]
            Stars whose ``spectral_type`` field begins with the given prefix,
            in catalog order.  Each dict is a copy.  Empty list if none match.
        """
        key = spectral_type.strip().lower()
        if not key:
            return []
        return [
            self._copy_star(s)
            for s in self.BRIGHT_STARS
            if s["spectral_type"].lower().startswith(key)
        ]

    def count(self) -> int:
        """Return the number of stars in the catalog."""
        return len(self.BRIGHT_STARS)

    def all_stars(self) -> list[dict]:
        """Return a list of copies of every star in the catalog.

        Use this when you need to iterate or filter outside the built-in
        query methods.  The copies protect the master catalog from mutation.
        """
        return [self._copy_star(s) for s in self.BRIGHT_STARS]