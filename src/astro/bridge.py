"""Astronomical data bridge for the R1-A1 astromech robot.

Provides unified, failure-tolerant access to several public astronomy APIs:

* **NASA JPL Horizons** — solar-system body ephemerides and observability.
* **SIMBAD** — astronomical object database (name and coordinate look-ups).
* **NASA SkyView** — survey-image retrieval.
* **NASA InSight Mars Weather** — Martian surface weather telemetry.

Design principles
-----------------
- **HTTPS only** — every endpoint uses TLS-encrypted URLs.
- **Never raise** — all public methods catch exceptions and return an
  error dict ``{"error": ..., "type": ..., "api": ...}`` so the bridge
  can be used safely from robotic control loops where an unhandled
  exception would be dangerous.
- **Lazy dependencies** — the optional ``requests`` package is imported
  inside :meth:`AstroBridge._default_http` so the module loads and
  operates with an injected client even when ``requests`` is absent.
- **Injectable transport** — an alternative HTTP callable can be passed
  to :meth:`AstroBridge.__init__` for unit testing without network access.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Callable


class AstroBridge:
    """Fail-safe bridge to public astronomical data APIs.

    The bridge wraps four external services behind a single, consistent
    interface.  Each method builds an HTTPS URL, delegates the HTTP GET to
    an injectable callable, and returns the parsed JSON as a dict.  When
    anything goes wrong — network error, non-200 status, JSON parse failure,
    or missing dependency — the method catches the exception and returns a
    structured error dict instead of raising.

    Parameters
    ----------
    http_client : callable, optional
        A callable with signature ``client(url: str) -> dict`` that performs
        the HTTP request and returns the parsed JSON body.  When *None*
        (the default) the bridge uses :meth:`_default_http`, which lazily
        imports :mod:`requests`.  Injecting a stub callable makes the bridge
        fully testable in isolation — no network, no ``requests`` needed.

    Attributes
    ----------
    _http : callable
        The active HTTP transport (injected or default).

    Examples
    --------
    >>> bridge = AstroBridge()
    >>> bridge.info()["apis"]
    ['horizons', 'simbad', 'skyview', 'mars_weather']

    >>> # inject a fake client for testing
    >>> fake = lambda url: {"url": url}
    >>> test_bridge = AstroBridge(http_client=fake)
    >>> test_bridge.mars_weather()["url"].startswith("https://")
    True
    """

    # ------------------------------------------------------------------
    #  Endpoint constants — all HTTPS
    # ------------------------------------------------------------------
    _HORIZONS_URL: str = "https://ssd.jpl.nasa.gov/api/horizons.api"
    _SIMBAD_ID_URL: str = "https://simbad.u-strasbg.fr/simbad/sim-id"
    _SIMBAD_COO_URL: str = "https://simbad.u-strasbg.fr/simbad/sim-coo"
    _SKYVIEW_URL: str = "https://skyview.gsfc.nasa.gov/current/cgi/query.pl"
    _MARS_WEATHER_URL: str = "https://api.nasa.gov/insight_weather/"

    _APIS: list[str] = ["horizons", "simbad", "skyview", "mars_weather"]

    # ------------------------------------------------------------------
    #  Construction & transport
    # ------------------------------------------------------------------

    def __init__(
        self,
        http_client: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        """Initialise the bridge with an optional injectable HTTP client.

        Parameters
        ----------
        http_client : callable or None
            A callable ``(url: str) -> dict`` used for every HTTP request.
            Pass *None* to use the built-in :meth:`_default_http` (which
            lazily imports :mod:`requests`).
        """
        self._http: Callable[[str], dict[str, Any]] = (
            http_client if http_client is not None else self._default_http
        )

    @staticmethod
    def _default_http(url: str, timeout: int = 30) -> dict[str, Any]:
        """Default HTTP GET transport backed by :mod:`requests`.

        ``requests`` is imported *lazily* (inside this method) so that the
        module can be imported and used with an injected client even when
        the ``requests`` package is not installed.

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
            Any network, HTTP-status, or JSON-parsing error is *deliberately
            allowed to propagate* here; the public query methods that call
            this catch it and return an error dict.
        """
        import requests  # lazy import — requests is optional

        response = requests.get(url, timeout=timeout)
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

    # ------------------------------------------------------------------
    #  Public query API
    # ------------------------------------------------------------------

    def horizons_query(
        self,
        body: str,
        datetime_str: str | None = None,
    ) -> dict[str, Any]:
        """Query NASA JPL Horizons for solar-system body ephemeris data.

        Uses the JPL Horizons REST API to retrieve observational ephemeris
        and physical data for a solar-system body (planet, moon, asteroid,
        comet, or spacecraft).

        Parameters
        ----------
        body : str
            Horizons body designator — e.g. ``"499"`` (Mars),
            ``"599"`` (Jupiter), ``"10"`` (Sun), or a target name.
        datetime_str : str or None, optional
            Observation time in Horizons-compatible format (e.g.
            ``"2025-Jan-01 00:00"``).  When provided, it is sent as the
            ``TLIST`` parameter (single-epoch ephemeris).  When *None* the
            API returns default ephemeris data.

        Returns
        -------
        dict
            Parsed JSON response from Horizons, or an error dict with keys
            ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            params: dict[str, str] = {
                "format": "json",
                "COMMAND": str(body),
                "OBJ_DATA": "YES",
                "MAKE_EPHEM": "YES",
                "EPHEM_TYPE": "OBSERVER",
                "CENTER": "500",
            }
            if datetime_str is not None:
                params["TLIST"] = str(datetime_str)
            url = self._build_url(self._HORIZONS_URL, params)
            return self._http(url)
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "horizons",
            }

    def simbad_query(self, object_name: str) -> dict[str, Any]:
        """Query SIMBAD by astronomical object name.

        Looks up an object (star, galaxy, nebula, etc.) by its commonly
        used identifier (e.g. ``"M31"``, ``"Sirius"``, ``"NGC 224"``)
        using the SIMBAD ``sim-id`` service.

        Parameters
        ----------
        object_name : str
            Object identifier or name to resolve.

        Returns
        -------
        dict
            Parsed JSON response from SIMBAD, or an error dict with keys
            ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            params: dict[str, str] = {
                "Ident": str(object_name),
                "output.format": "JSON",
            }
            url = self._build_url(self._SIMBAD_ID_URL, params)
            return self._http(url)
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "simbad",
            }

    def simbad_coordinate_query(
        self,
        ra_degrees: float,
        dec_degrees: float,
        radius_arcmin: float = 10.0,
    ) -> dict[str, Any]:
        """Query SIMBAD by sky coordinates (cone search).

        Searches the SIMBAD database for objects within a circular region
        centered on the given equatorial coordinates, using the SIMBAD
        ``sim-coo`` service.

        Parameters
        ----------
        ra_degrees : float
            Right ascension in decimal degrees (J2000).
        dec_degrees : float
            Declination in decimal degrees (J2000).
        radius_arcmin : float, default 10.0
            Search radius in arcminutes.

        Returns
        -------
        dict
            Parsed JSON response from SIMBAD, or an error dict with keys
            ``"error"``, ``"type"``, ``"api"`` on failure.
        """
        try:
            params: dict[str, str] = {
                "Coo": f"{float(ra_degrees)} {float(dec_degrees)}",
                "Radius": str(float(radius_arcmin)),
                "Radius.unit": "arcmin",
                "output.format": "JSON",
            }
            url = self._build_url(self._SIMBAD_COO_URL, params)
            return self._http(url)
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "simbad",
            }

    def skyview_query(
        self,
        ra_degrees: float,
        dec_degrees: float,
        survey: str = "DSS",
    ) -> dict[str, Any]:
        """Query NASA SkyView for a survey image at given coordinates.

        Requests a survey image (default: Digitized Sky Survey) centered
        on the specified equatorial coordinates via the NASA SkyView
        ``query.pl`` CGI endpoint.

        Parameters
        ----------
        ra_degrees : float
            Right ascension of the image center in decimal degrees.
        dec_degrees : float
            Declination of the image center in decimal degrees.
        survey : str, default "DSS"
            Survey name — e.g. ``"DSS"``, ``"2MASS-J"``, ``"GALEX"``.

        Returns
        -------
        dict
            Parsed response from SkyView, or an error dict with keys
            ``"error"``, ``"type"``, ``"api"`` on failure.

        Note
        ----
        The SkyView ``query.pl`` endpoint may return HTML or binary image
        data rather than JSON.  When using the default HTTP client, a
        non-JSON response triggers a parse error that is caught and
        returned as an error dict.  Inject a custom HTTP client if you
        need to handle non-JSON SkyView responses.
        """
        try:
            params: dict[str, str] = {
                "Position": f"{float(ra_degrees)}, {float(dec_degrees)}",
                "Survey": str(survey),
                "Return": "PNG",
                "Pixels": "300",
                "size": "1.0",
            }
            url = self._build_url(self._SKYVIEW_URL, params)
            return self._http(url)
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "skyview",
            }

    def mars_weather(self) -> dict[str, Any]:
        """Query NASA InSight Mars lander weather data.

        Retrieves the latest Martian surface weather telemetry (air
        temperature, wind speed, pressure) from the NASA InSight lander
        via the public NASA API.  Uses the ``DEMO_KEY`` API key, which is
        rate-limited but sufficient for low-frequency queries.

        Returns
        -------
        dict
            Parsed JSON response from the NASA InSight Weather API, or an
            error dict with keys ``"error"``, ``"type"``, ``"api"`` on
            failure.
        """
        try:
            params: dict[str, str] = {
                "api_key": "DEMO_KEY",
                "feedtype": "json",
                "ver": "1.0",
            }
            url = self._build_url(self._MARS_WEATHER_URL, params)
            return self._http(url)
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "api": "mars_weather",
            }

    def info(self) -> dict[str, Any]:
        """Return bridge capability metadata.

        Reports whether the bridge is operational and lists the available
        API methods.

        Returns
        -------
        dict
            ``{"available": bool, "apis": ["horizons", "simbad",
            "skyview", "mars_weather"]}``.  The ``available`` flag is
            ``True`` when an injected HTTP client is in use, or when the
            default client's dependency (``requests``) is importable.
        """
        try:
            available: bool = True
            if self._http is self._default_http:
                try:
                    import importlib.util
                    available = importlib.util.find_spec("requests") is not None
                except Exception:
                    available = False
            return {
                "available": available,
                "apis": list(self._APIS),
            }
        except Exception as exc:
            return {
                "available": False,
                "apis": list(self._APIS),
                "error": str(exc),
                "type": type(exc).__name__,
            }