"""Solar system body tracking for the R1-A1 astromech.

This module computes the apparent positions of the Sun, Moon, and eight
planets from standard Keplerian orbital elements at the J2000.0 epoch.
It is pure stdlib (math, datetime, typing) and uses no external astronomy
library so it can run anywhere the robot can — including offline on a
Jetson.

== Overview ===========================================================

For each body we store six osculating orbital elements referred to the
ecliptic of J2000.0 (plus a mean daily motion):

    a       semi-major axis, in astronomical units (AU)
    e       eccentricity (dimensionless)
    i       inclination of the orbit to the ecliptic, in degrees
    Omega   longitude of the ascending node, in degrees
    omega   argument of perihelion, in degrees
    M0      mean anomaly at the J2000.0 epoch, in degrees
    n       mean daily motion, in degrees per day

From these, for a given instant, the position is found by:

    1. Advancing the mean anomaly:  M = M0 + n * d
       where d is the number of days since J2000.0.

    2. Solving Kepler's equation for the eccentric anomaly E:
           M = E - e * sin(E)
       solved iteratively (Newton–Raphson, see solve_kepler).

    3. Computing the body's rectangular coordinates in its *orbital
       plane* (perifocal frame, x-axis toward perihelion):
           x' = a * (cos(E) - e)
           y' = a * sqrt(1 - e^2) * sin(E)
           z' = 0

    4. Rotating from the orbital plane to the heliocentric (or, for the
       Sun and Moon, geocentric) ecliptic frame by applying three Euler
       rotations, in order:
           R3(-omega)   … rotate by the argument of perihelion
           R1(-i)       … tilt the plane by the inclination
           R3(-Omega)   … rotate to the ascending node
       The combined matrix is the classical
           x_ecl = r * (cos(Omega+omega+nu) * cos i ... ) form; we build
       it as the product of three matrices below for clarity.

    5. Converting ecliptic rectangular coordinates (x, y, z) to
       equatorial coordinates by rotating about the x-axis by the
       obliquity of the ecliptic (epsilon = 23.44 deg):
           X = x
           Y = y * cos(eps) - z * sin(eps)
           Z = y * sin(eps) + z * cos(eps)

    6. Converting equatorial rectangular coordinates to right
       ascension and declination:
           ra  = atan2(Y, X)        … normalised to [0, 24) hours
           dec = asin(Z / r)       … in degrees
       where r = sqrt(X^2 + Y^2 + Z^2) is the distance.

== Notes on the "Sun" and "Moon" entries ===============================

The Sun's elements here are the *geocentric* orbital elements of the
Sun (which mirror Earth's heliocentric orbit): Earth's mean longitude of
perihelion (102.94 deg) is used for omega, and Earth's mean anomaly and
daily motion are reused.  Distance is therefore the Earth–Sun distance.

The Moon's entry is a heavily simplified mean-lunar-orbit model: a
fixed a, e, i, with Omega = omega = M0 = 0 and the sidereal mean daily
motion n = 13.176 deg/day.  This is accurate to a few degrees at best
and is intended only as a placeholder until a full ELP/Meeus lunar
theory is substituted; the real lunar orbit precesses roughly every
18.6 years and needs a nutation/ΔT correction for precision pointing.

== J2000.0 epoch ======================================================

J2000.0 is 2000-01-01 12:00:00 TT (Julian date 2451545.0).  We treat
input datetimes as UTC/TT-equivalent for this simplified model; for
arcminute-level pointing a proper ΔT correction (≈ 69 s in 2024) should
be added.

== Learning annotations ===============================================

Lines tagged `# LEARN:` point at subtleties worth re-reading later:
    - the sign conventions of the three Euler rotations,
    - the normalisation of RA to [0, 24) hours,
    - the Newton–Raphson iteration for Kepler's equation,
    - the geocentric shortcut for the Sun.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, Final, List

__all__: Final[List[str]] = [
    "SolarSystem",
]


# --- Constants --------------------------------------------------------

# Obliquity of the ecliptic at J2000.0, in degrees.
OBLIQUITY_DEG: Final[float] = 23.44

# J2000.0 epoch as a UTC datetime (TT ≈ UTC for this simplified model).
J2000: Final[datetime] = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# Julian date of the J2000.0 epoch.
JD_J2000: Final[float] = 2451545.0


class SolarSystem:
    """Keplerian solar-system ephemeris for the R1-A1 astromech.

    Holds osculating orbital elements for the Sun, Moon and eight planets
    referred to the J2000.0 ecliptic, and computes apparent RA/Dec and
    distance for any UTC instant.  All angles in the element table are in
    degrees and are converted to radians internally.

    The model is a first-order (mean-element) ephemeris: it reproduces
    planetary positions to a fraction of a degree for the inner planets
    and to a degree or so for the outer planets over a few decades
    around J2000.0.  It is *not* a substitute for JPL DE-series
    ephemerides, but it is cheap, dependency-free, and good enough to
    point the dome at a target.
    """

    # Orbital elements at J2000.0 (mean equinox of date ≈ J2000).
    #
    # Keys map to a dict of seven elements.  Units:
    #   semi_major_axis_au          — AU
    #   eccentricity                — dimensionless
    #   inclination_deg             — degrees
    #   longitude_ascending_node_deg — degrees (Omega)
    #   argument_of_perihelion_deg  — degrees (omega)
    #   mean_anomaly_at_epoch_deg   — degrees (M0)
    #   mean_daily_motion_deg       — degrees per day (n)
    ORBITAL_ELEMENTS: Final[Dict[str, Dict[str, float]]] = {
        "Mercury": {
            "semi_major_axis_au": 0.387,
            "eccentricity": 0.206,
            "inclination_deg": 7.00,
            "longitude_ascending_node_deg": 48.33,
            "argument_of_perihelion_deg": 29.12,
            "mean_anomaly_at_epoch_deg": 174.80,
            "mean_daily_motion_deg": 4.09234,
        },
        "Venus": {
            "semi_major_axis_au": 0.723,
            "eccentricity": 0.007,
            "inclination_deg": 3.39,
            "longitude_ascending_node_deg": 76.68,
            "argument_of_perihelion_deg": 54.85,
            "mean_anomaly_at_epoch_deg": 50.38,
            "mean_daily_motion_deg": 1.60213,
        },
        "Earth": {
            "semi_major_axis_au": 1.000,
            "eccentricity": 0.017,
            "inclination_deg": 0.00,
            "longitude_ascending_node_deg": -11.26,
            "argument_of_perihelion_deg": 114.21,
            "mean_anomaly_at_epoch_deg": 357.53,
            "mean_daily_motion_deg": 0.98561,
        },
        "Mars": {
            "semi_major_axis_au": 1.524,
            "eccentricity": 0.093,
            "inclination_deg": 1.85,
            "longitude_ascending_node_deg": 49.56,
            "argument_of_perihelion_deg": 286.54,
            "mean_anomaly_at_epoch_deg": 19.37,
            "mean_daily_motion_deg": 0.52403,
        },
        "Jupiter": {
            "semi_major_axis_au": 5.203,
            "eccentricity": 0.048,
            "inclination_deg": 1.30,
            "longitude_ascending_node_deg": 100.46,
            "argument_of_perihelion_deg": 273.87,
            "mean_anomaly_at_epoch_deg": 20.02,
            "mean_daily_motion_deg": 0.08309,
        },
        "Saturn": {
            "semi_major_axis_au": 9.537,
            "eccentricity": 0.054,
            "inclination_deg": 2.49,
            "longitude_ascending_node_deg": 113.64,
            "argument_of_perihelion_deg": 339.49,
            "mean_anomaly_at_epoch_deg": 317.02,
            "mean_daily_motion_deg": 0.03346,
        },
        "Uranus": {
            "semi_major_axis_au": 19.19,
            "eccentricity": 0.047,
            "inclination_deg": 0.77,
            "longitude_ascending_node_deg": 74.01,
            "argument_of_perihelion_deg": 96.99,
            "mean_anomaly_at_epoch_deg": 142.24,
            "mean_daily_motion_deg": 0.01174,
        },
        "Neptune": {
            "semi_major_axis_au": 30.07,
            "eccentricity": 0.009,
            "inclination_deg": 1.77,
            "longitude_ascending_node_deg": 131.78,
            "argument_of_perihelion_deg": 273.19,
            "mean_anomaly_at_epoch_deg": 256.23,
            "mean_daily_motion_deg": 0.00600,
        },
        # Geocentric Sun: mirrors Earth's heliocentric orbit.  The
        # argument of perihelion (102.94 deg) is Earth's mean longitude of
        # perihelion, so the Sun's apparent path matches Earth's.  LEARN:
        # the Sun's "distance" is the Earth–Sun distance, ~1 AU.
        "Sun": {
            "semi_major_axis_au": 1.0,
            "eccentricity": 0.017,
            "inclination_deg": 0.00,
            "longitude_ascending_node_deg": 0.00,
            "argument_of_perihelion_deg": 102.94,
            "mean_anomaly_at_epoch_deg": 357.53,
            "mean_daily_motion_deg": 0.98561,
        },
        # Simplified Moon: mean lunar orbit, no node precession.  LEARN:
        # real lunar theory needs Omega precession (~3.2 yr-ish to a
        # full ~18.6 yr cycle) plus nutation and ΔT for arcmin accuracy.
        "Moon": {
            "semi_major_axis_au": 0.00257,
            "eccentricity": 0.055,
            "inclination_deg": 5.14,
            "longitude_ascending_node_deg": 0.00,
            "argument_of_perihelion_deg": 0.00,
            "mean_anomaly_at_epoch_deg": 0.00,
            "mean_daily_motion_deg": 13.176,
        },
    }

    # Physical and descriptive data per body (real values, rounded).
    BODY_INFO: Final[Dict[str, Dict[str, object]]] = {
        "Sun": {
            "diameter_km": 1_392_700,
            "mass_kg": 1.989e30,
            "orbital_period_days": 0.0,   # does not orbit the Sun
            "moons": 0,
            "type": "star",
        },
        "Mercury": {
            "diameter_km": 4_879,
            "mass_kg": 3.3011e23,
            "orbital_period_days": 87.97,
            "moons": 0,
            "type": "terrestrial planet",
        },
        "Venus": {
            "diameter_km": 12_104,
            "mass_kg": 4.8675e24,
            "orbital_period_days": 224.70,
            "moons": 0,
            "type": "terrestrial planet",
        },
        "Earth": {
            "diameter_km": 12_742,
            "mass_kg": 5.972e24,
            "orbital_period_days": 365.25,
            "moons": 1,
            "type": "terrestrial planet",
        },
        "Mars": {
            "diameter_km": 6_779,
            "mass_kg": 6.4171e23,
            "orbital_period_days": 686.97,
            "moons": 2,
            "type": "terrestrial planet",
        },
        "Jupiter": {
            "diameter_km": 139_820,
            "mass_kg": 1.898e27,
            "orbital_period_days": 4_332.59,
            "moons": 95,
            "type": "gas giant",
        },
        "Saturn": {
            "diameter_km": 116_460,
            "mass_kg": 5.683e26,
            "orbital_period_days": 10_759.22,
            "moons": 146,
            "type": "gas giant",
        },
        "Uranus": {
            "diameter_km": 50_724,
            "mass_kg": 8.681e25,
            "orbital_period_days": 30_688.50,
            "moons": 28,
            "type": "ice giant",
        },
        "Neptune": {
            "diameter_km": 49_244,
            "mass_kg": 1.024e26,
            "orbital_period_days": 60_182.00,
            "moons": 16,
            "type": "ice giant",
        },
        "Moon": {
            "diameter_km": 3_474,
            "mass_kg": 7.342e22,
            "orbital_period_days": 27.32,
            "moons": 0,
            "type": "natural satellite",
        },
    }

    # --- Time helpers --------------------------------------------------

    @staticmethod
    def _days_since_j2000(datetime_str: str) -> float:
        """Elapsed days from the J2000.0 epoch to ``datetime_str``.

        ``datetime_str`` is parsed as ISO-8601 (e.g.
        ``"2026-08-04T12:00:00"`` or with a trailing ``Z``).  If no
        timezone is supplied it is assumed to be UTC.  The result is the
        signed number of days since 2000-01-01 12:00 UTC, suitable for
        advancing a mean anomaly by ``M = M0 + n * d``.

        LEARN: We compute via Julian dates because the Julian date of
        J2000.0 is exactly 2451545.0, which makes the arithmetic exact
        and avoids month/year edge cases.
        """
        # Normalise a trailing 'Z' to '+00:00' for fromisoformat.
        s = datetime_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)

        # Julian date of the given UTC instant.
        # LEARN: the Meeus (1991) JD algorithm for Gregorian calendars.
        # For January and February the year/month are shifted so that the
        # 30.6001 term handles month lengths uniformly; without this the
        # JD is off by one day for Jan/Feb dates.
        year = dt.year
        month = dt.month
        if month <= 2:
            year -= 1
            month += 12
        a = year // 100
        b = 2 - a + a // 4
        # day fraction: hour/24 + minute/1440 + second/86400
        day_fraction = (
            dt.hour / 24.0
            + dt.minute / 1440.0
            + (dt.second + dt.microsecond / 1e6) / 86400.0
        )
        jd = (
            int(365.25 * (year + 4716))
            + int(30.6001 * (month + 1))
            + dt.day
            + b
            + day_fraction
            - 1524.5
        )
        return jd - JD_J2000

    # --- Kepler solver -------------------------------------------------

    @staticmethod
    def solve_kepler(
        M: float, e: float, tolerance: float = 1e-6, max_iter: int = 50
    ) -> float:
        """Solve Kepler's equation ``M = E - e sin(E)`` for the eccentric
        anomaly ``E`` (both ``M`` and ``E`` in radians) by Newton–Raphson
        iteration.

        Kepler's equation relates the *mean* anomaly M (which grows
        uniformly with time) to the *eccentric* anomaly E (which locates
        the body on its elliptical orbit):

            M = E - e * sin(E)

        It has no closed-form solution, so we iterate:

            E_{n+1} = E_n - (E_n - e sin(E_n) - M) / (1 - e cos(E_n))

        starting from ``E_0 = M`` (a good guess for small e).  Convergence
        is quadratic; for the planets e ≤ 0.21 so a handful of
        iterations reaches 1e-6.

        Parameters
        ----------
        M:
            Mean anomaly, in radians.
        e:
            Eccentricity (0 ≤ e < 1).
        tolerance:
            Stop when the absolute correction is below this value.
        max_iter:
            Safety cap on the iteration count.

        Returns
        -------
        float
            The eccentric anomaly E in radians.

        Raises
        ------
        ValueError
            If ``e`` is outside the elliptic range [0, 1).
        """
        if not 0.0 <= e < 1.0:
            raise ValueError(f"eccentricity must be in [0, 1), got {e}")

        # Normalise M to [-pi, pi] to keep the iteration well behaved.
        M = math.atan2(math.sin(M), math.cos(M))  # LEARN: preserves angle

        E = M  # initial guess
        for _ in range(max_iter):
            f = E - e * math.sin(E) - M
            fp = 1.0 - e * math.cos(E)
            dE = f / fp
            E -= dE
            if abs(dE) < tolerance:
                return E
        return E  # best effort if we hit max_iter

    # --- Core position computation -------------------------------------

    def planet_position(self, body_name: str, datetime_str: str) -> Dict[str, float | str]:
        """Return the apparent position of ``body_name`` at ``datetime_str``.

        Computes RA and Dec via the full Keplerian pipeline described in
        the module docstring: advance the mean anomaly, solve Kepler's
        equation, form perifocal coordinates, rotate to the ecliptic,
        then to the equator, and finally to RA/Dec.

        Parameters
        ----------
        body_name:
            One of the keys of :attr:`ORBITAL_ELEMENTS` (case-sensitive):
            "Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn",
            "Uranus", "Neptune", "Sun", "Moon".
        datetime_str:
            ISO-8601 UTC datetime, e.g. ``"2026-08-04T12:00:00"``.

        Returns
        -------
        dict
            ``{"ra_hours": float, "dec_degrees": float,
               "distance_au": float, "body": str}`` where ``ra_hours`` is
            in [0, 24), ``dec_degrees`` in [-90, 90], and ``distance_au``
            is the geometric distance from the frame origin (the Sun for
            planets, the Earth for the Sun and Moon).

        Raises
        ------
        KeyError
            If ``body_name`` is not a known body.
        """
        elements = self.ORBITAL_ELEMENTS[body_name]  # raises KeyError

        a = float(elements["semi_major_axis_au"])
        e = float(elements["eccentricity"])
        inc = math.radians(float(elements["inclination_deg"]))
        Omega = math.radians(float(elements["longitude_ascending_node_deg"]))
        omega = math.radians(float(elements["argument_of_perihelion_deg"]))
        M0 = math.radians(float(elements["mean_anomaly_at_epoch_deg"]))
        n = math.radians(float(elements["mean_daily_motion_deg"]))

        # 1. Advance the mean anomaly by the elapsed time.
        d = self._days_since_j2000(datetime_str)
        M = M0 + n * d
        # Normalise to [-pi, pi].
        M = math.atan2(math.sin(M), math.cos(M))

        # 2. Solve Kepler's equation for the eccentric anomaly E.
        E = self.solve_kepler(M, e)

        # 3. Perifocal (orbital-plane) rectangular coordinates.
        #    x-axis points to perihelion.
        cosE = math.cos(E)
        sinE = math.sin(E)
        xp = a * (cosE - e)
        yp = a * math.sqrt(1.0 - e * e) * sinE
        # zp = 0 by construction.

        # 4. Rotate from the perifocal frame to the ecliptic frame.
        #
        # The three standard rotations (see e.g. Meeus, *Astronomical
        # Algorithms*, eq. 33.3) are, applied in order:
        #   R3(-omega)   — argument of perihelion
        #   R1(-i)       — inclination
        #   R3(-Omega)   — longitude of ascending node
        # LEARN: the combined transform is
        #
        #   x_ecl = (cos Omega cos omega - sin Omega sin omega cos i) * xp
        #         - (cos Omega sin omega + sin Omega cos omega cos i) * yp
        #   y_ecl = (sin Omega cos omega + cos Omega sin omega cos i) * xp
        #         - (sin Omega sin omega - cos Omega cos omega cos i) * yp
        #   z_ecl = (sin i sin omega) * xp + (sin i cos omega) * yp
        cosO = math.cos(Omega)
        sinO = math.sin(Omega)
        cosw = math.cos(omega)
        sinw = math.sin(omega)
        cosi = math.cos(inc)
        sini = math.sin(inc)

        x_ecl = (
            (cosO * cosw - sinO * sinw * cosi) * xp
            - (cosO * sinw + sinO * cosw * cosi) * yp
        )
        y_ecl = (
            (sinO * cosw + cosO * sinw * cosi) * xp
            - (sinO * sinw - cosO * cosw * cosi) * yp
        )
        z_ecl = (sini * sinw) * xp + (sini * cosw) * yp

        # 5. Ecliptic → equatorial, rotating about the x-axis by the
        #    obliquity of the ecliptic.  LEARN: positive obliquity tips
        #    the north ecliptic pole toward the north equatorial pole.
        eps = math.radians(OBLIQUITY_DEG)
        cosEps = math.cos(eps)
        sinEps = math.sin(eps)
        X = x_ecl
        Y = y_ecl * cosEps - z_ecl * sinEps
        Z = y_ecl * sinEps + z_ecl * cosEps

        # 6. Equatorial rectangular → RA/Dec.
        r = math.sqrt(X * X + Y * Y + Z * Z)
        # Guard against division by zero at the origin.
        if r == 0.0:
            ra_rad = 0.0
            dec_rad = 0.0
        else:
            ra_rad = math.atan2(Y, X)  # [-pi, pi]
            dec_rad = math.asin(max(-1.0, min(1.0, Z / r)))

        # Normalise RA to [0, 2*pi) then to hours [0, 24).
        if ra_rad < 0.0:
            ra_rad += 2.0 * math.pi
        ra_hours = ra_rad * 12.0 / math.pi  # 2pi rad -> 24 h
        dec_deg = math.degrees(dec_rad)

        return {
            "ra_hours": ra_hours,
            "dec_degrees": dec_deg,
            "distance_au": r,
            "body": body_name,
        }

    # --- Batch + info --------------------------------------------------

    def all_bodies(self, datetime_str: str) -> Dict[str, Dict[str, float | str]]:
        """Positions of every tracked body at ``datetime_str``.

        Returns a dict keyed by body name, each value the same shape as
        :meth:`planet_position`.  Earth is included as a heliocentric
        position; for a geocentric observer the Sun and Moon entries are
        already in the correct (geocentric) frame.
        """
        return {name: self.planet_position(name, datetime_str) for name in self.ORBITAL_ELEMENTS}

    def body_info(self, body_name: str) -> Dict[str, object]:
        """Physical and descriptive data for ``body_name``.

        Returns a dict with keys ``diameter_km``, ``mass_kg``,
        ``orbital_period_days``, ``moons`` and ``type``.  Values are
        rounded real-world figures (moon counts as of the mid-2020s).

        Raises
        ------
        KeyError
            If ``body_name`` is not a known body.
        """
        return dict(self.BODY_INFO[body_name])  # raises KeyError


# --- Quick self-test (manual) -----------------------------------------
if __name__ == "__main__":  # pragma: no cover
    ss = SolarSystem()
    when = "2026-08-04T12:00:00"
    for name in ss.ORBITAL_ELEMENTS:
        pos = ss.planet_position(name, when)
        print(
            f"{name:8s}  RA={pos['ra_hours']:7.4f} h  "
            f"Dec={pos['dec_degrees']:+8.4f} deg  "
            f"r={pos['distance_au']:8.4f} AU"
        )