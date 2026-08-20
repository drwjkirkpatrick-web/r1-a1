"""Live exoplanet catalog for the R1-A1 astromech robot.

Provides up-to-date access to the NASA Exoplanet Archive via its TAP
(Table Access Protocol) API, giving the R1-A1 droid a real-time view of
all confirmed exoplanets known to humanity.

Design principles
-----------------
- **HTTPS only** — the archive endpoint uses TLS.
- **Never raise** — all public methods catch exceptions and return an
  error dict ``{"error": ..., "type": ..., "api": ...}`` so the catalog
  can be used safely from robotic control loops where an unhandled
  exception would be dangerous.
- **Lazy dependencies** — the optional ``requests`` package is imported
  inside :meth:`ExoplanetCatalog._default_http` so the module loads and
  operates with an injected client even when ``requests`` is absent.
- **Injectable transport** — an alternative HTTP callable can be passed
  to :meth:`ExoplanetCatalog.__init__` for unit testing without network.

About TAP / ADQL
----------------
The Table Access Protocol (TAP) is an IVOA standard for querying
astronomical databases using ADQL (Astronomical Data Query Language),
which is essentially SQL with extensions for spherical geometry. The
NASA Exoplanet Archive exposes a synchronous TAP endpoint at
``https://exoplanetarchive.ipac.caltech.edu/TAP/sync``.

The archive's **Planetary Systems** table (``ps``) contains one row per
planet per literature reference.  The ``default_flag=1`` column filters
to the archive's preferred solution for each planet, giving exactly one
row per confirmed exoplanet.

Key columns in the ``ps`` table
------------------------------
- ``pl_name`` — planet name (e.g. "Kepler-186 b")
- ``hostname`` — host star name
- ``ra``, ``dec`` — sky position in degrees (J2000)
- ``pl_rade`` — planet radius in Earth radii
- ``pl_orbper`` — orbital period in days
- ``pl_trandep`` — transit depth (fraction)
- ``sy_tmag`` — TESS magnitude of host star
- ``st_rad`` — stellar radius in solar radii
- ``disc_facility`` — discovery facility (e.g. "Kepler", "TESS")
- ``disc_year`` — discovery year
- ``pl_bmasse`` — planet mass in Earth masses
- ``pl_orbeccen`` — orbital eccentricity
- ``pl_eqt`` — equilibrium temperature in Kelvin

Learning annotations
--------------------
Inline ``# learning:`` comments call out the non-obvious astronomy,
TAP/ADQL, and engineering choices so a maintainer (human or droid) can
learn the *why*, not just the *what*.

References
----------
- NASA Exoplanet Archive: https://exoplanetarchive.ipac.caltech.edu/
- IVOA TAP standard: https://www.ivoa.net/documents/TAP/
- ADQL specification: https://www.ivoa.net/documents/ADQL/
"""

from __future__ import annotations

import math
import os
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable


