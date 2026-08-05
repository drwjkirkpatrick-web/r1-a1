"""Milky Way galaxy structure model.

This module provides a :class:`MilkyWay` class that encodes the large-scale
structure of our home galaxy — its dimensions, spiral arms, component regions,
and notable deep-sky objects — together with a coordinate transform from
galactic (longitude / latitude) to equatorial (right ascension / declination)
coordinates for the J2000 epoch.

Pure standard library only (:mod:`typing`, :mod:`math`); no third-party
astronomy packages are required, so this is safe to import on a bare
MicroPython host or a constrained embedded system.

Coordinate notes
----------------
The galactic coordinate system is a heliocentric spherical system whose
fundamental plane is the galactic equator (the plane of the Milky Way disk)
and whose latitude ``b = 0°`` runs along the disk.  Longitude ``l`` is
measured from the direction of the *galactic center* (Sgr A*), increasing
counter-clockwise (north of the disk) from 0° to 360°.

The equatorial (RA / Dec) system is referenced to the J2000 equator and
equinox.  The transformation between the two uses a single rotation defined by
the J2000 pole of the galactic system:

    North Galactic Pole  →  RA 192.85948°,  Dec  27.12825°  (J2000)
    Galactic Center      →  RA 266.40510°,  Dec -28.93615°  (l=0, b=0)

See :meth:`MilkyWay.galactic_to_equatorial` for the implementation.

All celestial data are rounded to the precision commonly cited in popular and
undergraduate astronomy references; they are intended for educational and
rough pointing use, not for precision astrometry.
"""

from __future__ import annotations

import math
from typing import Final

__all__ = ["MilkyWay"]


