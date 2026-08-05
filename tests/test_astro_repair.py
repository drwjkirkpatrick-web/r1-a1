"""Tests for the astro navigation and spacecraft repair packages.

All tests are pure-stdlib, no network, no hardware. HTTP is mocked
for the AstroBridge tests.

Run: python -m pytest tests/test_astro_repair.py -v
"""

import sys
import math
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ─── Astro: Navigation ──────────────────────────────────────────


class TestNavigation(unittest.TestCase):

    def setUp(self):
        from astro.navigation import Navigation
        self.nav = Navigation(latitude=45.0, longitude=-120.0)

    def test_init_defaults(self):
        from astro.navigation import Navigation
        nav = Navigation()
        self.assertEqual(nav.latitude, 0.0)
        self.assertEqual(nav.longitude, 0.0)

    def test_set_location(self):
        self.nav.set_location(35.0, -100.0)
        self.assertEqual(self.nav.latitude, 35.0)
        self.assertEqual(self.nav.longitude, -100.0)

    def test_constellations_returns_dict(self):
        stars = self.nav.constellations()
        self.assertIsInstance(stars, dict)
        self.assertGreaterEqual(len(stars), 12)
        for name, coords in stars.items():
            self.assertIn("ra", coords)
            self.assertIn("dec", coords)

    def test_constellations_has_polaris(self):
        stars = self.nav.constellations()
        self.assertIn("Polaris", stars)
        self.assertAlmostEqual(stars["Polaris"]["dec"], 89.26, places=1)

    def test_altaz_to_radec_returns_dict(self):
        result = self.nav.altaz_to_radec(45.0, 180.0, "2026-08-04T12:00:00")
        self.assertIn("ra_hours", result)
        self.assertIn("dec_degrees", result)
        self.assertIsInstance(result["ra_hours"], float)
        self.assertIsInstance(result["dec_degrees"], float)

    def test_radec_to_altaz_returns_dict(self):
        result = self.nav.radec_to_altaz(12.0, 45.0, "2026-08-04T12:00:00")
        self.assertIn("alt_degrees", result)
        self.assertIn("az_degrees", result)

    def test_roundtrip_altaz_radec(self):
        """Converting altaz -> radec -> altaz should return approximately
        the original coordinates (within ~1 degree tolerance)."""
        orig_alt, orig_az = 45.0, 180.0
        dt = "2026-08-04T12:00:00"
        radec = self.nav.altaz_to_radec(orig_alt, orig_az, dt)
        back = self.nav.radec_to_altaz(radec["ra_hours"], radec["dec_degrees"], dt)
        self.assertAlmostEqual(back["alt_degrees"], orig_alt, delta=1.0)
        # Azimuth may wrap, so check absolute angular distance
        az_diff = abs(back["az_degrees"] - orig_az)
        az_diff = min(az_diff, 360 - az_diff)
        self.assertLess(az_diff, 2.0)

    def test_angular_separation_zero(self):
        sep = self.nav.angular_separation(10.0, 20.0, 10.0, 20.0)
        self.assertAlmostEqual(sep, 0.0, places=4)

    def test_angular_separation_known(self):
        """Angular separation between (0,0) and (0,90) should be 90 deg."""
        sep = self.nav.angular_separation(0.0, 0.0, 0.0, 90.0)
        self.assertAlmostEqual(sep, 90.0, delta=0.1)

    def test_angular_separation_symmetric(self):
        sep1 = self.nav.angular_separation(5.0, 10.0, 15.0, 20.0)
        sep2 = self.nav.angular_separation(15.0, 20.0, 5.0, 10.0)
        self.assertAlmostEqual(sep1, sep2, places=4)

    def test_identify_star_returns_str(self):
        # Point near Polaris (alt ~89, az ~0 from lat 45)
        star = self.nav.identify_star(89.0, 0.0, "2026-08-04T12:00:00")
        self.assertIsInstance(star, str)


# ─── Astro: Solar System ────────────────────────────────────────


