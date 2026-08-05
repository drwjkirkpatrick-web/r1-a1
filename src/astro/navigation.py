"""Celestial navigation module for the R1-A1 astromech droid.

This module provides the :class:`Navigation` class, a small, dependency-free
celestial-navigation toolkit that converts between the two most common
astronomical coordinate frames:

* **Horizontal / horizon coordinates** -- *altitude* (alt) and *azimuth* (az),
  the direction of an object as seen from a particular place on Earth at a
  particular instant.  Altitude is measured up from the horizon (0° at the
  horizon, 90° at the zenith); azimuth is measured clockwise around the horizon
  from true North (0° = North, 90° = East, 180° = South, 270° = West).

* **Equatorial coordinates** -- *right ascension* (RA) and *declination* (dec),
  a fixed frame tied to the stars.  RA is measured eastward along the celestial
  equator and is expressed in **hours** (0-24 h, where 24 h = 360°, so 1 h of
  RA = 15°).  Declination is measured north/south of the celestial equator in
  **degrees** (-90° to +90°).

The bridge between the two frames is the **Local Sidereal Time** (LST), which
tells us how far the celestial sphere has rotated above the observer.  The
fundamental relationship is::

        Hour Angle (HA) = LST - RA

where HA is how far an object has moved westward since crossing the meridian.
Once we know HA, latitude, and declination, spherical trigonometry gives us
altitude and azimuth (and vice-versa).

Reference formulas
------------------
The conversions use the standard spherical-triangle identities (see e.g.
Meeus, *Astronomical Algorithms*, or Smart, *Text-Book on Spherical
Astronomy*)::

    sin(alt) = sin(lat)·sin(dec) + cos(lat)·cos(dec)·cos(HA)
    sin(az)  = -cos(dec)·sin(HA) / cos(alt)
    cos(az)  = (sin(dec) - sin(lat)·sin(alt)) / (cos(lat)·cos(alt))

and, inverting the first two for the alt/az -> RA/dec direction::

    sin(dec) = sin(lat)·sin(alt) + cos(lat)·cos(alt)·cos(az)
    sin(HA)  = -sin(az)·cos(alt) / cos(dec)
    cos(HA)  = (sin(alt) - sin(lat)·sin(dec)) / (cos(lat)·cos(dec))

The Local Sidereal Time (in degrees) uses the classic low-precision
approximation::

    LST = (100.46 + 0.985647·d + lon + 15·UT)  (mod 360)

where ``d`` is the number of (fractional) days since the J2000.0 epoch
(2000-01-01 12:00 UTC, JD 2451545.0), ``lon`` is the observer's east-positive
longitude in degrees, and ``UT`` is Universal Time in decimal hours.

Design notes
------------
* **Pure standard library** -- only :mod:`math`, :mod:`datetime` and
  :mod:`typing` are used, so the module imports cleanly on any Python 3.12
  install with no third-party packages.
* All trigonometry is done in **radians** internally; conversions to/from
  degrees/hours happen only at the public API boundary.
* Numerical edge cases (object at the zenith, observer at a pole, pointing at a
  celestial pole) are guarded with small epsilon checks so the functions never
  divide by zero.
* The module is written as a *learning* reference: the comments explain *why*
  each step is taken, not merely *what* is computed.

Learning annotations are placed throughout the code as inline comments.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Final

# ---------------------------------------------------------------------------
# J2000.0 epoch -- the fundamental reference epoch for modern astrometry.
# Julian Day 2451545.0 corresponds to 2000-01-01 at 12:00:00 UTC (noon, not
# midnight -- a common source of off-by-one-day errors).  We keep it as a
# timezone-aware UTC instant so subtraction is always well defined.
# ---------------------------------------------------------------------------
_J2000_EPOCH: Final[datetime] = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# A small value used to guard against division by (near) zero when an object
# sits at a celestial/horizon pole, where the relevant cosine collapses to 0.
_EPS: Final[float] = 1e-12

# ---------------------------------------------------------------------------
# The 12 classical navigational stars.  These are the bright, well-spread
# reference stars traditionally used for celestial navigation at sea and in
# aviation.  RA is given in *hours*, declination in *degrees* (J2000
# approximate mean places).  ``identify_star`` searches this table.
# ---------------------------------------------------------------------------
_NAVIGATIONAL_STARS: Final[dict[str, dict[str, float]]] = {
    'Polaris': {'ra': 2.53, 'dec': 89.26},
    'Vega': {'ra': 18.62, 'dec': 38.78},
    'Sirius': {'ra': 6.75, 'dec': -16.72},
    'Betelgeuse': {'ra': 5.92, 'dec': 7.41},
    'Rigel': {'ra': 5.24, 'dec': -8.20},
    'Arcturus': {'ra': 14.26, 'dec': 19.18},
    'Antares': {'ra': 16.49, 'dec': -26.43},
    'Deneb': {'ra': 20.69, 'dec': 45.28},
    'Altair': {'ra': 19.85, 'dec': 8.87},
    'Aldebaran': {'ra': 4.60, 'dec': 16.51},
    'Spica': {'ra': 13.42, 'dec': -11.16},
    'Capella': {'ra': 5.28, 'dec': 45.99},
}


class Navigation:
    """Celestial-navigation coordinate converter.

    An instance is bound to an observer's geographic location (latitude and
    longitude) and then provides conversions between horizon coordinates
    (altitude/azimuth) and equatorial coordinates (right ascension /
    declination) for any UTC instant.

    Parameters
    ----------
    latitude:
        Observer latitude in decimal degrees, north positive (e.g. ``34.05``
        for +34.05°).  Defaults to ``0.0`` (the equator).
    longitude:
        Observer longitude in decimal degrees, **east positive** (e.g.
        ``-118.24`` for 118.24° west / Los Angeles).  Defaults to ``0.0``
        (Greenwich).

    Attributes
    ----------
    latitude, longitude:
        The currently set observer location in decimal degrees.

    Examples
    --------
    >>> nav = Navigation(latitude=34.05, longitude=-118.24)
    >>> nav.set_location(-33.87, 151.21)        # Sydney, Australia
    >>> eq = nav.altaz_to_radec(45.0, 180.0, '2026-08-04T22:00:00')
    >>> 'ra_hours' in eq and 'dec_degrees' in eq
    True
    >>> hor = nav.radec_to_altaz(eq['ra_hours'], eq['dec_degrees'],
    ...                          '2026-08-04T22:00:00')
    >>> round(hor['alt_degrees'], 1) == 45.0
    True
    """

    # -- construction & location -------------------------------------------------
    def __init__(self, latitude: float = 0.0, longitude: float = 0.0) -> None:
        """Create a navigation helper at the given geographic location."""
        # Store the observer's position.  East-positive longitude is the
        # astronomical convention and is what the LST formula expects.
        self.latitude: float = float(latitude)
        self.longitude: float = float(longitude)

    def set_location(self, lat: float, lon: float) -> None:
        """Update the observer's latitude (degrees N+) and longitude (degrees E+).

        This lets a single :class:`Navigation` instance be reused as the
        astromech moves across the galaxy.
        """
        self.latitude = float(lat)
        self.longitude = float(lon)

    # -- datetime / time helpers -------------------------------------------------
    @staticmethod
    def _parse_datetime(datetime_str: str) -> datetime:
        """Parse an ISO-8601 UTC timestamp into a timezone-aware UTC datetime.

        A naive (offset-less) string is assumed to already be UTC, which is the
        convention used throughout this module.  Timezone-aware inputs are
        converted to UTC so the rest of the math can rely on a single frame.
        """
        # ``datetime.fromisoformat`` (3.11+) happily accepts 'Z', offsets, and
        # a space-or-'T' separator.
        dt = datetime.fromisoformat(datetime_str)
        if dt.tzinfo is None:
            # Treat naive timestamps as UTC by attaching the UTC tzinfo.
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Normalise any other timezone to UTC for consistent math below.
            dt = dt.astimezone(timezone.utc)
        return dt

    @staticmethod
    def _days_since_j2000(dt: datetime) -> float:
        """Fractional days elapsed since the J2000.0 epoch (JD 2451545.0).

        Because J2000.0 is defined at *noon* UTC, this value carries a half-day
        phase that is correctly absorbed by the LST approximation used here
        (see the module docstring for the derivation).
        """
        return (dt - _J2000_EPOCH).total_seconds() / 86400.0

    def _local_sidereal_time_degrees(self, datetime_str: str) -> float:
        """Approximate Local Sidereal Time in degrees for the observer.

        Uses the classic low-precision formula::

            LST = (100.46 + 0.985647·d + lon + 15·UT) mod 360

        where ``d`` is fractional days since J2000.0 and ``UT`` is Universal
        Time in decimal hours.  Accurate to a few arcminutes -- more than
        enough for R1-A1's navigational needs.
        """
        dt = self._parse_datetime(datetime_str)
        d = self._days_since_j2000(dt)
        # UT expressed as decimal hours since 00:00 UTC.
        ut_hours = (
            dt.hour
            + dt.minute / 60.0
            + dt.second / 3600.0
            + dt.microsecond / 3_600_000_000.0
        )
        # Assemble the LST in degrees and fold into [0, 360).
        lst = (100.46 + 0.985647 * d + self.longitude + 15.0 * ut_hours) % 360.0
        return lst

    # -- horizon -> equatorial ---------------------------------------------------
    def altaz_to_radec(
        self, alt: float, az: float, datetime_str: str
    ) -> dict[str, float]:
        """Convert horizon coordinates (alt, az) to equatorial (RA, dec).

        Parameters
        ----------
        alt:
            Altitude above the horizon in degrees (0 = horizon, 90 = zenith).
        az:
            Azimuth in degrees measured clockwise from North
            (0 = N, 90 = E, 180 = S, 270 = W).
        datetime_str:
            ISO-8601 UTC timestamp of the observation.

        Returns
        -------
        dict
            ``{'ra_hours': float, 'dec_degrees': float}`` with RA in hours
            (0-24) and declination in degrees (-90 to +90).
        """
        # Work in radians for all trig calls.
        lat_r = math.radians(self.latitude)
        alt_r = math.radians(alt)
        az_r = math.radians(az)

        # --- Declination from the spherical-triangle identity ---
        #   sin(dec) = sin(lat)·sin(alt) + cos(lat)·cos(alt)·cos(az)
        sin_dec = (
            math.sin(lat_r) * math.sin(alt_r)
            + math.cos(lat_r) * math.cos(alt_r) * math.cos(az_r)
        )
        # Clamp to [-1, 1] to absorb tiny floating-point overshoot before asin.
        sin_dec = max(-1.0, min(1.0, sin_dec))
        dec_r = math.asin(sin_dec)
        dec_degrees = math.degrees(dec_r)
        cos_dec = math.cos(dec_r)
        cos_lat = math.cos(lat_r)

        # --- Hour angle (HA) from its sine and cosine ---
        #   sin(HA) = -sin(az)·cos(alt) / cos(dec)
        #   cos(HA) = (sin(alt) - sin(lat)·sin(dec)) / (cos(lat)·cos(dec))
        # atan2(sin, cos) then resolves the correct quadrant.
        if abs(cos_dec) < _EPS:
            # Object at a celestial pole: HA is undefined from sin(HA) alone.
            sin_ha = 0.0
        else:
            sin_ha = -math.sin(az_r) * math.cos(alt_r) / cos_dec
        if abs(cos_lat) < _EPS or abs(cos_dec) < _EPS:
            # Observer at a geographic pole, or target at a celestial pole:
            # cos(HA) denominator collapses; default to the meridian (HA = 0).
            cos_ha = 1.0
        else:
            cos_ha = (math.sin(alt_r) - math.sin(lat_r) * sin_dec) / (
                cos_lat * cos_dec
            )
        sin_ha = max(-1.0, min(1.0, sin_ha))
        cos_ha = max(-1.0, min(1.0, cos_ha))
        ha_r = math.atan2(sin_ha, cos_ha)  # range (-pi, pi]

        # Fold HA into [0, 360) degrees for clean arithmetic with LST.
        ha_deg = math.degrees(ha_r) % 360.0

        # --- Right ascension from the fundamental relation RA = LST - HA ---
        lst_deg = self._local_sidereal_time_degrees(datetime_str)
        ra_deg = (lst_deg - ha_deg) % 360.0
        # RA is conventionally reported in hours (24 h = 360°).
        ra_hours = ra_deg / 15.0

        return {'ra_hours': ra_hours, 'dec_degrees': dec_degrees}

    # -- equatorial -> horizon ---------------------------------------------------
    def radec_to_altaz(
        self, ra_hours: float, dec_degrees: float, datetime_str: str
    ) -> dict[str, float]:
        """Convert equatorial coordinates (RA, dec) to horizon (alt, az).

        Parameters
        ----------
        ra_hours:
            Right ascension in hours (0-24).
        dec_degrees:
            Declination in degrees (-90 to +90).
        datetime_str:
            ISO-8601 UTC timestamp of the observation.

        Returns
        -------
        dict
            ``{'alt_degrees': float, 'az_degrees': float}`` with azimuth in
            degrees (0-360, clockwise from North) and altitude in degrees
            (-90 to +90).
        """
        lat_r = math.radians(self.latitude)
        dec_r = math.radians(dec_degrees)
        cos_lat = math.cos(lat_r)

        # --- Hour angle: HA = LST - RA ---
        # Bring RA and LST both into degrees, then subtract.
        lst_deg = self._local_sidereal_time_degrees(datetime_str)
        ra_deg = ra_hours * 15.0
        ha_deg = (lst_deg - ra_deg) % 360.0
        ha_r = math.radians(ha_deg)

        # --- Altitude from the identity ---
        #   sin(alt) = sin(lat)·sin(dec) + cos(lat)·cos(dec)·cos(HA)
        sin_alt = (
            math.sin(lat_r) * math.sin(dec_r)
            + math.cos(lat_r) * math.cos(dec_r) * math.cos(ha_r)
        )
        sin_alt = max(-1.0, min(1.0, sin_alt))
        alt_r = math.asin(sin_alt)
        alt_deg = math.degrees(alt_r)
        cos_alt = math.cos(alt_r)

        # --- Azimuth from its sine and cosine (atan2 resolves the quadrant) ---
        #   sin(az) = -cos(dec)·sin(HA) / cos(alt)
        #   cos(az) = (sin(dec) - sin(lat)·sin(alt)) / (cos(lat)·cos(alt))
        if abs(cos_alt) < _EPS:
            # Object at the zenith: azimuth is geometrically undefined.
            sin_az = 0.0
            cos_az = 1.0
        else:
            sin_az = -math.cos(dec_r) * math.sin(ha_r) / cos_alt
            if abs(cos_lat) < _EPS:
                # Observer at a geographic pole: use sin(az) only.
                cos_az = 1.0
            else:
                cos_az = (math.sin(dec_r) - math.sin(lat_r) * sin_alt) / (
                    cos_lat * cos_alt
                )
        sin_az = max(-1.0, min(1.0, sin_az))
        cos_az = max(-1.0, min(1.0, cos_az))
        az_r = math.atan2(sin_az, cos_az)
        az_deg = math.degrees(az_r) % 360.0

        return {'alt_degrees': alt_deg, 'az_degrees': az_deg}

    # -- angular separation -----------------------------------------------------
    @staticmethod
    def angular_separation(
        ra1: float, dec1: float, ra2: float, dec2: float
    ) -> float:
        """Great-circle angular separation between two sky positions.

        Uses the haversine formula, which is numerically stable for small
        separations (unlike the plain spherical-law-of-cosines form).

        Parameters
        ----------
        ra1, ra2:
            Right ascensions in *hours* (0-24).
        dec1, dec2:
            Declinations in *degrees* (-90 to +90).

        Returns
        -------
        float
            Angular separation in **degrees** (0-180).
        """
        # Convert RA from hours to degrees and then to radians, and dec to
        # radians directly -- haversine needs both quantities in the same
        # angular unit.
        ra1_r = math.radians(ra1 * 15.0)
        dec1_r = math.radians(dec1)
        ra2_r = math.radians(ra2 * 15.0)
        dec2_r = math.radians(dec2)

        d_ra = ra2_r - ra1_r
        d_dec = dec2_r - dec1_r

        # haversine: a = sin²(Δdec/2) + cos(dec1)·cos(dec2)·sin²(Δra/2)
        a = (
            math.sin(d_dec / 2.0) ** 2
            + math.cos(dec1_r) * math.cos(dec2_r) * math.sin(d_ra / 2.0) ** 2
        )
        # Clamp a to [0, 1] to protect against floating-point excursions.
        a = max(0.0, min(1.0, a))
        # c = 2·atan2(√a, √(1-a)); the central angle in radians.
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return math.degrees(c)

    # -- navigational star catalog ----------------------------------------------
    @staticmethod
    def constellations() -> dict[str, dict[str, float]]:
        """Return the 12 classical navigational stars with RA/dec.

        Each entry maps a star name to ``{'ra': <hours>, 'dec': <degrees>}``
        using approximate J2000 mean places.  These are the bright, widely
        separated beacons traditionally used for celestial position fixing.
        """
        # Return a fresh copy so callers cannot mutate the module-level table.
        return {
            'Polaris': {'ra': 2.53, 'dec': 89.26},
            'Vega': {'ra': 18.62, 'dec': 38.78},
            'Sirius': {'ra': 6.75, 'dec': -16.72},
            'Betelgeuse': {'ra': 5.92, 'dec': 7.41},
            'Rigel': {'ra': 5.24, 'dec': -8.20},
            'Arcturus': {'ra': 14.26, 'dec': 19.18},
            'Antares': {'ra': 16.49, 'dec': -26.43},
            'Deneb': {'ra': 20.69, 'dec': 45.28},
            'Altair': {'ra': 19.85, 'dec': 8.87},
            'Aldebaran': {'ra': 4.60, 'dec': 16.51},
            'Spica': {'ra': 13.42, 'dec': -11.16},
            'Capella': {'ra': 5.28, 'dec': 45.99},
        }

    # -- star identification -----------------------------------------------------
    def identify_star(
        self,
        alt: float,
        az: float,
        datetime_str: str,
        magnitude: float | None = None,
    ) -> str:
        """Identify the navigational star nearest to a given alt/az position.

        The observed (alt, az) is first converted to equatorial coordinates
        with :meth:`altaz_to_radec`, then the closest entry in the
        navigational-star catalog is found by minimum angular separation.

        Parameters
        ----------
        alt, az:
            Observed altitude and azimuth in degrees.
        datetime_str:
            ISO-8601 UTC timestamp of the observation.
        magnitude:
            Optional observed visual magnitude of the target.  It is
            *accepted* (so callers can pass it) and reserved for a future
            photometric disambiguation step when two stars sit close together
            on the sky; it does not currently alter the result.

        Returns
        -------
        str
            The name of the closest navigational star.
        """
        # Convert the sighted position to the equatorial frame so it can be
        # compared directly with the catalog's RA/dec values.
        coords = self.altaz_to_radec(alt, az, datetime_str)
        ra = coords['ra_hours']
        dec = coords['dec_degrees']

        # ``magnitude`` is accepted for forward compatibility with brightness
        # filtering; it is intentionally unused in the current nearest-match
        # logic (see the parameter docs above).
        _ = magnitude  # noqa: F841  -- acknowledged-but-reserved parameter

        stars = self.constellations()
        best_name: str | None = None
        best_sep = float('inf')
        for name, info in stars.items():
            sep = self.angular_separation(ra, dec, info['ra'], info['dec'])
            if sep < best_sep:
                best_sep = sep
                best_name = name

        # best_name is guaranteed non-None because the catalog is non-empty.
        assert best_name is not None
        return best_name


# ---------------------------------------------------------------------------
# Small self-demo -- lets the module be run directly to sanity-check the
# round-trip conversions.  ``python -m astro.navigation`` (or
# ``python navigation.py``) prints a short report.
# ---------------------------------------------------------------------------
def _demo() -> None:  # pragma: no cover - manual sanity check
    nav = Navigation(latitude=34.05, longitude=-118.24)  # Los Angeles
    when = '2026-08-04T22:00:00'
    eq = nav.altaz_to_radec(alt=45.0, az=180.0, datetime_str=when)
    print('alt/az -> RA/dec :', eq)
    back = nav.radec_to_altaz(eq['ra_hours'], eq['dec_degrees'], when)
    print('RA/dec -> alt/az:', back)
    print('identified star :', nav.identify_star(45.0, 180.0, when))
    print('Polaris-Vega sep:', round(
        nav.angular_separation(2.53, 89.26, 18.62, 38.78), 3), 'deg')


if __name__ == '__main__':  # pragma: no cover
    _demo()