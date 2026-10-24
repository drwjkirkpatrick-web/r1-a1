"""Regression tests for the R1-A1 code-review astro findings.

Covers three findings from ``docs/CODE_REVIEW.md``:

* **F9** — ``SolarSystem.planet_position("Sun")`` returned Earth's
  heliocentric position (the exact antipode of the geocentric Sun)
  because the geocentric 180° flip was missing.
* **F11 / F12** — ``StarCatalog``: Mira's RA was stored as 34.83
  *hours* (it is 34.83 *degrees* ≈ 2.32 h, outside the documented
  0–24 h range); the catalog held 58 stars while the docs claim 60;
  and the "ordered by descending brightness" claim was false.
* **F10** — ``ExoplanetDetector.validate_known_planet`` imported
  ``ExoplanetCatalog`` from ``astro.star_catalog`` (where it does not
  exist), making the catalog path dead code that always fell back to
  a direct TAP query.

All tests are pure-stdlib and run offline; HTTP is stubbed or
monkeypatched, never real.

Run: python -m pytest tests/test_fix_astro.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ─── F9: SolarSystem geocentric Sun ─────────────────────────────────


class TestSunGeocentricPosition(unittest.TestCase):
    """The Sun's computed position must be geocentric, not heliocentric."""

    J2000 = "2000-01-01T12:00:00Z"

    def setUp(self) -> None:
        from astro.solar_system import SolarSystem

        self.ss = SolarSystem()

    def test_sun_ra_dec_at_j2000_matches_ephemeris(self) -> None:
        """At J2000.0 the true geocentric Sun is RA ≈ 18.75 h, Dec ≈ −23°."""
        sun = self.ss.planet_position("Sun", self.J2000)
        # learning: the JPL ephemeris puts the Sun at RA ~18h45m,
        # Dec ~-23°02' at J2000.0.  A mean-element model is good to a
        # fraction of a degree, so a generous ±0.5 h / ±1° window is used.
        self.assertGreater(sun["ra_hours"], 18.25)
        self.assertLess(sun["ra_hours"], 19.25)
        self.assertGreater(sun["dec_degrees"], -24.0)
        self.assertLess(sun["dec_degrees"], -22.0)

    def test_sun_is_antipodal_to_earth(self) -> None:
        """Earth's heliocentric position must be antipodal to the
        Sun's geocentric position: 12 h away in RA, opposite in Dec,
        at the same distance."""
        sun = self.ss.planet_position("Sun", self.J2000)
        earth = self.ss.planet_position("Earth", self.J2000)

        ra_sep = abs(sun["ra_hours"] - earth["ra_hours"])
        ra_sep = min(ra_sep, 24.0 - ra_sep)  # wrap-around separation
        self.assertAlmostEqual(ra_sep, 12.0, delta=0.1)
        self.assertAlmostEqual(
            sun["dec_degrees"], -earth["dec_degrees"], delta=0.1
        )
        self.assertAlmostEqual(
            sun["distance_au"], earth["distance_au"], places=9
        )

    def test_sun_is_not_earth_position(self) -> None:
        """Regression: the bug returned identical Sun and Earth positions."""
        sun = self.ss.planet_position("Sun", self.J2000)
        earth = self.ss.planet_position("Earth", self.J2000)
        self.assertNotAlmostEqual(sun["ra_hours"], earth["ra_hours"], places=3)

    def test_planets_unaffected_by_sun_flip(self) -> None:
        """The flip must apply only to the Sun; planets stay heliocentric."""
        for body in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
            pos = self.ss.planet_position(body, self.J2000)
            self.assertGreaterEqual(pos["ra_hours"], 0.0)
            self.assertLess(pos["ra_hours"], 24.0)
            self.assertGreaterEqual(pos["dec_degrees"], -90.0)
            self.assertLessEqual(pos["dec_degrees"], 90.0)


# ─── F11 / F12: StarCatalog data integrity ──────────────────────────