class TestSolarSystem(unittest.TestCase):

    def setUp(self):
        from astro.solar_system import SolarSystem
        self.ss = SolarSystem()

    def test_has_mercury(self):
        pos = self.ss.planet_position("Mercury", "2026-08-04T12:00:00")
        self.assertEqual(pos["body"], "Mercury")
        self.assertIn("ra_hours", pos)
        self.assertIn("dec_degrees", pos)
        self.assertIn("distance_au", pos)

    def test_has_earth(self):
        pos = self.ss.planet_position("Earth", "2026-08-04T12:00:00")
        self.assertEqual(pos["body"], "Earth")
        self.assertIsInstance(pos["ra_hours"], float)

    def test_has_jupiter(self):
        pos = self.ss.planet_position("Jupiter", "2026-08-04T12:00:00")
        self.assertEqual(pos["body"], "Jupiter")

    def test_has_neptune(self):
        pos = self.ss.planet_position("Neptune", "2026-08-04T12:00:00")
        self.assertEqual(pos["body"], "Neptune")

    def test_all_bodies(self):
        bodies = self.ss.all_bodies("2026-08-04T12:00:00")
        self.assertIsInstance(bodies, dict)
        self.assertGreaterEqual(len(bodies), 8)
        self.assertIn("Mercury", bodies)
        self.assertIn("Mars", bodies)

    def test_body_info(self):
        info = self.ss.body_info("Earth")
        self.assertIn("diameter_km", info)
        self.assertIn("mass_kg", info)
        self.assertIn("moons", info)
        self.assertIn("type", info)

    def test_body_info_jupiter(self):
        info = self.ss.body_info("Jupiter")
        self.assertIn("gas", info["type"].lower())
        self.assertGreater(info["moons"], 0)

    def test_solve_kepler_circular(self):
        """For a circular orbit (e=0), E should equal M."""
        from astro.solar_system import SolarSystem
        E = SolarSystem.solve_kepler(0.5, 0.0)
        self.assertAlmostEqual(E, 0.5, places=4)

    def test_solve_kepler_elliptical(self):
        """For e>0, E should be between M and pi for M in (0, pi)."""
        from astro.solar_system import SolarSystem
        M = 1.0  # radian
        e = 0.2
        E = SolarSystem.solve_kepler(M, e)
        # E should satisfy M = E - e*sin(E)
        self.assertAlmostEqual(E - e * math.sin(E), M, places=4)

    def test_unknown_body_raises_or_returns(self):
        """Unknown body should not crash — it should raise KeyError or
        return an error dict. Either is acceptable."""
        try:
            result = self.ss.planet_position("Pluto", "2026-08-04T12:00:00")
            # If it returns rather than raising, it should have an error key
            self.assertIn("error", result)
        except (KeyError, ValueError):
            pass  # acceptable


# ─── Astro: Star Catalog ────────────────────────────────────────


class TestStarCatalog(unittest.TestCase):

    def setUp(self):
        from astro.star_catalog import StarCatalog
        self.cat = StarCatalog()

    def test_count_at_least_50(self):
        self.assertGreaterEqual(self.cat.count(), 50)

    def test_brightest(self):
        bright = self.cat.brightest(5)
        self.assertEqual(len(bright), 5)
        # Should be sorted by magnitude (ascending = brightest first)
        for i in range(len(bright) - 1):
            self.assertLessEqual(bright[i]["magnitude"], bright[i + 1]["magnitude"])

    def test_brightest_has_sirius(self):
        bright = self.cat.brightest(1)
        self.assertEqual(bright[0]["name"], "Sirius")

    def test_find_by_name(self):
        star = self.cat.find_by_name("Sirius")
        self.assertIsNotNone(star)
        self.assertEqual(star["name"], "Sirius")

    def test_find_by_name_case_insensitive(self):
        star = self.cat.find_by_name("SIRIUS")
        self.assertIsNotNone(star)

    def test_find_by_name_not_found(self):
        star = self.cat.find_by_name("Nonexistent Star")
        self.assertIsNone(star)

    def test_find_by_position(self):
        # Search near Sirius (ra=6.75, dec=-16.72)
        results = self.cat.find_by_position(6.75, -16.72, radius_deg=5.0)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        # Sirius should be first (closest)
        self.assertEqual(results[0]["name"], "Sirius")

    def test_by_constellation(self):
        stars = self.cat.by_constellation("Orion")
        self.assertIsInstance(stars, list)
        self.assertGreater(len(stars), 0)
        for s in stars:
            self.assertEqual(s["constellation"], "Orion")

    def test_by_spectral_type(self):
        stars = self.cat.by_spectral_type("A")
        self.assertIsInstance(stars, list)
        self.assertGreater(len(stars), 0)
        for s in stars:
            self.assertTrue(s["spectral_type"].startswith("A"))

    def test_all_stars(self):
        all_stars = self.cat.all_stars()
        self.assertEqual(len(all_stars), self.cat.count())


