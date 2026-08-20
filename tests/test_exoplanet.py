"""Tests for the astro exoplanet transit-detection and catalog packages.

All tests are pure-stdlib, no network, no hardware. HTTP is mocked and any
heavy scientific dependency (lightkurve / numpy) is mock-injected, so the suite
runs on the droid's embedded controller without third-party packages. The
tests verify error handling and mock-injected behaviour only — they never
attempt a real network request.

Run: python -m pytest tests/test_exoplanet.py -v
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ─── Astro: Exoplanet Transit Detector ──────────────────────────────


class TestExoplanetDetector(unittest.TestCase):
    """Unit tests for :class:`astro.exoplanet.ExoplanetDetector`.

    The detector wraps an optional HTTP client (for catalog / archive lookups)
    and an optional lightkurve client (for light-curve retrieval and transit
    search). Neither dependency is installed in the test environment, so every
    client is mock-injected. All public methods are contractually required to
    return dicts and never raise.
    """

    # ---- info() --------------------------------------------------------

    def test_info_returns_dict(self):
        """``info()`` returns a dict exposing ``available`` and ``apis``."""
        from astro.exoplanet import ExoplanetDetector
        detector = ExoplanetDetector()
        info = detector.info()
        self.assertIsInstance(info, dict)
        self.assertIn("available", info)
        self.assertIn("apis", info)

    def test_info_has_transit_api(self):
        """``info()['apis']`` advertises a transit-detection capability."""
        from astro.exoplanet import ExoplanetDetector
        detector = ExoplanetDetector()
        info = detector.info()
        apis = info["apis"]
        # Accept either a list (membership) or a dict (key presence).
        if isinstance(apis, dict):
            self.assertTrue(
                any("transit" in str(k).lower() for k in apis),
                f"no transit key in apis dict: {list(apis)}",
            )
        else:
            self.assertTrue(
                any("transit" in str(a).lower() for a in apis),
                f"no transit entry in apis list: {list(apis)}",
            )

    # ---- detect_transits() ---------------------------------------------

    def test_detect_transits_error_handling(self):
        """A failing HTTP client must yield an error dict, never an exception."""
        from astro.exoplanet import ExoplanetDetector
        mock_http = MagicMock(side_effect=Exception("network error"))
        detector = ExoplanetDetector(http_client=mock_http)
        result = detector.detect_transits("Kepler-10")
        self.assertIsInstance(result, dict)
        # Must surface an error marker of some kind, never raise.
        self.assertTrue(
            "error" in result or "ok" in result and result["ok"] is False
            or "status" in result,
            f"detect_transits returned no error indicator: {result}",
        )

    def test_detect_transits_with_injected_lightcurve(self):
        """Injecting a fake lightkurve client returns a structured result.

        The fake client supplies a dict with ``time`` and ``flux`` arrays so the
        detector can run its transit search against pure-Python data without
        lightkurve/numpy being installed.
        """
        from astro.exoplanet import ExoplanetDetector

        def fake_lightkurve(target):
            """Return a minimal light-curve-like dict."""
            return {
                "target": target,
                "time": list(range(0, 200)),
                "flux": [1.0] * 200,
                "flux_err": [0.001] * 200,
            }

        mock_http = MagicMock(return_value={"pl_name": "Kepler-10 b"})
        detector = ExoplanetDetector(
            http_client=mock_http, lightkurve_client=fake_lightkurve
        )
        result = detector.detect_transits("Kepler-10")
        self.assertIsInstance(result, dict)

    # ---- search_target() ----------------------------------------------

    def test_search_target_error_handling(self):
        """A failing HTTP client must yield an error dict, never raise."""
        from astro.exoplanet import ExoplanetDetector
        mock_http = MagicMock(side_effect=Exception("timeout"))
        detector = ExoplanetDetector(http_client=mock_http)
        result = detector.search_target("Kepler-10")
        self.assertIsInstance(result, dict)
        self.assertTrue(
            "error" in result or "ok" in result and result["ok"] is False
            or "status" in result,
            f"search_target returned no error indicator: {result}",
        )

    # ---- never-raise contract -----------------------------------------

    def test_all_methods_never_raise(self):
        """With a totally failing HTTP client no public method raises."""
        from astro.exoplanet import ExoplanetDetector
        mock_http = MagicMock(side_effect=Exception("total failure"))
        detector = ExoplanetDetector(http_client=mock_http)
        # None of these should raise.
        detector.detect_transits("Kepler-10")
        detector.search_target("Kepler-10")
        detector.validate_known_planet("Kepler-10 b")


# ─── Astro: Exoplanet Catalog ────────────────────────────────────────


class TestExoplanetCatalog(unittest.TestCase):
    """Unit tests for :class:`astro.exoplanet_catalog.ExoplanetCatalog`.

    The catalog wraps the NASA Exoplanet Archive via a pluggable
    ``http_client(url: str) -> dict`` callable. All tests inject mocks so no
    network is touched. All public methods return dicts and never raise.
    """

    # ---- info() --------------------------------------------------------

    def test_info(self):
        """``info()`` returns a dict with ``available`` and ``apis``."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        catalog = ExoplanetCatalog(http_client=lambda url: {})
        info = catalog.info()
        self.assertIsInstance(info, dict)
        self.assertIn("available", info)
        self.assertIn("apis", info)

    def test_info_has_exoplanet_archive(self):
        """``info()['apis']`` advertises the exoplanet-archive backend."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        catalog = ExoplanetCatalog(http_client=lambda url: {})
        info = catalog.info()
        apis = info["apis"]
        if isinstance(apis, dict):
            self.assertIn(
                "exoplanet_archive",
                apis,
                f"exoplanet_archive missing from apis dict: {list(apis)}",
            )
        else:
            self.assertIn(
                "exoplanet_archive",
                apis,
                f"exoplanet_archive missing from apis list: {list(apis)}",
            )

    # ---- all_planets() -------------------------------------------------

    def test_all_planets_with_mock(self):
        """A mock returning a JSON list yields a structured planet result."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        planets = [
            {"pl_name": "Kepler-10 b", "hostname": "Kepler-10"},
            {"pl_name": "Kepler-10 c", "hostname": "Kepler-10"},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.all_planets()
        self.assertIsInstance(result, dict)
        self.assertIn("planets", result)
        self.assertIn("count", result)

    def test_all_planets_error_handling(self):
        """A failing HTTP client yields an error dict, never raises."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        mock_http = MagicMock(side_effect=Exception("network error"))
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.all_planets()
        self.assertIsInstance(result, dict)
        self.assertTrue(
            "error" in result or "ok" in result and result["ok"] is False
            or "status" in result,
            f"all_planets returned no error indicator: {result}",
        )

    # ---- search_by_name() ----------------------------------------------

    def test_search_by_name_found(self):
        """A matching planet returns a found result."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        planets = [
            {"pl_name": "Kepler-10 b", "hostname": "Kepler-10"},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.search_by_name("Kepler-10 b")
        self.assertIsInstance(result, dict)
        # Found path should be distinguishable from the not-found path.
        self.assertNotEqual(result.get("found"), False)

    def test_search_by_name_not_found(self):
        """An empty list yields ``{"found": False}``."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        mock_http = MagicMock(return_value=[])
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.search_by_name("Nonexistent Planet")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("found"), False)

    # ---- search_by_host() ---------------------------------------------

    def test_search_by_host(self):
        """Searching by host star returns a structured result."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        planets = [
            {"pl_name": "Kepler-10 b", "hostname": "Kepler-10"},
            {"pl_name": "Kepler-10 c", "hostname": "Kepler-10"},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.search_by_host("Kepler-10")
        self.assertIsInstance(result, dict)

    # ---- search_by_position() ------------------------------------------

    def test_search_by_position_returns_list(self):
        """Searching by position returns a list of nearby planets."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        planets = [
            {"pl_name": "Kepler-10 b", "ra": 285.0, "dec": 52.0},
            {"pl_name": "Far Planet", "ra": 10.0, "dec": -10.0},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.search_by_position(285.0, 52.0, radius_deg=5.0)
        # May be a list or a dict wrapping a list; either way it's structured.
        self.assertIsNotNone(result)

    # ---- search_by_radius() -------------------------------------------

    def test_search_by_radius(self):
        """Searching by planet radius (Earth radii) returns a structured result."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        planets = [
            {"pl_name": "Kepler-10 b", "pl_rade": 1.47},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.search_by_radius(1.0, 2.0)
        self.assertIsNotNone(result)

    # ---- search_by_period() -------------------------------------------

    def test_search_by_period(self):
        """Searching by orbital period returns a structured result."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        planets = [
            {"pl_name": "Kepler-10 b", "pl_orbper": 0.8375},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.search_by_period(min_period=0.5, max_period=1.0)
        self.assertIsNotNone(result)

    # ---- search_by_facility() -----------------------------------------

    def test_search_by_facility(self):
        """Searching by discovery facility returns a structured result."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        planets = [
            {"pl_name": "Kepler-10 b", "pl_facility": "Kepler"},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.search_by_facility("Kepler")
        self.assertIsNotNone(result)

    # ---- count() -------------------------------------------------------

    def test_count_returns_number(self):
        """``count()`` returns a count-like result (number or numeric dict)."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        planets = [
            {"pl_name": "Kepler-10 b"},
            {"pl_name": "Kepler-10 c"},
            {"pl_name": "TRAPPIST-1 e"},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.count()
        if isinstance(result, dict):
            self.assertIn("count", result)
        else:
            self.assertEqual(result, 3)

    # ---- never-raise contract -----------------------------------------

    def test_all_methods_never_raise(self):
        """With a totally failing HTTP client no public method raises."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        mock_http = MagicMock(side_effect=Exception("total failure"))
        catalog = ExoplanetCatalog(http_client=mock_http)
        # None of these should raise.
        catalog.query("select * from ps")
        catalog.all_planets()
        catalog.search_by_name("Kepler-10 b")
        catalog.search_by_host("Kepler-10")
        catalog.search_by_position(285.0, 52.0, 5.0)
        catalog.search_by_radius(1.0, 2.0)
        catalog.search_by_period(0.5, 1.0)
        catalog.search_by_facility("Kepler")
        catalog.count()

    # ---- _angular_separation() ----------------------------------------

    def test_angular_separation_zero(self):
        """Identical points are zero degrees apart."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        sep = ExoplanetCatalog._angular_separation(0.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(sep, 0.0, places=4)

    def test_angular_separation_90deg(self):
        """(0,0) to (0,90) is ~90 degrees."""
        from astro.exoplanet_catalog import ExoplanetCatalog
        sep = ExoplanetCatalog._angular_separation(0.0, 0.0, 0.0, 90.0)
        self.assertAlmostEqual(sep, 90.0, delta=0.1)


class TestExoplanetCatalogMirror(unittest.TestCase):
    """Tests for the local SQLite mirror fallback functionality."""

    def setUp(self):
        """Create a temporary directory for test mirror databases."""
        import tempfile
        self._tmpdir = tempfile.mkdtemp(prefix="r1a1_exo_mirror_")
        self._db_path = str(Path(self._tmpdir) / "test_exoplanets.db")

    def tearDown(self):
        """Clean up the temporary directory."""
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ---- download_mirror() -------------------------------------------

    def test_download_mirror_with_mock(self):
        """download_mirror() fetches from TAP and populates SQLite."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "WASP-18 b", "hostname": "WASP-18",
             "ra": 24.16, "dec": -45.69, "pl_rade": 1.20,
             "pl_orbper": 3.5246, "pl_trandep": 0.0046,
             "sy_tmag": 9.7, "st_rad": 1.23,
             "disc_facility": "SuperWASP", "disc_year": 2009,
             "pl_bmasse": 332.5, "pl_orbeccen": 0.0085,
             "pl_eqt": 2400.0},
            {"pl_name": "Kepler-10 b", "hostname": "Kepler-10",
             "ra": 285.0, "dec": 52.0, "pl_rade": 1.47,
             "pl_orbper": 0.8375, "pl_trandep": 0.0005,
             "sy_tmag": 13.0, "st_rad": 1.06,
             "disc_facility": "Kepler", "disc_year": 2011,
             "pl_bmasse": 3.7, "pl_orbeccen": 0.0,
             "pl_eqt": 700.0},
        ]
        mock_http = MagicMock(return_value=planets)
        catalog = ExoplanetCatalog(http_client=mock_http)

        result = catalog.download_mirror(self._db_path)
        self.assertNotIn("error", result, f"download failed: {result}")
        self.assertEqual(result["downloaded"], 2)
        self.assertEqual(result["db_path"], self._db_path)
        self.assertEqual(result["source"], "nasa_archive")

        # Verify the SQLite file exists
        self.assertTrue(Path(self._db_path).exists())

    def test_download_mirror_no_path_error(self):
        """download_mirror() returns error when no path is configured."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        catalog = ExoplanetCatalog(http_client=lambda url: [])
        result = catalog.download_mirror()
        self.assertIn("error", result)
        self.assertIn("no db_path", result["error"])

    def test_download_mirror_tap_error_propagates(self):
        """download_mirror() propagates TAP errors."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        mock_http = MagicMock(side_effect=Exception("network down"))
        catalog = ExoplanetCatalog(http_client=mock_http)
        result = catalog.download_mirror(self._db_path)
        self.assertIn("error", result)

    def test_download_mirror_idempotent(self):
        """Re-downloading replaces existing data, not duplicates."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets1 = [{"pl_name": "Planet A", "hostname": "Star A"}]
        planets2 = [
            {"pl_name": "Planet A", "hostname": "Star A"},
            {"pl_name": "Planet B", "hostname": "Star B"},
        ]

        # learning: The mock needs to handle both all_planets() queries
        # (which return planet lists) and count() queries (which return
        # [{"n": N}]).  We inspect the URL to differentiate.
        call_count = [0]
        def mock_http(url):
            call_count[0] += 1
            if "COUNT" in url.upper():
                # Count query — return the current call number as a proxy
                return [{"n": call_count[0]}]
            # all_planets query — cycle through the two planet lists
            return planets1 if call_count[0] == 1 else planets2

        catalog = ExoplanetCatalog(http_client=mock_http)

        catalog.download_mirror(self._db_path)
        first = catalog.mirror_info()
        self.assertEqual(first["row_count"], 1)

        catalog.download_mirror(self._db_path)
        second = catalog.mirror_info()
        self.assertEqual(second["row_count"], 2)

    # ---- mirror fallback routing -------------------------------------

    def test_search_falls_back_to_mirror(self):
        """When live TAP fails and mirror exists, search uses mirror."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        # First, populate the mirror with a working mock
        planets = [
            {"pl_name": "Kepler-10 b", "hostname": "Kepler-10",
             "ra": 285.0, "dec": 52.0, "pl_rade": 1.47,
             "pl_orbper": 0.8375},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)

        # Now make the HTTP client fail — should fall back to mirror
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.all_planets()
        self.assertNotIn("error", result, f"mirror fallback failed: {result}")
        self.assertEqual(result["source"], "local_mirror")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["planets"][0]["pl_name"], "Kepler-10 b")

    def test_search_by_name_falls_back_to_mirror(self):
        """search_by_name falls back to mirror on network failure."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Kepler-10 b", "hostname": "Kepler-10",
             "ra": 285.0, "dec": 52.0, "pl_rade": 1.47},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.search_by_name("Kepler-10 b")
        self.assertNotIn("error", result)
        self.assertEqual(result["pl_name"], "Kepler-10 b")

    def test_search_by_name_not_found_in_mirror(self):
        """search_by_name returns found=False when mirror has no match."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Kepler-10 b", "hostname": "Kepler-10"},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.search_by_name("Nonexistent Planet")
        self.assertEqual(result, {"found": False})

    def test_count_falls_back_to_mirror(self):
        """count() falls back to mirror on network failure."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Planet A", "hostname": "Star A"},
            {"pl_name": "Planet B", "hostname": "Star B"},
            {"pl_name": "Planet C", "hostname": "Star C"},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.count()
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["source"], "local_mirror")

    def test_search_by_radius_falls_back_to_mirror(self):
        """search_by_radius falls back to mirror on network failure."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Planet A", "pl_rade": 1.5},
            {"pl_name": "Planet B", "pl_rade": 2.5},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.search_by_radius(1.0, 2.0)
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["source"], "local_mirror")

    def test_search_by_period_falls_back_to_mirror(self):
        """search_by_period falls back to mirror on network failure."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Planet A", "pl_orbper": 1.5},
            {"pl_name": "Planet B", "pl_orbper": 4.0},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.search_by_period(0.5, 2.0)
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["source"], "local_mirror")

    def test_search_by_facility_falls_back_to_mirror(self):
        """search_by_facility falls back to mirror on network failure."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Planet A", "disc_facility": "Kepler"},
            {"pl_name": "Planet B", "disc_facility": "TESS"},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.search_by_facility("Kepler")
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["source"], "local_mirror")

    def test_search_by_position_falls_back_to_mirror(self):
        """search_by_position falls back to mirror on network failure."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Planet A", "ra": 285.0, "dec": 52.0},
            {"pl_name": "Planet B", "ra": 300.0, "dec": 60.0},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.search_by_position(285.0, 52.0, radius_deg=10.0)
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["source"], "local_mirror")

    def test_search_by_host_falls_back_to_mirror(self):
        """search_by_host falls back to mirror on network failure."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Planet A", "hostname": "Kepler-10"},
            {"pl_name": "Planet B", "hostname": "WASP-18"},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)
        catalog._http = MagicMock(side_effect=Exception("network down"))

        result = catalog.search_by_host("Kepler-10")
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["source"], "local_mirror")

    # ---- mirror_info() -----------------------------------------------

    def test_mirror_info_no_mirror(self):
        """mirror_info() when no mirror is configured."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        catalog = ExoplanetCatalog(http_client=lambda url: [])
        info = catalog.mirror_info()
        self.assertFalse(info["configured"])
        self.assertFalse(info["exists"])
        self.assertIsNone(info["row_count"])

    def test_mirror_info_after_download(self):
        """mirror_info() reports row count after download."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [
            {"pl_name": "Planet A", "hostname": "Star A"},
            {"pl_name": "Planet B", "hostname": "Star B"},
        ]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)

        info = catalog.mirror_info()
        self.assertTrue(info["configured"])
        self.assertTrue(info["exists"])
        self.assertEqual(info["row_count"], 2)
        self.assertIsNotNone(info["last_sync"])

    # ---- sync_mirror() -----------------------------------------------

    def test_sync_mirror_no_path_error(self):
        """sync_mirror() returns error when no path is configured."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        catalog = ExoplanetCatalog(http_client=lambda url: [])
        result = catalog.sync_mirror()
        self.assertIn("error", result)

    # ---- info() with mirror ------------------------------------------

    def test_info_includes_mirror_status(self):
        """info() includes mirror metadata when configured."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        planets = [{"pl_name": "Planet A", "hostname": "Star A"}]
        catalog = ExoplanetCatalog(http_client=MagicMock(return_value=planets))
        catalog.download_mirror(self._db_path)

        info = catalog.info()
        self.assertIn("mirror", info)
        self.assertTrue(info["mirror"]["exists"])
        self.assertEqual(info["mirror"]["row_count"], 1)

    # ---- never-raise with mirror -------------------------------------

    def test_mirror_methods_never_raise(self):
        """Mirror-related methods never raise even with broken state."""
        from astro.exoplanet_catalog import ExoplanetCatalog

        catalog = ExoplanetCatalog(
            http_client=MagicMock(side_effect=Exception("fail")),
            db_path="/nonexistent/path/mirror.db",
        )
        # None of these should raise
        catalog.mirror_info()
        catalog.sync_mirror()
        catalog.download_mirror("/another/nonexistent/path.db")


if __name__ == "__main__":
    unittest.main()