class ExoplanetCatalog:
    """Live, fail-safe access to the NASA Exoplanet Archive via TAP.

    The catalog wraps the archive's synchronous TAP endpoint behind a
    consistent, never-raising interface.  Each method builds an ADQL
    query, delegates the HTTP GET to an injectable callable, and returns
    the parsed JSON as a dict.  When anything goes wrong — network error,
    non-200 status, JSON parse failure, or missing dependency — the
    method catches the exception and returns a structured error dict
    instead of raising.

    Parameters
    ----------
    http_client : callable, optional
        A callable with signature ``client(url: str) -> dict`` that
        performs the HTTP request and returns the parsed JSON body.
        When *None* (the default) the catalog uses
        :meth:`_default_http`, which lazily imports :mod:`requests`.
        Injecting a stub callable makes the catalog fully testable in
        isolation — no network, no ``requests`` needed.

    Attributes
    ----------
    _http : callable
        The active HTTP transport (injected or default).

    Examples
    --------
    >>> cat = ExoplanetCatalog()
    >>> cat.info()["apis"]
    ['exoplanet_archive']

    >>> # inject a fake client for testing
    >>> fake = lambda url: {"url": url}
    >>> test_cat = ExoplanetCatalog(http_client=fake)
    >>> test_cat.info()["available"]
    True
    """

    # ------------------------------------------------------------------
    #  Endpoint constants — all HTTPS
    # ------------------------------------------------------------------

    #: NASA Exoplanet Archive synchronous TAP endpoint.
    #: learning: TAP "sync" returns the result inline in the HTTP response;
    #: the alternative "async" endpoint queues a job and requires polling.
    #: For a droid making real-time queries, sync is simpler and sufficient.
    _TAP_URL: str = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

    _APIS: list[str] = ["exoplanet_archive"]

    #: Columns mirrored from the ``ps`` table — kept in sync with every
    #: SELECT clause in the query methods below.
    _COLUMNS: list[str] = [
        "pl_name", "hostname", "ra", "dec", "pl_rade",
        "pl_orbper", "pl_trandep", "sy_tmag", "st_rad",
        "disc_facility", "disc_year", "pl_bmasse",
        "pl_orbeccen", "pl_eqt",
    ]

    #: SQLite schema for the local mirror.  All numeric columns are stored
    #: as REAL (double-precision); text columns as TEXT.  ``pl_name`` is
    #: the primary key because ``default_flag=1`` guarantees one row per
    #: planet, making it a natural unique identifier.
    #: learning: SQLite is ideal for an embedded droid because it needs
    #: no server process, ships with Python's stdlib, and a 5,000-row
    #: table occupies < 1 MB on disk.
    _MIRROR_SCHEMA: str = """\
CREATE TABLE IF NOT EXISTS exoplanets (
    pl_name      TEXT PRIMARY KEY,
    hostname     TEXT,
    ra           REAL,
    dec          REAL,
    pl_rade      REAL,
    pl_orbper    REAL,
    pl_trandep   REAL,
    sy_tmag      REAL,
    st_rad       REAL,
    disc_facility TEXT,
    disc_year    INTEGER,
    pl_bmasse    REAL,
    pl_orbeccen  REAL,
    pl_eqt       REAL
);
"""
    #: Metadata table for sync state — last download timestamp and row count.
    _MIRROR_META_SCHEMA: str = """\
CREATE TABLE IF NOT EXISTS mirror_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

    # ------------------------------------------------------------------
    #  Construction & transport
    # ------------------------------------------------------------------

    def __init__(
        self,
        http_client: Callable[[str], dict[str, Any]] | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        """Initialise the catalog with optional HTTP client and local mirror.

        Parameters
        ----------
        http_client : callable or None
            A callable ``(url: str) -> dict`` used for every HTTP request.
            Pass *None* to use the built-in :meth:`_default_http` (which
            lazily imports :mod:`requests`).
        db_path : str, Path, or None
            Filesystem path to a local SQLite mirror of the exoplanet
            archive.  When provided, all search methods automatically fall
            back to the mirror when the live TAP endpoint is unreachable.
            Pass *None* (the default) for live-only operation with no
            local mirror.  The mirror is created/populated by
            :meth:`download_mirror` or :meth:`sync_mirror`.

        Attributes
        ----------
        _http : callable
            The active HTTP transport (injected or default).
        _db_path : Path or None
            Path to the local SQLite mirror, if configured.
        """
        self._http: Callable[[str], dict[str, Any]] = (
            http_client if http_client is not None else self._default_http
        )
        self._db_path: Path | None = (
            Path(db_path) if db_path is not None else None
        )

    @staticmethod
    def _default_http(url: str, timeout: int = 30) -> dict[str, Any]:
        """Default HTTP GET transport backed by :mod:`requests`.

        ``requests`` is imported *lazily* (inside this method) so that the
        module can be imported and used with an injected client even when
        the ``requests`` package is not installed.

        A ``User-Agent`` header is set because some NASA archive endpoints
        reject requests with a default/empty User-Agent.

        Parameters
        ----------
        url : str
            Fully-qualified HTTPS URL to fetch.
        timeout : int, default 30
            Request timeout in seconds.

        Returns
        -------
        dict
            Parsed JSON response body.

        Raises
        ------
        Exception
            Any network, HTTP-status, or JSON-parsing error is
            *deliberately allowed to propagate* here; the public query
            methods that call this catch it and return an error dict.
        """
        import requests  # lazy import — requests is optional

        # learning: Some NASA archive endpoints return 403 if the
        # User-Agent is empty or the Python-requests default.  Setting
        # a descriptive UA avoids this.
        headers = {
            "User-Agent": "R1-A1-Astromech/1.0 (exoplanet_catalog.py)",
        }
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_url(base: str, params: dict[str, str]) -> str:
        """Build a fully-qualified HTTPS URL with URL-encoded query params.

        Parameters
        ----------
        base : str
            Base URL (must start with ``https://``).
        params : dict[str, str]
            Query parameters to URL-encode and append.

        Returns
        -------
        str
            ``base?key=value&key=value``
        """
        return f"{base}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def _angular_separation(
        ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float
    ) -> float:
        """Great-circle angular separation between two sky positions, in degrees.

        Uses the **haversine** formula which is numerically stable for the
        small angles that dominate position-matching work::

            a = sin²(Δδ/2) + cos δ₁ · cos δ₂ · sin²(Δα/2)
            d = 2 · asin(√a)

        Both RA and Dec are in *degrees* (not hours), matching the
        coordinate convention used by the NASA Exoplanet Archive.

        Parameters
        ----------
        ra1_deg, ra2_deg : float
            Right ascensions in degrees (0–360).
        dec1_deg, dec2_deg : float
            Declinations in degrees (-90–+90).

        Returns
        -------
        float
            Angular separation in degrees (0–180).
        """
        # learning: Unlike StarCatalog which stores RA in hours, the
        # exoplanet archive uses degrees for both RA and Dec, so no
        # ×15 conversion is needed here.
        ra1 = math.radians(ra1_deg)
        ra2 = math.radians(ra2_deg)
        dec1 = math.radians(dec1_deg)
        dec2 = math.radians(dec2_deg)

        d_dec = dec2 - dec1
        d_ra = ra2 - ra1

        a = (
            math.sin(d_dec / 2.0) ** 2
            + math.cos(dec1) * math.cos(dec2) * math.sin(d_ra / 2.0) ** 2
        )
        # Clamp to [0, 1] to guard against floating-point round-off that
        # could push √a slightly negative (asin domain error) or above 1.
        a = max(0.0, min(1.0, a))
        return math.degrees(2.0 * math.asin(math.sqrt(a)))

    # ------------------------------------------------------------------
    #  Local SQLite mirror
    # ------------------------------------------------------------------

    def _use_mirror(self) -> bool:
        """Return *True* if a local SQLite mirror is configured and exists.

        Checks ``self._db_path`` is set and the file exists on disk.
        This is the gate for automatic fallback in every search method.
        """
        return self._db_path is not None and self._db_path.exists()

    def _mirror_connect(self) -> sqlite3.Connection:
        """Open a read-only connection to the local mirror.

        Raises ``sqlite3.Error`` if the file doesn't exist or is corrupt.
        Callers wrap this in try/except to return error dicts.
        """
        if self._db_path is None or not self._db_path.exists():
            raise sqlite3.Error("mirror database not configured or missing")
        # learning: SQLite URI mode "file://path?mode=ro" opens read-only,
        # preventing accidental writes from search queries.
        conn = sqlite3.connect(
            f"file:{self._db_path}?mode=ro",
            uri=True,
        )
        conn.row_factory = sqlite3.Row  # access columns by name
        return conn

    def _mirror_search(
        self,
        where: str,
        params: tuple[Any, ...] = (),
        order_by: str = "pl_name",
        limit: int = 0,
    ) -> dict[str, Any]:
        """Execute a parameterised query against the local mirror.

        This is the mirror-side equivalent of :meth:`_tap_query` — all
        public search methods call this when the live endpoint fails and
        a mirror is available.

        Parameters
        ----------
        where : str
            SQL WHERE clause (without the ``WHERE`` keyword), using
            ``?`` placeholders for parameterised values.
        params : tuple
            Values to bind to the placeholders.
        order_by : str
            Column name to ORDER BY.
        limit : int
            Maximum rows (0 = all).

        Returns
        -------
        dict
            ``{"planets": [...], "count": N, "source": "local_mirror"}``
            on success, or an error dict.
        """
        try:
            conn = self._mirror_connect()
            try:
                cols = ", ".join(self._COLUMNS)
                sql = f"SELECT {cols} FROM exoplanets"
                if where:
                    sql += f" WHERE {where}"
                if order_by:
                    sql += f" ORDER BY {order_by}"
                if limit > 0:
                    sql += f" LIMIT {limit}"
                rows = conn.execute(sql, params).fetchall()
                planets = [dict(row) for row in rows]
                return {
                    "planets": planets,
                    "count": len(planets),
                    "source": "local_mirror",
                }
            finally:
                conn.close()
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "local_mirror",
            }

    def _mirror_count(self) -> dict[str, Any]:
        """Return the row count from the local mirror."""
        try:
            conn = self._mirror_connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM exoplanets"
                ).fetchone()
                return {"count": int(row["n"]), "source": "local_mirror"}
            finally:
                conn.close()
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "local_mirror",
            }

    def download_mirror(
        self, db_path: str | Path | None = None
    ) -> dict[str, Any]:
        """Download all confirmed exoplanets and store them in a local SQLite DB.

        Fetches every planet (``default_flag=1``) from the NASA Exoplanet
        Archive via TAP, creates a SQLite database at *db_path* (or
        ``self._db_path`` if set), creates the schema, and inserts all
        rows.  After this call, all search methods can operate fully
        offline by falling back to the mirror.

        Parameters
        ----------
        db_path : str, Path, or None
            Path for the mirror database.  When *None*, uses
            ``self._db_path``.  If that is also *None*, raises
            ``ValueError`` (returned as an error dict, not raised).

        Returns
        -------
        dict
            ``{"downloaded": N, "db_path": str, "source": "nasa_archive"}``
            on success, or an error dict.
        """
        try:
            # Resolve target path
            if db_path is not None:
                target = Path(db_path)
            elif self._db_path is not None:
                target = self._db_path
            else:
                return {
                    "error": "no db_path specified",
                    "type": "ValueError",
                    "api": "local_mirror",
                }

            # Fetch all planets from the live archive
            result = self.all_planets()
            if "error" in result:
                return result  # propagate TAP error

            planets = result.get("planets", [])
            count = len(planets)

            # Create directory if needed
            target.parent.mkdir(parents=True, exist_ok=True)

            # Create/overwrite the SQLite database
            # learning: We use mode=ro for reads but need read-write for
            # the initial download, so connect normally (not URI mode).
            conn = sqlite3.connect(str(target))
            try:
                conn.executescript(self._MIRROR_SCHEMA)
                conn.executescript(self._MIRROR_META_SCHEMA)

                # Clear existing data (idempotent re-download)
                conn.execute("DELETE FROM exoplanets")
                conn.execute("DELETE FROM mirror_meta")

                # Bulk insert
                # learning: executemany with parameterised placeholders is
                # the fastest safe way to bulk-insert in SQLite.  Using
                # INSERT OR REPLACE handles re-downloads gracefully.
                placeholders = ", ".join(["?"] * len(self._COLUMNS))
                cols = ", ".join(self._COLUMNS)
                insert_sql = (
                    f"INSERT OR REPLACE INTO exoplanets ({cols}) "
                    f"VALUES ({placeholders})"
                )
                rows = []
                for p in planets:
                    rows.append(tuple(p.get(c) for c in self._COLUMNS))
                conn.executemany(insert_sql, rows)

                # Record sync metadata
                conn.execute(
                    "INSERT OR REPLACE INTO mirror_meta (key, value) "
                    "VALUES (?, ?)",
                    ("last_sync_epoch", str(time.time())),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO mirror_meta (key, value) "
                    "VALUES (?, ?)",
                    ("row_count", str(count)),
                )
                conn.commit()
            finally:
                conn.close()

            # Update self._db_path so future calls use the mirror
            self._db_path = target

            return {
                "downloaded": count,
                "db_path": str(target),
                "source": "nasa_archive",
            }
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "local_mirror",
            }

    def sync_mirror(self) -> dict[str, Any]:
        """Re-download from the live archive and update the local mirror.

        Convenience wrapper around :meth:`download_mirror` that uses the
        already-configured ``self._db_path``.  If no mirror path is
        configured, returns an error dict.

        Returns
        -------
        dict
            Same shape as :meth:`download_mirror`.
        """
        if self._db_path is None:
            return {
                "error": "no mirror path configured (set db_path in __init__)",
                "type": "ValueError",
                "api": "local_mirror",
            }
        return self.download_mirror(self._db_path)

    def mirror_info(self) -> dict[str, Any]:
        """Return metadata about the local mirror database.

        Returns
        -------
        dict
            ``{"configured": bool, "exists": bool, "db_path": str|None,
            "row_count": N|None, "last_sync": str|None}`` on success,
            or an error dict.
        """
        try:
            configured = self._db_path is not None
            exists = self._use_mirror()
            info: dict[str, Any] = {
                "configured": configured,
                "exists": exists,
                "db_path": str(self._db_path) if self._db_path else None,
                "row_count": None,
                "last_sync": None,
            }
            if exists:
                conn = self._mirror_connect()
                try:
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM exoplanets"
                    ).fetchone()
                    info["row_count"] = int(row["n"])
                    sync_row = conn.execute(
                        "SELECT value FROM mirror_meta WHERE key='last_sync_epoch'"
                    ).fetchone()
                    if sync_row:
                        info["last_sync"] = sync_row["value"]
                finally:
                    conn.close()
            return info
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "local_mirror",
            }

    def _tap_query(self, sql: str) -> Any:
        """Execute an ADQL query against the TAP endpoint and return parsed JSON.

        This is the single point of contact with the HTTP transport.
        All public query methods build their ADQL and delegate here.

        Parameters
        ----------
        sql : str
            ADQL SELECT statement to execute.

        Returns
        -------
        list[dict] or dict
            Parsed JSON response — the TAP sync endpoint returns a JSON
            array of row objects when ``format=json``.  The return type
            is ``Any`` (not ``dict``) because a successful query yields a
            ``list``, while a transport-level error propagated from the
            HTTP callable could be a ``dict``.
        """
        # learning: TAP sync accepts the query as a URL parameter rather
        # than a POST body.  urlencode handles ADQL special characters
        # (spaces, quotes, semicolons) safely.
        params: dict[str, str] = {
            "query": sql,
            "format": "json",
        }
        url = self._build_url(self._TAP_URL, params)
        return self._http(url)

    # ------------------------------------------------------------------
    #  Public query API
    # ------------------------------------------------------------------

    def query(self, sql: str) -> dict[str, Any]:
        """Execute an arbitrary ADQL/TAP query against the NASA Exoplanet Archive.

        This is the escape hatch for advanced users who need queries that
        the convenience methods don't cover (joins, aggregates, etc.).
        The caller is responsible for writing valid ADQL.

        Parameters
        ----------
        sql : str
            A valid ADQL SELECT statement.

        Returns
        -------
        dict
            ``{"results": [...], "count": N}`` on success — the archive
            returns a JSON array of row objects which is wrapped for a
            consistent dict return type.  On failure, an error dict with
            keys ``"error"``, ``"type"``, ``"api"``.

        Note
        ----
        The TAP ``sync`` endpoint returns results inline.  For very large
        queries (millions of rows) consider using the ``async`` endpoint
        instead, which is not wrapped by this catalog.
        """
        try:
            result = self._tap_query(sql)
            # learning: TAP sync with format=json returns a list of dicts
            # (one per row).  We wrap it so every public method returns a
            # dict with a consistent shape.
            if isinstance(result, list):
                return {"results": result, "count": len(result), "source": "live"}
            return result
        except Exception as exc:
            # Fallback to local mirror if configured
            if self._use_mirror():
                # learning: For arbitrary SQL we can't safely translate
                # ADQL to SQLite, so we only fall back for known query
                # patterns — query() is the escape hatch, so we return
                # the error but note the mirror is available.
                pass
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
                "mirror_available": self._use_mirror(),
            }

    def all_planets(self, limit: int = 0) -> dict[str, Any]:
        """Query all confirmed exoplanets from the Planetary Systems table.

        Returns every column for every planet where ``default_flag=1``
        (the archive's preferred solution per planet).  When *limit* is
        greater than zero, adds ``TOP {limit}`` to the query to cap the
        result set.

        Parameters
        ----------
        limit : int, default 0
            Maximum number of planets to return.  When 0, returns all
            confirmed planets (currently 5,000+).

        Returns
        -------
        dict
            ``{"planets": [...], "count": N}`` on success, or an error
            dict with keys ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            # learning: ADQL supports TOP n just like SQL Server / T-SQL.
            # It goes right after SELECT and limits the row count.
            top_clause = f"TOP {limit} " if limit > 0 else ""
            sql = (
                f"SELECT {top_clause}pl_name,hostname,ra,dec,pl_rade,"
                f"pl_orbper,pl_trandep,sy_tmag,st_rad,disc_facility,"
                f"disc_year,pl_bmasse,pl_orbeccen,pl_eqt "
                f"FROM ps WHERE default_flag=1 "
                f"ORDER BY pl_name"
            )
            result = self._tap_query(sql)
            if isinstance(result, list):
                return {"planets": result, "count": len(result), "source": "live"}
            return result
        except Exception as exc:
            # Fallback to local mirror
            if self._use_mirror():
                return self._mirror_search("", limit=limit)
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
            }

    def search_by_name(self, planet_name: str) -> dict[str, Any]:
        """Case-insensitive search for a planet by name (``pl_name``).

        Uses ``LIKE`` with wildcards so partial names match — e.g.
        ``"Kepler-186"`` finds ``"Kepler-186 b"``.  Returns the first
        match (sorted by name).

        Parameters
        ----------
        planet_name : str
            Planet name or substring to search for, e.g.
            ``"Kepler-186 b"`` or ``"TRAPPIST-1"``.

        Returns
        -------
        dict
            The matching planet dict (all columns) when found, or
            ``{"found": False}`` when no match exists, or an error dict
            with keys ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            # learning: ADQL's UPPER() function is the portable way to do
            # case-insensitive comparison across database backends.  We
            # also escape single quotes in the input to prevent SQL
            # injection (though the archive is read-only, it's good
            # practice).
            safe_name = planet_name.replace("'", "''")
            sql = (
                f"SELECT pl_name,hostname,ra,dec,pl_rade,pl_orbper,"
                f"pl_trandep,sy_tmag,st_rad,disc_facility,disc_year,"
                f"pl_bmasse,pl_orbeccen,pl_eqt "
                f"FROM ps WHERE default_flag=1 "
                f"AND UPPER(pl_name) LIKE UPPER('%{safe_name}%') "
                f"ORDER BY pl_name"
            )
            result = self._tap_query(sql)
            if isinstance(result, list):
                if len(result) == 0:
                    return {"found": False}
                return result[0]
            return result
        except Exception as exc:
            # Fallback to local mirror
            if self._use_mirror():
                mr = self._mirror_search(
                    "UPPER(pl_name) LIKE UPPER(?)",
                    (f"%{planet_name}%",),
                )
                if "error" not in mr:
                    planets = mr.get("planets", [])
                    if len(planets) == 0:
                        return {"found": False}
                    return planets[0]
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
            }

    def search_by_host(self, host_name: str) -> dict[str, Any]:
        """Search for planets by host star name (``hostname``).

        Uses ``LIKE`` with wildcards for case-insensitive substring
        matching — e.g. ``"Kepler-186"`` returns all planets orbiting
        that star.

        Parameters
        ----------
        host_name : str
            Host star name or substring to search for, e.g.
            ``"Kepler-186"`` or ``"TRAPPIST-1"``.

        Returns
        -------
        dict
            ``{"planets": [...], "count": N}`` on success, or an error
            dict with keys ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            safe_host = host_name.replace("'", "''")
            sql = (
                f"SELECT pl_name,hostname,ra,dec,pl_rade,pl_orbper,"
                f"pl_trandep,sy_tmag,st_rad,disc_facility,disc_year,"
                f"pl_bmasse,pl_orbeccen,pl_eqt "
                f"FROM ps WHERE default_flag=1 "
                f"AND UPPER(hostname) LIKE UPPER('%{safe_host}%') "
                f"ORDER BY pl_name"
            )
            result = self._tap_query(sql)
            if isinstance(result, list):
                return {"planets": result, "count": len(result), "source": "live"}
            return result
        except Exception as exc:
            # Fallback to local mirror
            if self._use_mirror():
                mr = self._mirror_search(
                    "UPPER(hostname) LIKE UPPER(?)",
                    (f"%{host_name}%",),
                )
                if "error" not in mr:
                    return mr
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
            }

    def search_by_position(
        self,
        ra_degrees: float,
        dec_degrees: float,
        radius_deg: float = 10.0,
    ) -> dict[str, Any]:
        """Cone search: find planets within *radius_deg* of a sky position.

        Uses a two-stage filter:

        1. **SQL box filter** — queries the archive for planets where
           ``ra`` is within ``± radius_deg`` of the target RA and ``dec``
           is within ``± radius_deg`` of the target Dec.  This is fast
           because it uses the archive's indexed columns.

        2. **Client-side haversine filter** — for each candidate, computes
           the true great-circle angular distance and keeps only those
           within *radius_deg*.  This removes false positives at the
           corners of the box.

        Parameters
        ----------
        ra_degrees : float
            Right ascension of the search center in degrees (0–360).
        dec_degrees : float
            Declination of the search center in degrees (-90–+90).
        radius_deg : float, default 10.0
            Search radius in degrees.

        Returns
        -------
        dict
            ``{"planets": [...], "count": N}`` — planets within the
            cone, nearest first.  Each planet dict has an extra
            ``"angular_distance_deg"`` key.  On failure, an error dict
            with keys ``"error"``, ``"type"``, ``"api"``.
        """
        try:
            ra = float(ra_degrees)
            dec = float(dec_degrees)
            radius = float(radius_deg)

            # learning: Box filter is a cheap rectangle in RA/Dec space.
            # We deliberately do NOT use ADQL's native cone-search
            # functions (CONTAINS/POINT/CIRCLE) because the archive's
            # TAP implementation can be slow with them — a simple
            # range query on indexed columns is much faster.
            ra_min = ra - radius
            ra_max = ra + radius
            dec_min = dec - radius
            dec_max = dec + radius

            sql = (
                f"SELECT pl_name,hostname,ra,dec,pl_rade,pl_orbper,"
                f"pl_trandep,sy_tmag,st_rad,disc_facility,disc_year,"
                f"pl_bmasse,pl_orbeccen,pl_eqt "
                f"FROM ps WHERE default_flag=1 "
                f"AND ra IS NOT NULL AND dec IS NOT NULL "
                f"AND ra BETWEEN {ra_min} AND {ra_max} "
                f"AND dec BETWEEN {dec_min} AND {dec_max} "
                f"ORDER BY pl_name"
            )
            result = self._tap_query(sql)

            if not isinstance(result, list):
                return result

            # learning: Client-side haversine filtering removes corner
            # false positives — points inside the RA/Dec box but outside
            # the circular cone.  At 10° radius the difference is
            # significant (box corners are ~14° from center).
            filtered: list[tuple[float, dict]] = []
            for planet in result:
                p_ra = planet.get("ra")
                p_dec = planet.get("dec")
                if p_ra is None or p_dec is None:
                    continue
                sep = self._angular_separation(
                    ra, dec, float(p_ra), float(p_dec)
                )
                if sep <= radius:
                    entry = dict(planet)
                    entry["angular_distance_deg"] = sep
                    filtered.append((sep, entry))

            # Sort nearest first.
            filtered.sort(key=lambda pair: pair[0])
            planets = [entry for _, entry in filtered]
            return {"planets": planets, "count": len(planets), "source": "live"}
        except Exception as exc:
            # Fallback to local mirror
            if self._use_mirror():
                ra = float(ra_degrees)
                dec = float(dec_degrees)
                radius = float(radius_deg)
                mr = self._mirror_search(
                    "ra IS NOT NULL AND dec IS NOT NULL "
                    "AND ra BETWEEN ? AND ? "
                    "AND dec BETWEEN ? AND ?",
                    (ra - radius, ra + radius,
                     dec - radius, dec + radius),
                )
                if "error" not in mr:
                    planets = mr.get("planets", [])
                    filtered = []
                    for planet in planets:
                        p_ra = planet.get("ra")
                        p_dec = planet.get("dec")
                        if p_ra is None or p_dec is None:
                            continue
                        sep = self._angular_separation(
                            ra, dec, float(p_ra), float(p_dec)
                        )
                        if sep <= radius:
                            entry = dict(planet)
                            entry["angular_distance_deg"] = sep
                            filtered.append((sep, entry))
                    filtered.sort(key=lambda pair: pair[0])
                    planets = [entry for _, entry in filtered]
                    return {
                        "planets": planets,
                        "count": len(planets),
                        "source": "local_mirror",
                    }
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
            }

    def search_by_radius(
        self, min_rade: float, max_rade: float
    ) -> dict[str, Any]:
        """Search for planets by radius range in Earth radii (``pl_rade``).

        Parameters
        ----------
        min_rade : float
            Minimum planet radius in Earth radii.
        max_rade : float
            Maximum planet radius in Earth radii.

        Returns
        -------
        dict
            ``{"planets": [...], "count": N}`` on success, or an error
            dict with keys ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            sql = (
                f"SELECT pl_name,hostname,ra,dec,pl_rade,pl_orbper,"
                f"pl_trandep,sy_tmag,st_rad,disc_facility,disc_year,"
                f"pl_bmasse,pl_orbeccen,pl_eqt "
                f"FROM ps WHERE default_flag=1 "
                f"AND pl_rade IS NOT NULL "
                f"AND pl_rade BETWEEN {float(min_rade)} AND {float(max_rade)} "
                f"ORDER BY pl_rade"
            )
            result = self._tap_query(sql)
            if isinstance(result, list):
                return {"planets": result, "count": len(result), "source": "live"}
            return result
        except Exception as exc:
            # Fallback to local mirror
            if self._use_mirror():
                mr = self._mirror_search(
                    "pl_rade IS NOT NULL AND pl_rade BETWEEN ? AND ?",
                    (float(min_rade), float(max_rade)),
                    order_by="pl_rade",
                )
                if "error" not in mr:
                    return mr
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
            }

    def search_by_period(
        self, min_period: float, max_period: float
    ) -> dict[str, Any]:
        """Search for planets by orbital period range in days (``pl_orbper``).

        Parameters
        ----------
        min_period : float
            Minimum orbital period in days.
        max_period : float
            Maximum orbital period in days.

        Returns
        -------
        dict
            ``{"planets": [...], "count": N}`` on success, or an error
            dict with keys ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            sql = (
                f"SELECT pl_name,hostname,ra,dec,pl_rade,pl_orbper,"
                f"pl_trandep,sy_tmag,st_rad,disc_facility,disc_year,"
                f"pl_bmasse,pl_orbeccen,pl_eqt "
                f"FROM ps WHERE default_flag=1 "
                f"AND pl_orbper IS NOT NULL "
                f"AND pl_orbper BETWEEN {float(min_period)} "
                f"AND {float(max_period)} "
                f"ORDER BY pl_orbper"
            )
            result = self._tap_query(sql)
            if isinstance(result, list):
                return {"planets": result, "count": len(result), "source": "live"}
            return result
        except Exception as exc:
            # Fallback to local mirror
            if self._use_mirror():
                mr = self._mirror_search(
                    "pl_orbper IS NOT NULL AND pl_orbper BETWEEN ? AND ?",
                    (float(min_period), float(max_period)),
                    order_by="pl_orbper",
                )
                if "error" not in mr:
                    return mr
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
            }

    def search_by_facility(self, facility: str) -> dict[str, Any]:
        """Search for planets by discovery facility (``disc_facility``).

        Uses ``LIKE`` matching so partial names work — e.g.
        ``"TESS"`` matches ``"Transiting Exoplanet Survey Satellite (TESS)"``.

        Parameters
        ----------
        facility : str
            Facility name or substring to search for, e.g.
            ``"Kepler"``, ``"TESS"``, ``"Hubble"``.

        Returns
        -------
        dict
            ``{"planets": [...], "count": N}`` on success, or an error
            dict with keys ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            safe_facility = facility.replace("'", "''")
            sql = (
                f"SELECT pl_name,hostname,ra,dec,pl_rade,pl_orbper,"
                f"pl_trandep,sy_tmag,st_rad,disc_facility,disc_year,"
                f"pl_bmasse,pl_orbeccen,pl_eqt "
                f"FROM ps WHERE default_flag=1 "
                f"AND disc_facility IS NOT NULL "
                f"AND disc_facility LIKE '%{safe_facility}%' "
                f"ORDER BY disc_year DESC, pl_name"
            )
            result = self._tap_query(sql)
            if isinstance(result, list):
                return {"planets": result, "count": len(result), "source": "live"}
            return result
        except Exception as exc:
            # Fallback to local mirror
            if self._use_mirror():
                mr = self._mirror_search(
                    "disc_facility IS NOT NULL AND disc_facility LIKE ?",
                    (f"%{facility}%",),
                    order_by="disc_year DESC, pl_name",
                )
                if "error" not in mr:
                    return mr
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
            }

    def count(self) -> dict[str, Any]:
        """Return the total number of confirmed exoplanets in the archive.

        Returns
        -------
        dict
            ``{"count": N}`` on success, or an error dict with keys
            ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            # learning: COUNT(*) is the cheapest way to get the total
            # without transferring all rows.  ADQL supports standard
            # SQL aggregate functions.
            sql = "SELECT COUNT(*) AS n FROM ps WHERE default_flag=1"
            result = self._tap_query(sql)
            if isinstance(result, list) and len(result) > 0:
                # learning: TAP JSON format wraps scalar results in a
                # list of dicts.  The column alias "n" becomes the key.
                n = result[0].get("n", 0)
                return {"count": int(n), "source": "live"}
            return {"count": 0, "source": "live"}
        except Exception as exc:
            # Fallback to local mirror
            if self._use_mirror():
                mr = self._mirror_count()
                if "error" not in mr:
                    return mr
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "exoplanet_archive",
            }

    def info(self) -> dict[str, Any]:
        """Return catalog capability metadata.

        Reports whether the catalog is operational, lists the available
        API identifiers, and attempts to retrieve the current total count
        of confirmed exoplanets from the archive.

        Returns
        -------
        dict
            ``{"available": bool, "apis": ["exoplanet_archive"],
            "total_known": N}`` on success.  When the archive is
            unreachable, ``total_known`` is ``None`` and ``available``
            reflects whether ``requests`` is importable (or an injected
            client is in use).
        """
        try:
            # learning: The available flag follows the same pattern as
            # AstroBridge.info() — check whether requests is importable
            # when using the default transport.
            available: bool = True
            if self._http is self._default_http:
                try:
                    import importlib.util

                    available = (
                        importlib.util.find_spec("requests") is not None
                    )
                except Exception:
                    available = False

            # Best-effort count query — don't fail info() if the network
            # is down; just report total_known as None.
            total_known: int | None = None
            if available:
                count_result = self.count()
                if "count" in count_result and "error" not in count_result:
                    total_known = count_result["count"]

            # Mirror status
            mirror = self.mirror_info()

            return {
                "available": available,
                "apis": list(self._APIS),
                "total_known": total_known,
                "mirror": mirror,
            }
        except Exception as exc:
            return {
                "available": False,
                "apis": list(self._APIS),
                "total_known": None,
                "mirror": self.mirror_info() if self._use_mirror() else None,
                "error": str(exc),
                "type": type(exc).__name__,
            }

    def summary(self) -> str:
        """Return a human-readable summary of the catalog state.

        Returns
        -------
        str
            A multi-line string describing the catalog's availability,
            supported APIs, and (if reachable) the total number of
            confirmed exoplanets known to the archive.
        """
        info = self.info()
        lines = [
            "R1-A1 Exoplanet Catalog — NASA Exoplanet Archive (TAP)",
            "=" * 52,
            f"  Endpoint : {self._TAP_URL}",
            f"  Available: {info.get('available', False)}",
            f"  APIs     : {', '.join(info.get('apis', []))}",
        ]
        total = info.get("total_known")
        if total is not None:
            lines.append(f"  Confirmed exoplanets known: {total}")
        else:
            lines.append("  Confirmed exoplanets known: (unreachable)")

        # Mirror status
        mirror = info.get("mirror") or {}
        if mirror.get("configured"):
            lines.append(f"  Mirror   : {mirror.get('db_path', '?')}")
            if mirror.get("exists"):
                lines.append(f"  Mirror rows: {mirror.get('row_count', '?')}")
                sync = mirror.get("last_sync")
                if sync:
                    lines.append(f"  Last sync: {sync}")
            else:
                lines.append("  Mirror   : configured but not downloaded")
        else:
            lines.append("  Mirror   : not configured")

        if "error" in info:
            lines.append(f"  Last error: {info['error']}")
        return "\n".join(lines)