# ─── Astro: Milky Way ────────────────────────────────────────────


class TestMilkyWay(unittest.TestCase):

    def setUp(self):
        from astro.milky_way import MilkyWay
        self.mw = MilkyWay()

    def test_info_has_diameter(self):
        info = self.mw.info()
        # The MilkyWay subagent nests structure under 'structure' key
        struct = info.get("structure", info)
        self.assertIn("diameter_ly", struct)
        self.assertGreater(struct["diameter_ly"], 0)

    def test_info_has_black_hole(self):
        info = self.mw.info()
        struct = info.get("structure", info)
        self.assertIn("central_black_hole", struct)
        self.assertIn("Sagittarius", struct["central_black_hole"])

    def test_galactic_arms(self):
        arms = self.mw.galactic_arms()
        self.assertIsInstance(arms, list)
        self.assertGreaterEqual(len(arms), 4)
        for arm in arms:
            self.assertIn("name", arm)
            self.assertIn("distance_from_center_ly", arm)

    def test_notable_regions(self):
        regions = self.mw.notable_regions()
        self.assertIsInstance(regions, list)
        self.assertGreaterEqual(len(regions), 3)

    def test_notable_objects(self):
        objects = self.mw.notable_objects()
        self.assertIsInstance(objects, list)
        self.assertGreaterEqual(len(objects), 10)
        for obj in objects:
            self.assertIn("name", obj)
            self.assertIn("type", obj)
            self.assertIn("ra_degrees", obj)
            self.assertIn("dec_degrees", obj)
            self.assertIn("distance_ly", obj)

    def test_galactic_to_equatorial(self):
        result = self.mw.galactic_to_equatorial(0.0, 0.0)
        self.assertIn("ra_degrees", result)
        self.assertIn("dec_degrees", result)

    def test_summary_returns_str(self):
        s = self.mw.summary()
        self.assertIsInstance(s, str)
        self.assertGreater(len(s), 50)


# ─── Astro: Bridge ───────────────────────────────────────────────


class TestAstroBridge(unittest.TestCase):

    def test_info(self):
        from astro.bridge import AstroBridge
        bridge = AstroBridge(http_client=lambda url, **kw: {})
        info = bridge.info()
        self.assertIn("available", info)
        self.assertIn("apis", info)
        self.assertIn("horizons", info["apis"])

    def test_horizons_query_with_mock(self):
        from astro.bridge import AstroBridge
        mock_http = MagicMock(return_value={"result": "ok", "ephemeris": "data"})
        bridge = AstroBridge(http_client=mock_http)
        result = bridge.horizons_query("Mars", "2026-08-04T12:00:00")
        self.assertIn("result", result)

    def test_horizons_query_error_handling(self):
        from astro.bridge import AstroBridge
        mock_http = MagicMock(side_effect=Exception("network error"))
        bridge = AstroBridge(http_client=mock_http)
        result = bridge.horizons_query("Mars")
        self.assertIn("error", result)

    def test_simbad_query_error_handling(self):
        from astro.bridge import AstroBridge
        mock_http = MagicMock(side_effect=Exception("timeout"))
        bridge = AstroBridge(http_client=mock_http)
        result = bridge.simbad_query("M31")
        self.assertIn("error", result)

    def test_all_methods_never_raise(self):
        from astro.bridge import AstroBridge
        mock_http = MagicMock(side_effect=Exception("total failure"))
        bridge = AstroBridge(http_client=mock_http)
        # None of these should raise
        bridge.horizons_query("Mars")
        bridge.simbad_query("M31")
        bridge.simbad_coordinate_query(10.0, 20.0)
        bridge.skyview_query(10.0, 20.0)
        bridge.mars_weather()


# ─── Repair: Registry ─────────────────────────────────────────────