class TestStarCatalogData(unittest.TestCase):
    """Catalog coordinates must be in range and the count must match docs."""

    def setUp(self) -> None:
        from astro.star_catalog import StarCatalog

        self.cat = StarCatalog()

    def test_count_is_60_as_documented(self) -> None:
        """The module docstring and count() doctest both promise 60 stars."""
        self.assertEqual(self.cat.count(), 60)

    def test_all_ra_in_valid_hour_range(self) -> None:
        """Every RA must be in [0, 24) hours — Mira's 34.83 h violated this."""
        for star in self.cat.all_stars():
            self.assertGreaterEqual(
                star["ra_hours"], 0.0, f"{star['name']} RA below 0 h"
            )
            self.assertLess(
                star["ra_hours"], 24.0, f"{star['name']} RA >= 24 h"
            )
            self.assertGreaterEqual(star["dec_degrees"], -90.0)
            self.assertLessEqual(star["dec_degrees"], 90.0)

    def test_star_names_unique(self) -> None:
        names = [s["name"].lower() for s in self.cat.all_stars()]
        self.assertEqual(len(names), len(set(names)))

    def test_mira_ra_is_in_hours(self) -> None:
        """Mira's J2000 RA is 34.83° ≈ 2.32 h, Dec ≈ −3°."""
        mira = self.cat.find_by_name("mira")
        self.assertIsNotNone(mira)
        self.assertAlmostEqual(mira["ra_hours"], 2.32, places=2)
        self.assertAlmostEqual(mira["dec_degrees"], -3.00, places=2)

    def test_mira_found_by_position_search(self) -> None:
        """Position searches near Mira's true location must match it —
        with RA stored as 34.83 h they silently never did."""
        hits = self.cat.find_by_position(2.32, -3.0, radius_deg=2.0)
        self.assertTrue(any(h["name"] == "Mira" for h in hits))

    def test_added_navigation_stars_present(self) -> None:
        """The two stars added to reach the documented 60: Mimosa, Adhara."""
        self.assertIsNotNone(self.cat.find_by_name("Mimosa"))
        self.assertIsNotNone(self.cat.find_by_name("Adhara"))
        crux = {s["name"] for s in self.cat.by_constellation("Crux")}
        self.assertIn("Mimosa", crux)
        self.assertIn("Acrux", crux)

    def test_brightest_sorts_despite_unordered_list(self) -> None:
        """brightest() must sort by magnitude; the three brightest stars
        in the sky are Sirius (-1.46), Canopus (-0.74), and
        Rigil Kentaurus (-0.27) — the last sits near the end of the
        stored list, so only a real sort finds it."""
        top3 = self.cat.brightest(3)
        self.assertEqual(
            [s["name"] for s in top3],
            ["Sirius", "Canopus", "Rigil Kentaurus"],
        )
        mags = [s["magnitude"] for s in self.cat.brightest(60)]
        self.assertEqual(mags, sorted(mags))


# ─── F10: ExoplanetCatalog import path ──────────────────────────────


class TestExoplanetCatalogImport(unittest.TestCase):
    """The catalog class must live in astro.exoplanet_catalog, and the
    detector's catalog path must actually reach it."""

    def test_catalog_importable_from_correct_module(self) -> None:
        from astro.exoplanet_catalog import ExoplanetCatalog

        self.assertTrue(callable(ExoplanetCatalog))

    def test_catalog_not_in_star_catalog(self) -> None:
        """Guard against regressing to the old wrong import location."""
        import astro.star_catalog

        self.assertFalse(hasattr(astro.star_catalog, "ExoplanetCatalog"))

    def test_catalog_instantiates_and_info_works_offline(self) -> None:
        """Smoke test: the real catalog object builds and info() returns
        capability metadata without any network access."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        catalog = ExoplanetCatalog(http_client=lambda url: [{"n": 5500}])
        info = catalog.info()
        self.assertIsInstance(info, dict)
        self.assertTrue(info["available"])
        self.assertEqual(info["apis"], ["exoplanet_archive"])
        self.assertEqual(info["total_known"], 5500)

    def test_validate_known_planet_reaches_the_catalog(self) -> None:
        """Regression: validate_known_planet used to import the catalog
        from astro.star_catalog, raising ImportError every call and
        silently falling back to the direct TAP path.  It must now use
        the real ExoplanetCatalog from astro.exoplanet_catalog."""
        import astro.exoplanet_catalog
        from astro.exoplanet import ExoplanetDetector

        calls: list[str] = []

        class StubCatalog:
            def search_by_name(self, planet_name: str) -> dict:
                calls.append(planet_name)
                return {"pl_name": planet_name, "pl_orbper": 3.7}

        original = astro.exoplanet_catalog.ExoplanetCatalog
        astro.exoplanet_catalog.ExoplanetCatalog = StubCatalog  # type: ignore[assignment]
        try:
            detector = ExoplanetDetector()
            result = detector.validate_known_planet("Kepler-186 b")
        finally:
            astro.exoplanet_catalog.ExoplanetCatalog = original  # type: ignore[assignment]

        self.assertEqual(calls, ["Kepler-186 b"])
        self.assertTrue(result["found"])
        self.assertEqual(result["known_params"]["pl_name"], "Kepler-186 b")
        self.assertIn("ExoplanetCatalog", result["source"])

    def test_validate_known_planet_offline_never_raises(self) -> None:
        """With no injected HTTP client the catalog query fails safely
        and validate_known_planet returns a dict instead of raising."""
        from astro.exoplanet import ExoplanetDetector

        class OfflineCatalog:
            def search_by_name(self, planet_name: str) -> dict:
                return {
                    "error": "no network",
                    "type": "ConnectionError",
                    "api": "exoplanet_archive",
                }

        import astro.exoplanet_catalog

        original = astro.exoplanet_catalog.ExoplanetCatalog
        astro.exoplanet_catalog.ExoplanetCatalog = OfflineCatalog  # type: ignore[assignment]
        try:
            result = ExoplanetDetector().validate_known_planet("WASP-18 b")
        finally:
            astro.exoplanet_catalog.ExoplanetCatalog = original  # type: ignore[assignment]

        self.assertIsInstance(result, dict)
        self.assertFalse(result["found"])
        self.assertIn("error", result)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