class MilkyWay:
    """Model of the Milky Way galaxy for the R1-A1 astromech.

    The class exposes the galaxy's gross physical parameters as the
    :attr:`GALACTIC_STRUCTURE` class-level constant, the four major spiral
    arms via :meth:`galactic_arms`, the principal structural components
    via :meth:`notable_regions`, and a catalogue of prominent deep-sky
    objects via :meth:`notable_objects`.

    A coordinate utility :meth:`galactic_to_equatorial` converts galactic
    (l, b) coordinates to equatorial (RA, Dec) for the J2000 epoch using the
    standard pole-based rotation.

    Example
    -------
    >>> mw = MilkyWay()
    >>> mw.GALACTIC_STRUCTURE["diameter_ly"]
    100000
    >>> coord = mw.galactic_to_equatorial(0.0, 0.0)        # galactic center
    >>> round(coord["ra_degrees"], 1)
    266.4
    >>> arms = mw.galactic_arms()
    >>> len(arms)
    4
    """

    # ------------------------------------------------------------------
    # Gross physical parameters of the galaxy (J2000 / modern consensus).
    # ------------------------------------------------------------------
    # ``Final`` declares intent: these are physical constants, not knobs to
    # be tuned at runtime.  The dict itself is still mutable in Python, but
    # callers should treat it as read-only.
    GALACTIC_STRUCTURE: Final[dict[str, float | str]] = {
        "diameter_ly": 100_000,            # approximate optical disk diameter
        "thickness_ly": 1_000,            # thin-disk scale (1000 ly ~ 307 pc)
        "num_stars_estimated": 100_000_000_000,  # ~100–400 Gyr depending on M-dwarf census; use 1e11
        "central_black_hole": "Sagittarius A*",
        "sun_distance_from_center_ly": 26_000,  # ~8 kpc (Orbit of the Sun)
        "galactic_center_ra": 266.42,      # J2000 RA of Sgr A* in degrees
        "galactic_center_dec": -29.01,    # J2000 Dec of Sgr A* in degrees
        "rotation_speed_km_s": 220,       # local standard of rest (LSR) orbital speed
        "rotation_period_myr": 240,       # ~225–250 Myr "galactic year"
    }

    # ------------------------------------------------------------------
    # J2000 reference points that define the galactic ↔ equatorial rotation.
    # These are the IAU 1958 / J2000 adopted values.  Rounded versions of
    # the NGP (192.86, 27.13) and the GC (266.42, -29.01) appear in
    # :attr:`GALACTIC_STRUCTURE` for display; the more precise values below
    # are used internally for the coordinate transform.
    # ------------------------------------------------------------------
    _NGP_RA_DEG: Final[float] = 192.85948   # RA  of north galactic pole (J2000)
    _NGP_DEC_DEG: Final[float] = 27.12825   # Dec of north galactic pole (J2000)
    _GC_RA_DEG: Final[float] = 266.40510    # RA  of galactic center (J2000)
    _GC_DEC_DEG: Final[float] = -28.93615  # Dec of galactic center (J2000)

    # ------------------------------------------------------------------
    # Public catalogue API
    # ------------------------------------------------------------------
    def galactic_arms(self) -> list[dict[str, object]]:
        """Return the four major spiral arms of the Milky Way.

        Each arm is returned as a dict with keys:
        ``name`` (str), ``distance_from_center_ly`` (float), and
        ``description`` (str).  Distances are approximate galactocentric
        radii of the arm near the Sun's azimuth and are drawn from radio
        H II / maser parallax surveys (Reid et al. 2019 and successors).

        Returns
        -------
        list[dict[str, object]]
            Four spiral-arm dictionaries, ordered Perseus, Sagittarius,
            Norma, then Outer / Scutum–Centaurus.

        Note
        ----
        The Milky Way is a *barred* spiral (SBbc).  Arm naming and numbering
        are not perfectly settled; this list follows the most common
        four-arm convention used in introductory astronomy.
        """
        return [
            {
                "name": "Perseus Arm",
                "distance_from_center_ly": 52_000,
                "description": (
                    "Outer spiral arm outward from the Sun's position; host "
                    "to many H II regions and young stellar associations."
                ),
            },
            {
                "name": "Sagittarius Arm",
                "distance_from_center_ly": 33_000,
                "description": (
                    "Major arm inward toward the galactic center; rich in "
                    "star-forming molecular clouds visible as bright "
                    "nebulae along the galactic plane."
                ),
            },
            {
                "name": "Norma Arm",
                "distance_from_center_ly": 26_000,
                "description": (
                    "Inner arm close to the galactic center; contains "
                    "dense molecular complexes and joins the central bar."
                ),
            },
            {
                "name": "Outer Arm (Scutum-Centaurus)",
                "distance_from_center_ly": 60_000,
                "description": (
                    "Outermost prominent arm sweeping through Scutum and "
                    "Centaurus; one of the two main arms of the galaxy's "
                    "logarithmic-spiral model."
                ),
            },
        ]

    def notable_regions(self) -> list[dict[str, object]]:
        """Return the principal structural components of the galaxy.

        Returns
        -------
        list[dict[str, object]]
            Four component-region dicts, each with keys ``name`` (str),
            ``description`` (str).

        Order: Galactic Center / Bulge, Halo, Disk, Spiral Arms.
        """
        return [
            {
                "name": "Galactic Center / Bulge",
                "description": (
                    "Dense, roughly spheroidal central concentration of "
                    "old population II stars ~10 000 ly across, hosting the "
                    "supermassive black hole Sagittarius A* and the "
                    "galactic bar."
                ),
            },
            {
                "name": "Halo",
                "description": (
                    "Sparse, roughly spherical envelope of old stars and "
                    "globular clusters extending up to ~200 000 ly from "
                    "the center; contains most of the galaxy's dark matter."
                ),
            },
            {
                "name": "Disk",
                "description": (
                    "Thin (~1000 ly) and thick (~3000 ly) rotating disk of "
                    "gas, dust, and young-to-intermediate population I stars "
                    "where most active star formation occurs."
                ),
            },
            {
                "name": "Spiral Arms",
                "description": (
                    "Density-wave concentrations within the disk giving the "
                    "galaxy its spiral pattern; four major arms carry the "
                    "bulk of the H II regions and young O/B associations."
                ),
            },
        ]

    def notable_objects(self) -> list[dict[str, object]]:
        """Return a catalogue of prominent deep-sky objects.

        The catalogue mixes in-galaxy and Local Group targets so the
        astromech can reason about both internal structure and nearby
        galaxies.  Coordinates are J2000 right ascension (degrees) and
        declination (degrees).

        Returns
        -------
        list[dict[str, object]]
            Each entry has keys: ``name`` (str), ``type`` (str),
            ``ra_degrees`` (float), ``dec_degrees`` (float),
            ``distance_ly`` (float), ``description`` (str).
        """
        return [
            {
                "name": "Sagittarius A*",
                "type": "Supermassive black hole",
                "ra_degrees": 266.42,
                "dec_degrees": -29.01,
                "distance_ly": 26_000,
                "description": (
                    "The 4.1-million solar-mass black hole at the dynamical "
                    "center of the Milky Way; the defining point mass of the "
                    "galactic center."
                ),
            },
            {
                "name": "Omega Centauri (NGC 5139)",
                "type": "Globular cluster",
                "ra_degrees": 201.30,
                "dec_degrees": -47.48,
                "distance_ly": 15_800,
                "description": (
                    "Largest and most massive globular cluster in the "
                    "galaxy; may be the stripped core of a dwarf galaxy."
                ),
            },
            {
                "name": "47 Tucanae (NGC 104)",
                "type": "Globular cluster",
                "ra_degrees": 6.02,
                "dec_degrees": -72.08,
                "distance_ly": 13_400,
                "description": (
                    "Second-brightest globular cluster, rich and dense, in "
                    "the southern constellation Tucana."
                ),
            },
            {
                "name": "Carina Nebula (NGC 3372)",
                "type": "Emission nebula",
                "ra_degrees": 161.27,
                "dec_degrees": -59.69,
                "distance_ly": 7_500,
                "description": (
                    "Large, bright star-forming region containing the "
                    "homunculus around the massive variable star Eta Carinae."
                ),
            },
            {
                "name": "Orion Nebula (M42, NGC 1976)",
                "type": "Emission nebula",
                "ra_degrees": 83.82,
                "dec_degrees": -5.39,
                "distance_ly": 1_344,
                "description": (
                    "Nearest massive star-forming region to Earth; the "
                    "showpiece of the Orion OB1 association."
                ),
            },
            {
                "name": "Crab Nebula (M1, NGC 1952)",
                "type": "Supernova remnant",
                "ra_degrees": 83.63,
                "dec_degrees": 22.01,
                "distance_ly": 6_500,
                "description": (
                    "Remnant of the 1054 CE supernova, powered by the Crab "
                    "pulsar at its core."
                ),
            },
            {
                "name": "Large Magellanic Cloud (LMC)",
                "type": "Dwarf galaxy (satellite)",
                "ra_degrees": 80.89,
                "dec_degrees": -69.76,
                "distance_ly": 163_000,
                "description": (
                    "Satellite dwarf galaxy of the Milky Way; site of "
                    "Supernova 1987A and the Tarantula Nebula."
                ),
            },
            {
                "name": "Small Magellanic Cloud (SMC)",
                "type": "Dwarf galaxy (satellite)",
                "ra_degrees": 13.16,
                "dec_degrees": -72.80,
                "distance_ly": 197_000,
                "description": (
                    "Smaller satellite dwarf galaxy of the Milky Way, "
                    "interacting with the LMC via a tidal bridge."
                ),
            },
            {
                "name": "Andromeda Galaxy (M31, NGC 224)",
                "type": "Spiral galaxy",
                "ra_degrees": 10.68,
                "dec_degrees": 41.27,
                "distance_ly": 2_537_000,
                "description": (
                    "Nearest large spiral galaxy; approaching the Milky Way "
                    "for a future merger ~4.5 Gyr from now."
                ),
            },
            {
                "name": "Triangulum Galaxy (M33, NGC 598)",
                "type": "Spiral galaxy",
                "ra_degrees": 23.46,
                "dec_degrees": 30.66,
                "distance_ly": 2_723_000,
                "description": (
                    "Third-largest galaxy of the Local Group; a smaller "
                    "spiral satellite of the Andromeda system."
                ),
            },
        ]

    # ------------------------------------------------------------------
    # Coordinate transformation
    # ------------------------------------------------------------------
    def galactic_to_equatorial(
        self, galactic_lon: float, galactic_lat: float
    ) -> dict[str, float]:
        """Convert galactic coordinates to equatorial (J2000) coordinates.

        The galactic system is defined by two J2000 reference directions:

        * **North Galactic Pole (NGP)** — RA 192.85948°, Dec 27.12825° —
          the +Z axis of the galactic frame (latitude ``b = +90°``).
        * **Galactic Center (GC)** — RA 266.40510°, Dec -28.93615° —
          the ``l = 0°, b = 0°`` direction.

        The transform builds a 3×3 rotation matrix from an orthonormal
        basis (``ẑ`` = NGP, ``x̂`` = GC, ``ŷ`` = ẑ × x̂) and applies it to
        the galactic unit direction vector ``r_gal``::

            r_gal = ( cos b · cos l,  cos b · sin l,  sin b )
            r_eq  = R · r_gal

        then converts the equatorial Cartesian vector back to RA / Dec.
        This is the same construction used by astropy and SLALIB and is
        exact for a direction (unit vector) — no parallax or proper motion.

        Parameters
        ----------
        galactic_lon : float
            Galactic longitude ``l`` in degrees, 0°–360°, measured from the
            galactic center (Sgr A*) increasing counter-clockwise.
        galactic_lat : float
            Galactic latitude ``b`` in degrees, -90°–+90°, positive north of
            the galactic plane.

        Returns
        -------
        dict[str, float]
            ``{'ra_degrees': float, 'dec_degrees': float}`` in the range
            RA 0–360°, Dec -90°–+90°, J2000 equinox.

        Examples
        --------
        >>> mw = MilkyWay()
        >>> c = mw.galactic_to_equatorial(0.0, 0.0)          # galactic center
        >>> abs(c["ra_degrees"] - 266.4) < 0.05
        True
        >>> c = mw.galactic_to_equatorial(0.0, 90.0)         # north galactic pole
        >>> abs(c["dec_degrees"] - 27.13) < 0.05
        True
        """
        # --- 1. Build the equatorial orthonormal basis for the galactic frame
        # x̂  = unit vector toward galactic center   (l=0, b=0)
        # ẑ  = unit vector toward north galactic pole (l=0, b=90)
        # ŷ  = ẑ × x̂  (completes the right-handed triad; points to l=90, b=0)
        gc_ra = math.radians(self._GC_RA_DEG)
        gc_dec = math.radians(self._GC_DEC_DEG)
        ngp_ra = math.radians(self._NGP_RA_DEG)
        ngp_dec = math.radians(self._NGP_DEC_DEG)

        x = (
            math.cos(gc_dec) * math.cos(gc_ra),
            math.cos(gc_dec) * math.sin(gc_ra),
            math.sin(gc_dec),
        )
        z = (
            math.cos(ngp_dec) * math.cos(ngp_ra),
            math.cos(ngp_dec) * math.sin(ngp_ra),
            math.sin(ngp_dec),
        )
        # y = z × x  (right-handed)
        y = (
            z[1] * x[2] - z[2] * x[1],
            z[2] * x[0] - z[0] * x[2],
            z[0] * x[1] - z[1] * x[0],
        )

        # --- 2. Build the galactic unit direction vector ------------------
        l_rad = math.radians(galactic_lon)
        b_rad = math.radians(galactic_lat)
        cos_b = math.cos(b_rad)
        r_gal = (
            cos_b * math.cos(l_rad),   # component along x̂ (toward GC)
            cos_b * math.sin(l_rad),   # component along ŷ (l=90°)
            math.sin(b_rad),           # component along ẑ (toward NGP)
        )

        # --- 3. Rotate into the equatorial frame: r_eq = x·rx + y·ry + z·rz
        r_eq = (
            x[0] * r_gal[0] + y[0] * r_gal[1] + z[0] * r_gal[2],
            x[1] * r_gal[0] + y[1] * r_gal[1] + z[1] * r_gal[2],
            x[2] * r_gal[0] + y[2] * r_gal[1] + z[2] * r_gal[2],
        )

        # --- 4. Convert equatorial Cartesian → spherical (RA, Dec) ---------
        rx, ry, rz = r_eq
        # Clamp to the valid domain of asin to guard against round-off.
        rz_clamped = max(-1.0, min(1.0, rz))
        dec = math.degrees(math.asin(rz_clamped))
        ra = math.degrees(math.atan2(ry, rx)) % 360.0

        return {"ra_degrees": ra, "dec_degrees": dec}

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    def info(self) -> dict[str, object]:
        """Return a consolidated information dict about the galaxy.

        Aggregates the gross structure, arm list, region list, and object
        catalogue into a single nested dictionary for quick serialization.

        Returns
        -------
        dict[str, object]
            Keys: ``structure`` (the :attr:`GALACTIC_STRUCTURE` dict),
            ``arms`` (list of arm dicts), ``regions`` (list of region
            dicts), ``objects`` (list of object dicts).
        """
        return {
            "structure": dict(self.GALACTIC_STRUCTURE),
            "arms": self.galactic_arms(),
            "regions": self.notable_regions(),
            "objects": self.notable_objects(),
        }

    def summary(self) -> str:
        """Return a human-readable multi-line summary of the Milky Way.

        Returns
        -------
        str
            A formatted multi-paragraph string suitable for display to the
            operator.
        """
        s = self.GALACTIC_STRUCTURE
        lines: list[str] = []
        lines.append("=== Milky Way Galaxy — Structural Summary ===")
        lines.append("")
        lines.append("Physical parameters:")
        lines.append(
            f"  Diameter: {s['diameter_ly']:,} light-years"
        )
        lines.append(
            f"  Disk thickness: {s['thickness_ly']:,} light-years"
        )
        lines.append(
            f"  Estimated stars: {s['num_stars_estimated']:,}"
        )
        lines.append(f"  Central black hole: {s['central_black_hole']}")
        lines.append(
            f"  Sun distance from center: {s['sun_distance_from_center_ly']:,} ly"
        )
        lines.append(
            f"  Galactic center (J2000): "
            f"RA {s['galactic_center_ra']}°, Dec {s['galactic_center_dec']}°"
        )
        lines.append(
            f"  Rotation speed: {s['rotation_speed_km_s']} km/s  "
            f"(period ~{s['rotation_period_myr']} Myr)"
        )
        lines.append("")
        lines.append("Major spiral arms:")
        for arm in self.galactic_arms():
            lines.append(
                f"  • {arm['name']}: "
                f"{arm['distance_from_center_ly']:,} ly from center — "
                f"{arm['description']}"
            )
        lines.append("")
        lines.append("Structural regions:")
        for region in self.notable_regions():
            lines.append(f"  • {region['name']}: {region['description']}")
        lines.append("")
        lines.append("Notable objects (J2000 RA/Dec):")
        for obj in self.notable_objects():
            lines.append(
                f"  • {obj['name']} ({obj['type']}): "
                f"RA {obj['ra_degrees']}°, Dec {obj['dec_degrees']}°, "
                f"distance {obj['distance_ly']:,} ly — {obj['description']}"
            )
        lines.append("")
        lines.append("=== End of summary ===")
        return "\n".join(lines)


# ==================================================================
# Module-level convenience: a shared default instance.
# ==================================================================
_DEFAULT_MILKY_WAY: MilkyWay | None = None


def get_default() -> MilkyWay:
    """Return a shared default :class:`MilkyWay` instance (module-level cache).

    Returns
    -------
    MilkyWay
        A lazily-created, cached singleton for convenience callers that do
        not need their own instance.
    """
    global _DEFAULT_MILKY_WAY
    if _DEFAULT_MILKY_WAY is None:
        _DEFAULT_MILKY_WAY = MilkyWay()
    return _DEFAULT_MILKY_WAY