class TestSpacecraftRegistry(unittest.TestCase):

    def setUp(self):
        from repair.registry import SpacecraftRegistry, _build_catalog
        # Use the built-in catalog (has Crew Dragon, Soyuz MS, Space Shuttle)
        self.registry = _build_catalog()

    def test_list_spacecraft(self):
        ships = self.registry.list_spacecraft()
        self.assertIsInstance(ships, list)
        self.assertGreater(len(ships), 0)

    def test_get_known_ship(self):
        ship = self.registry.get("Crew Dragon")
        self.assertIsNotNone(ship)
        self.assertEqual(ship.name, "Crew Dragon")
        self.assertGreater(len(ship.subsystems), 0)

    def test_get_unknown_ship(self):
        ship = self.registry.get("Nonexistent")
        self.assertIsNone(ship)

    def test_all_spacecraft(self):
        all_ships = self.registry.all_spacecraft()
        self.assertGreater(len(all_ships), 0)

    def test_search_by_category(self):
        # Search for propulsion subsystems
        results = self.registry.search_by_category("propulsion")
        self.assertIsInstance(results, list)

    def test_register_custom_ship(self):
        from repair.registry import SpacecraftType, Subsystem, _build_catalog
        registry = _build_catalog()
        ship = SpacecraftType(
            name="TestShip",
            manufacturer="TestCo",
            classification="test",
            length_m=10.0,
            crew_capacity=2,
            subsystems=[
                Subsystem(name="Test Engine", category="propulsion"),
            ]
        )
        registry.register(ship)
        self.assertIsNotNone(registry.get("TestShip"))

    def test_subsystem_has_failure_modes(self):
        ship = self.registry.get("Space Shuttle")
        # At least one subsystem should have failure modes defined
        has_modes = any(
            sub.failure_modes for sub in ship.subsystems
        )
        self.assertTrue(has_modes)

    def test_subsystem_has_repair_steps(self):
        ship = self.registry.get("Space Shuttle")
        has_steps = any(
            sub.repair_steps for sub in ship.subsystems
        )
        self.assertTrue(has_steps)


# ─── Repair: Diagnostics ─────────────────────────────────────────


class TestDiagnostics(unittest.TestCase):

    def setUp(self):
        from repair.registry import _build_catalog
        from repair.diagnostics import DiagnosticEngine
        self.registry = _build_catalog()
        self.engine = DiagnosticEngine(self.registry)

    def test_diagnose_returns_dict(self):
        result = self.engine.diagnose("Crew Dragon", "Draco thrusters")
        self.assertIsInstance(result, dict)
        self.assertIn("status", result)

    def test_diagnose_unknown_ship(self):
        result = self.engine.diagnose("Nonexistent", "Engine")
        self.assertIn("unknown", result.get("status", "").lower())

    def test_run_all_checks(self):
        result = self.engine.run_all_checks("Crew Dragon")
        self.assertIsInstance(result, dict)
        self.assertIn("subsystems", result)

    def test_report_returns_str(self):
        report = self.engine.report("Crew Dragon")
        self.assertIsInstance(report, str)
        self.assertGreater(len(report), 20)

    def test_report_unknown_ship(self):
        report = self.engine.report("Nonexistent")
        self.assertIsInstance(report, str)
        self.assertIn("not found", report.lower())


# ─── Repair: RepairProcedure ────────────────────────────────────


class TestRepairProcedure(unittest.TestCase):

    def test_repair_procedure_init(self):
        from repair.diagnostics import RepairProcedure
        proc = RepairProcedure(
            spacecraft_name="Crew Dragon",
            subsystem_name="Draco thrusters",
            steps=["Step 1", "Step 2"],
            tools_required=["torque wrench", "borescope"],
            estimated_time_min=30,
            difficulty="moderate",
        )
        self.assertEqual(proc.spacecraft_name, "Crew Dragon")
        self.assertEqual(len(proc.steps), 2)

    def test_repair_procedure_execute(self):
        from repair.diagnostics import RepairProcedure
        proc = RepairProcedure(
            spacecraft_name="Crew Dragon",
            subsystem_name="Draco thrusters",
            steps=["Check propellant", "Replace valve seals"],
            tools_required=["torque wrench"],
            estimated_time_min=45,
            difficulty="hard",
        )
        result = proc.execute()
        self.assertIsInstance(result, dict)
        self.assertIn("spacecraft", result)
        self.assertIn("steps_total", result)

    def test_from_subsystem(self):
        from repair.registry import _build_catalog
        from repair.diagnostics import RepairProcedure
        registry = _build_catalog()
        ship = registry.get("Space Shuttle")
        self.assertIsNotNone(ship)
        # Find a subsystem with repair steps
        sub = None
        for s in ship.subsystems:
            if s.repair_steps:
                sub = s
                break
        if sub:
            proc = RepairProcedure.from_subsystem(ship, sub)
            self.assertIsNotNone(proc)
            self.assertEqual(proc.spacecraft_name, "Space Shuttle")


if __name__ == "__main__":
    unittest.main()