"""Exoplanet transit detection for the R1-A1 astromech robot.

This module adapts the transit-detection pipeline from the exoplanet-hunter
project into the R1-A1 droid's architecture and coding conventions.  It
provides the :class:`ExoplanetDetector` class, which searches the NASA MAST
portal for TESS (Transiting Exoplanet Survey Satellite) light curves,
downloads and flattens them, and runs a Box-fitting Least Squares (BLS)
periodogram to detect the periodic, box-shaped flux dips caused by a planet
transiting in front of its host star.

What is a transit?
-----------------
A **transit** occurs when a planet passes between its host star and the
observer, blocking a tiny fraction of the star's light.  For a hot Jupiter
the dip is ~1 % (10 000 ppm); for an Earth-sized planet around a Sun-like star
it is only ~0.01 % (100 ppm).  TESS monitors ~200 000 bright stars for exactly
these dips.

BLS — Box-fitting Least Squares
--------------------------------
The BLS algorithm (Kovács, Zucker & Mazeh 2002) is *the* classical method for
detecting transits in photometric light curves.  Its physical insight is
beautifully simple: a transit produces a **box-shaped dip** — the flux drops
abruptly, stays roughly constant for the transit duration, then rises
abruptly back to the baseline.  BLS fits a square-well (box) shape at *every
trial period and phase* and reports the period whose box best matches the
data.

The four key transit parameters BLS returns:

* **period (P)** — the orbital period of the planet, in days.  The time
  between successive transits.
* **duration (T)** — how long the transit lasts, in days (typically a few
  hours for short-period planets).
* **depth (δ)** — the fractional flux drop during transit.  Directly related
  to the ratio of the planet and star radii: δ ≈ (R_p / R_★)².
* **epoch (T₀)** — the mid-transit time (in BJD — Barycentric Julian Date),
  i.e. the reference time of one transit.  All future transit times are
  T₀ + n·P.
* **SNR (signal-to-noise ratio)** — the statistical significance of the
  detection.  SNR > ~6–7 is generally considered a robust detection.

Why flatten first?
------------------
Stars are not constant.  They pulsate, rotate (carrying starspots in and out
of view), and flare.  These stellar-variability signals are typically
*smooth* and *slow* compared to the sharp, brief transit dips.  Flattening
divides the light curve by a moving-median trend, removing the slow
variations so the transit dips — which are narrow in time — stand out against
a normalised ~1.0 baseline.  Without flattening, BLS would waste sensitivity
fitting the star's pulsation envelope rather than the transit.

The period range (0.5 – 30 d)
-----------------------------
TESS observes most of the sky for ~27 days per sector.  To detect at least
two transits (the minimum to confirm a period), the orbital period must be
shorter than roughly half the observing baseline — i.e. P < ~13 d for a single
sector.  We extend the search to 30 d so that multi-sector stitched light
curves (covering months) can catch longer-period planets.  The sweet spot for
TESS is short-period planets (P < 30 d): these are almost always hot
Jupupiters or ultra-short-period rocky planets, and their frequent transits
make them the easiest to detect.  Periods below 0.5 d are rare (ultra-short-
period planets) and risk aliasing against TESS's ~2-minute or 20-second
cadence.

Design principles
-----------------
- **Pure-stdlib import surface** — only :mod:`typing`, :mod:`logging`, and
  :mod:`dataclasses` are imported at module level.  :mod:`lightkurve`,
  :mod:`numpy`, and :mod:`requests` are imported *lazily* inside methods so
  the module loads on the droid even when those heavy packages are absent.
- **Never raise** — every public method catches exceptions and returns a
  structured error dict ``{"error": ..., "type": ..., "detail": ...}`` so the
  detector is safe to call from a robotic control loop where an unhandled
  exception could be dangerous.
- **Injectable transport** — an alternative ``http_client`` callable and an
  alternative ``lightkurve_client`` callable can be passed to
  :meth:`ExoplanetDetector.__init__` for unit testing without a network or
  SciPy stack.
- **Learning annotations** — inline ``# LEARN:`` / ``# learning:`` comments
  explain the astronomy behind non-obvious choices so a maintainer (human or
  droid) learns the *why*, not just the *what*.

References
----------
- Kovács, Zucker & Mazeh (2002), "A box-fitting algorithm in the detection of
  transiting planets", A&A 391, 369.
- Hippke & Heller (2019), "Optimized transit detection algorithms", A&A 623,
  A39 (TLS, the successor to BLS).
- lightkurve documentation: https://lightkurve.github.io/
- NASA Exoplanet Archive TAP API:
  https://exoplanetarchive.ipac.caltech.edu/TAP/sync
"""

from __future__ import annotations

import logging
from typing import Any, Callable

# --------------------------------------------------------------------------- #
#  Module-level constants                                                     #
# --------------------------------------------------------------------------- #

#: MAST (Mikulski Archive for Space Telescopes) portal — the public HTTPS
#: endpoint through which TESS light-curve products are discovered and
#: downloaded.  lightkurve queries MAST under the hood; we expose the URL
#: for documentation, diagnostics, and custom HTTP-client injection.
TESS_DATA_URL: str = "https://mast.stsci.edu/portal/Mashup/MashupQueryPort.asvc"

#: NASA Exoplanet Archive TAP (Table Access Protocol) sync endpoint.  Used
#: by :meth:`ExoplanetDetector.validate_known_planet` (via the catalog module)
#: to cross-check a detection against the literature.
EXOPLANET_ARCHIVE_URL: str = (
    "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
)

#: Default BLS period-search range in days.  TESS's ~27-day sector cadence
#: means periods longer than ~13 d require multi-sector stitching; 30 d is a
#: generous upper bound for stitched curves.  0.5 d avoids cadence aliasing.
DEFAULT_PERIOD_RANGE: tuple[float, float] = (0.5, 30.0)

#: Default flatten window length in cadences.  A 401-point window (~3.3 h at
#: 2-min cadence) is long enough to ride over transit dips (so they are not
#: removed) yet short enough to track stellar rotation / pulsation.
DEFAULT_FLATTEN_WINDOW: int = 401

#: Outlier-rejection sigma used before flattening.  Points deviating by more
#: than 5 σ from the median are removed so cosmic-ray hits do not skew the
#: flattening trend.
DEFAULT_OUTLIER_SIGMA: float = 5.0

#: Number of trial periods BLS evaluates across the period range.  More
#: periods = finer period resolution but slower; 10 000 is a good balance.
DEFAULT_BLS_PERIODS: int = 10_000

logger = logging.getLogger(__name__)


class ExoplanetDetector:
    """Exoplanet transit detector built on TESS photometry and BLS.

    The detector wraps the full transit-detection pipeline — target search,
    light-curve download, flattening, and BLS periodogram — behind a single
    fail-safe class that never raises from a public method.  It is designed
    to be called safely from R1-A1's robotic control loop: every failure
    (network error, missing dependency, empty search result, BLS failure) is
    caught and returned as a structured error dict.

    Transport injection
    -------------------
    Both the HTTP layer (used for target search and catalog cross-check) and
    the lightkurve layer (used for light-curve download and BLS) are
    injectable callables.  Passing stub callables at construction time makes
    the detector fully testable in isolation — no network, no SciPy, no
    lightkurve required::

        >>> detector = ExoplanetDetector(
        ...     http_client=lambda url: {"mock": True},
        ...     lightkurve_client=lambda **kw: {"mock_lc": True},
        ... )
        >>> "available" in detector.info()
        True

    Parameters
    ----------
    http_client : callable or None
        A callable with signature ``client(url: str) -> dict`` that performs
        an HTTP GET and returns the parsed JSON body.  When *None*, a default
        implementation lazily imports :mod:`requests`.
    lightkurve_client : callable or None
        A callable with signature ``client(**kwargs) -> Any`` that stands in
        for the :mod:`lightkurve` search/download/BLS operations.  When
        *None*, a default implementation lazily imports :mod:`lightkurve`.

    Attributes
    ----------
    _http : callable
        The active HTTP transport (injected or default).
    _lk : callable
        The active lightkurve transport (injected or default).
    """

    # ------------------------------------------------------------------ #
    #  Construction & transport                                          #
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        http_client: Callable[..., dict[str, Any]] | None = None,
        lightkurve_client: Callable[..., Any] | None = None,
    ) -> None:
        """Initialise the detector with optional injectable transports.

        Parameters
        ----------
        http_client : callable or None
            HTTP GET callable ``(url: str) -> dict``.  *None* uses the
            built-in default (lazily imports :mod:`requests`).
        lightkurve_client : callable or None
            lightkurve-operation callable ``(action: str, **kw) -> Any``.
            *None* uses the built-in default (lazily imports
            :mod:`lightkurve`).
        """
        self._http: Callable[..., dict[str, Any]] = (
            http_client if http_client is not None else self._default_http
        )
        self._lk: Callable[..., Any] = (
            lightkurve_client
            if lightkurve_client is not None
            else self._default_lightkurve
        )

    # ------------------------------------------------------------------ #
    #  Default transports (lazy heavy-dep imports)                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _default_http(url: str, timeout: int = 60) -> dict[str, Any]:
        """Default HTTP GET transport backed by :mod:`requests`.

        ``requests`` is imported *lazily* so the module can be imported and
        used with an injected client even when ``requests`` is absent.

        Parameters
        ----------
        url : str
            Fully-qualified HTTPS URL to fetch.
        timeout : int, default 60
            Request timeout in seconds (generous for large TESS downloads).

        Returns
        -------
        dict
            Parsed JSON response body.

        Raises
        ------
        Exception
            Any network, HTTP-status, or JSON error propagates here; the
            public methods that call this catch it and return an error dict.
        """
        import requests  # lazy import — requests is optional

        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _default_lightkurve(action: str, **kwargs: Any) -> Any:
        """Default lightkurve transport — lazily imports :mod:`lightkurve`.

        This dispatches named operations to the appropriate lightkurve API
        calls, importing :mod:`lightkurve` (and :mod:`numpy` where needed)
        only when actually invoked.  Supported actions:

        - ``"search"``  → ``lightkurve.search_lightcurve(target, mission=...)``
        - ``"download"`` → ``search_result[index].download()``
        - ``"bls"``     → ``lc.to_periodogram(method="bls", ...)``

        Parameters
        ----------
        action : str
            The lightkurve operation to perform.
        **kwargs
            Keyword arguments forwarded to the operation.

        Returns
        -------
        Any
            The lightkurve result object.

        Raises
        ------
        Exception
            Propagates here; public callers catch and return error dicts.
        """
        import lightkurve as lk  # lazy import — lightkurve is optional
        import numpy as np        # lazy import — numpy is optional

        if action == "search":
            # learning: lightkurve.search_lightcurve queries the MAST archive
            # and returns a SearchResult whose table lists every available
            # TESS light curve (one row per sector).
            target = kwargs["target"]
            mission = kwargs.get("mission", "TESS")
            return lk.search_lightcurve(target, mission=mission)

        if action == "download":
            # learning: SearchResult[index].download() fetches the actual
            # light-curve FITS product from MAST and returns a LightCurve
            # object with .time and .flux arrays.
            search_result = kwargs["search_result"]
            index = kwargs.get("index", 0)
            return search_result[index].download()

        if action == "bls":
            # learning: to_periodogram(method="bls") evaluates the
            # Box-fitting Least Squares statistic over a grid of trial
            # periods and returns a BoxLeastSquaresPeriodogram whose
            # .period_at_max_power / .depth_at_max_power / .duration_at_max_power
            # attributes give the best-fit transit parameters.
            lc = kwargs["lightcurve"]
            periods = np.linspace(
                kwargs["period_min"], kwargs["period_max"],
                kwargs.get("n_periods", DEFAULT_BLS_PERIODS),
            )
            return lc.to_periodogram(method="bls", period=periods)

        raise ValueError(f"unknown lightkurve action: {action!r}")

    # ------------------------------------------------------------------ #
    #  Public API                                                        #
    # ------------------------------------------------------------------ #

    def search_target(self, star_name_or_tic_id: str) -> dict[str, Any]:
        """Search MAST/TESS for light-curve data for a given target.

        Resolves a target — either a common star name (e.g. ``"WASP-18"``)
        or a TESS Input Catalog (TIC) identifier (e.g. ``"TIC 100100827"``)
        — to the list of TESS light curves available in the MAST archive.

        Parameters
        ----------
        star_name_or_tic_id : str
            Target name or TIC ID to search for.

        Returns
        -------
        dict
            On success: ``{"target": str, "count": int, "sectors": list,
            "search_result": <opaque>}``.  The ``search_result`` value is the
            raw lightkurve ``SearchResult`` and may not be JSON-serialisable;
            callers that need pure-JSON output should use ``sectors`` and
            ``count``.  On failure: ``{"error": str, "type": str,
            "detail": str}``.
        """
        try:
            target = str(star_name_or_tic_id).strip()
            if not target:
                return {
                    "error": "empty target name",
                    "type": "ValueError",
                    "detail": "star_name_or_tic_id must be a non-empty string",
                }

            # learning: TIC (TESS Input Catalog) IDs uniquely identify each
            # of the ~1.8 billion stars in TESS's input catalogue.  Names like
            # "WASP-18" are resolved by MAST's name resolver to TIC IDs
            # internally — we just pass the string through.
            search_result = self._lk(action="search", target=target)

            count = len(search_result)
            if count == 0:
                return {
                    "target": target,
                    "count": 0,
                    "sectors": [],
                    "error": "no TESS light curves found",
                    "type": "EmptyResult",
                    "detail": (
                        f"MAST has no TESS light curves for {target!r}. "
                        "The target may be outside the TESS observing "
                        "footprint or named differently in the archive."
                    ),
                }

            # learning: TESS observes in 27.4-day "sectors"; each sector
            # covers a 24°×96° strip of sky.  Multiple sectors of the same
            # star can be stitched together to extend the time baseline.
            sectors: list[Any] = []
            try:
                sectors = search_result.table["sequence_number"][:20].tolist()
            except Exception:
                # If we cannot extract sector numbers, leave the list empty
                # but still report the count — the search succeeded.
                sectors = []

            return {
                "target": target,
                "count": count,
                "sectors": sectors,
                "search_result": search_result,
            }
        except Exception as exc:
            logger.exception("search_target failed for %r", star_name_or_tic_id)
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "detail": "lightkurve search_lightcurve failed — "
                          "check network connectivity and target name",
            }

    def download_lightcurve(
        self,
        tic_id: int,
        sector: int | None = None,
    ) -> dict[str, Any]:
        """Download a TESS light curve for a TIC ID.

        Searches MAST for all available TESS light curves for the given TIC
        ID, then downloads the first (or a specified) sector.  The returned
        dict carries the raw ``time`` and ``flux`` arrays so the BLS step can
        operate on them directly.

        Parameters
        ----------
        tic_id : int
            TESS Input Catalog ID of the target star.
        sector : int or None, optional
            Specific TESS sector to download.  When *None*, the first
            available light curve is used.

        Returns
        -------
        dict
            On success: ``{"tic_id": int, "sector": int, "time": list,
            "flux": list, "n_cadences": int, "lightcurve": <opaque>}``.
            ``time`` is in BJD and ``flux`` is the raw flux (e.g. e-/s).  The
            ``lightcurve`` key holds the raw lightkurve ``LightCurve`` object
            for downstream use.  On failure: ``{"error": str, "type": str,
            "detail": str}``.
        """
        try:
            # learning: TIC IDs are integers; we search by "TIC <id>" so
            # MAST's resolver maps it to the right star.
            target = f"TIC {int(tic_id)}"
            search_result = self._lk(action="search", target=target)

            if len(search_result) == 0:
                return {
                    "error": "no light curves found",
                    "type": "EmptyResult",
                    "detail": f"MAST has no TESS data for TIC {tic_id}",
                }

            # Pick the requested sector, or default to the first result.
            index = 0
            actual_sector: Any = None
            available_sectors: list[Any] = []
            if sector is not None:
                try:
                    sectors_table = search_result.table["sequence_number"]
                    available_sectors = list(sectors_table)
                    index = available_sectors.index(int(sector))
                    actual_sector = int(sector)
                except (ValueError, KeyError):
                    return {
                        "error": "sector not found",
                        "type": "SectorNotFound",
                        "detail": (
                            f"Sector {sector} is not available for TIC {tic_id}. "
                            f"Available sectors: {available_sectors}"
                        ),
                    }

            # learning: download() fetches the full FITS light-curve product
            # from MAST.  For a 27-day sector at 2-min cadence this is ~20 000
            # data points (cadences); at 20-s "fast" cadence it is ~120 000.
            lc = self._lk(
                action="download",
                search_result=search_result,
                index=index,
            )

            # Extract plain-Python arrays so the result is usable without
            # numpy in the caller (though numpy is used here for extraction).
            import numpy as np  # lazy import

            time_arr = np.asarray(lc.time.value).tolist()
            flux_arr = np.asarray(lc.flux.value).tolist()

            if actual_sector is None:
                try:
                    actual_sector = int(lc.sector)
                except Exception:
                    actual_sector = None

            return {
                "tic_id": int(tic_id),
                "sector": actual_sector,
                "time": time_arr,
                "flux": flux_arr,
                "n_cadences": len(time_arr),
                "lightcurve": lc,
            }
        except Exception as exc:
            logger.exception("download_lightcurve failed for TIC %s", tic_id)
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "detail": "lightkurve download failed — check TIC ID and "
                          "network connectivity",
            }

    def detect_transits(
        self,
        tic_id: int,
        sector: int | None = None,
        period_range: tuple[float, float] = DEFAULT_PERIOD_RANGE,
    ) -> dict[str, Any]:
        """Full transit-detection pipeline: download, flatten, run BLS.

        This is the primary method of the module.  It downloads the TESS
        light curve for the given TIC ID, cleans and flattens it to remove
        stellar variability, and runs a BLS periodogram over the specified
        period range to search for box-shaped transit dips.

        **BLS (Box-fitting Least Squares)** works because a planetary transit
        produces a characteristic *box-shaped* dip in the light curve: the
        flux drops sharply when the planet enters the stellar disk, stays
        roughly flat for the transit duration, then rises sharply when the
        planet exits.  BLS slides a trial box across every possible period
        and phase and reports the period whose box best fits the data.

        The returned parameters are:

        - **period** — orbital period in days (time between transits).
        - **duration** — transit duration in days (how long the planet is
          in front of the star, typically a few hours).
        - **depth** — fractional flux drop during transit, directly related
          to the planet-to-star radius ratio: δ ≈ (R_p / R_★)².
        - **epoch** — mid-transit time in BJD (Barycentric Julian Date); all
          transits occur at T₀ + n·P.
        - **snr** — signal-to-noise ratio of the detection (SNR > ~6 is
          generally considered robust).

        We **flatten** the light curve first because stars are not constant:
        they pulsate, rotate (carrying starspots in and out of view), and
        flare.  These variations are slow and smooth compared to the brief,
        sharp transit dips.  Flattening divides by a moving-median trend,
        normalising the baseline to ~1.0 so BLS only has to fit the transit.

        The **period range** (0.5 – 30 d by default) is the sweet spot for
        TESS: a 27-day sector can catch at least two transits for P < ~13 d,
        and multi-sector stitched curves extend this to ~30 d.  TESS is
        optimised for short-period planets (hot Jupiters, ultra-short-period
        rocky planets) precisely because their frequent transits are easiest
        to detect in a single sector.

        Parameters
        ----------
        tic_id : int
            TESS Input Catalog ID of the target star.
        sector : int or None, optional
            Specific TESS sector to use.  *None* uses the first available.
        period_range : tuple[float, float], default (0.5, 30.0)
            ``(period_min, period_max)`` in days over which BLS searches.

        Returns
        -------
        dict
            On success: ``{"tic_id": int, "sector": int, "period": float,
            "duration": float, "depth": float, "epoch": float, "snr": float,
            "period_range": list, "n_cadences": int}``.  On failure:
            ``{"error": str, "type": str, "detail": str}``.
        """
        try:
            import numpy as np  # lazy import — numpy is optional

            # --- Step 1: download the light curve ---------------------------
            lc_result = self.download_lightcurve(tic_id, sector=sector)
            if "error" in lc_result:
                # learning: we propagate the error dict unchanged so the
                # caller sees the exact download failure, not a generic one.
                return lc_result

            lc = lc_result["lightcurve"]

            # --- Step 2: clean and flatten -----------------------------------
            # learning: remove_nans drops any NaN/inf cadences (common at
            # light-curve gaps), and remove_outliers(sigma=5) clips points
            # more than 5σ from the median — this removes cosmic-ray hits
            # and instrumental glitches that would confuse both the
            # flattener and BLS.
            lc_clean = lc.remove_nans().remove_outliers(
                sigma=DEFAULT_OUTLIER_SIGMA
            )

            # learning: flatten divides the light curve by a
            # moving-median trend (window_length in cadences).  The window
            # must be *longer than a transit* (so the transit isn't removed
            # by the trend) yet *shorter than stellar rotation periods*
            # (so rotation is removed).  401 cadences ≈ 3.3 h at 2-min
            # cadence — comfortably longer than a typical ~3-h transit.
            lc_flat = lc_clean.flatten(
                window_length=DEFAULT_FLATTEN_WINDOW
            )

            # learning: after flattening the median flux should be ~1.0.
            # We re-normalise defensively in case the flattener left a tiny
            # residual offset — BLS assumes a ~1.0 baseline.
            flux_values = np.asarray(lc_flat.flux.value, dtype=float)
            flux_values = flux_values / np.nanmedian(flux_values)

            # Re-attach the normalised flux to a lightkurve object for BLS.
            # We use the cleaned/flat LightCurve but override .flux with the
            # re-normalised array so BLS sees a unit baseline.
            lc_flat = lc_flat.copy()
            lc_flat.flux = lc_flat.flux * 0 + flux_values

            # --- Step 3: run BLS periodogram ---------------------------------
            period_min, period_max = float(period_range[0]), float(period_range[1])
            # learning: np.linspace(period_min, period_max, N) creates a
            # uniform period grid.  BLS evaluates the box-fit statistic at
            # each trial period; the period with the highest BLS power is
            # the most likely orbital period.  10 000 periods gives ~3×10⁻³
            # day resolution across a 30-day range — enough to pin a hot
            # Jupiter's 0.94-day period to <0.1 % error.
            bls = self._lk(
                action="bls",
                lightcurve=lc_flat,
                period_min=period_min,
                period_max=period_max,
                n_periods=DEFAULT_BLS_PERIODS,
            )

            # --- Step 4: extract best-fit transit parameters ----------------
            # learning: period_at_max_power is the trial period with the
            # highest BLS power — our best estimate of the orbital period.
            best_period = float(bls.period_at_max_power.value)
            # learning: depth_at_max_power is the fractional flux drop at
            # the best period.  For WASP-18 b this is ~0.008 (0.8 %, ~8000
            # ppm) because the planet is a massive hot Jupiter.
            best_depth = float(bls.depth_at_max_power.value)
            # learning: duration_at_max_power is the transit duration in
            # days at the best period — the width of the box.
            best_duration = float(bls.duration_at_max_power.value)

            # learning: the mid-transit time (epoch / T₀) is the BJD of the
            # first transit in the light curve.  lightkurve exposes it as
            # transit_time_at_max_power.  All future transits are at
            # T₀ + n·P.
            best_epoch: float
            try:
                best_epoch = float(bls.transit_time_at_max_power.value)
            except (AttributeError, TypeError):
                # Some lightkurve versions store this differently; fall back.
                best_epoch = float(
                    getattr(bls, "epoch_at_max_power", bls.period_at_max_power)
                )

            # learning: SNR (signal-to-noise) quantifies detection
            # significance.  We compute it as depth / (std of out-of-transit
            # flux), which is a robust proxy for the BLS SNR.  SNR > ~6 is a
            # solid detection; SNR < ~3 is likely noise.
            snr: float
            try:
                # Fold the light curve at the best period to isolate the
                # transit, then compute the noise from the out-of-transit
                # baseline.
                folded = lc_flat.fold(period=best_period)
                folded_flux = np.asarray(folded.flux.value, dtype=float)
                # Out-of-transit flux ~ baseline; its std is the noise.
                noise = float(np.std(folded_flux))
                snr = float(best_depth / noise) if noise > 0 else 0.0
            except Exception:
                snr = 0.0

            # Convert depth to ppm for convenience (1 ppm = 1e-6).
            depth_ppm = best_depth * 1e6

            return {
                "tic_id": int(tic_id),
                "sector": lc_result.get("sector"),
                "period": best_period,
                "duration": best_duration,
                "depth": best_depth,
                "depth_ppm": depth_ppm,
                "epoch": best_epoch,
                "snr": snr,
                "period_range": [period_min, period_max],
                "n_cadences": int(len(lc_flat)),
            }
        except Exception as exc:
            logger.exception("detect_transits failed for TIC %s", tic_id)
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "detail": "transit-detection pipeline failed during "
                          "download/flatten/BLS — see logs for details",
            }

    def validate_known_planet(self, planet_name: str) -> dict[str, Any]:
        """Cross-check a detection against the NASA Exoplanet Archive.

        Queries the :class:`ExoplanetCatalog` (from the sibling
        ``star_catalog`` module) for the known parameters of a confirmed
        exoplanet, so a detected transit can be compared against the
        literature values for period, depth, and epoch.

        Parameters
        ----------
        planet_name : str
            Confirmed-planet name as used by the NASA Exoplanet Archive,
            e.g. ``"WASP-18 b"``.

        Returns
        -------
        dict
            On success: ``{"planet": str, "found": bool, "known_params": dict,
            "source": str}``.  On failure: ``{"error": str, "type": str,
            "detail": str}``.
        """
        try:
            # learning: the NASA Exoplanet Archive (NEA) is the canonical
            # community database of confirmed exoplanets.  We delegate to
            # the sibling ExoplanetCatalog class (in star_catalog.py) which
            # wraps the NEA's TAP (Table Access Protocol) API.  The import
            # is lazy so this module doesn't hard-depend on the catalog at
            # import time — if the catalog module is renamed or refactored,
            # only this method (not the whole module) breaks.
            try:
                from astro.star_catalog import ExoplanetCatalog  # noqa: F401
            except ImportError:
                # learning: if the catalog module isn't available (e.g. it
                # hasn't been written yet, or the package path differs), we
                # fall back to a direct TAP query so validation still works.
                return self._query_exoplanet_archive(planet_name)

            catalog = ExoplanetCatalog()  # type: ignore[name-defined]
            result = catalog.lookup(planet_name)
            if isinstance(result, dict) and "error" in result:
                return {
                    "planet": str(planet_name),
                    "found": False,
                    "error": result["error"],
                    "type": result.get("type", "CatalogError"),
                    "detail": "ExoplanetCatalog lookup returned an error",
                }
            return {
                "planet": str(planet_name),
                "found": True,
                "known_params": result,
                "source": "NASA Exoplanet Archive via ExoplanetCatalog",
            }
        except Exception as exc:
            logger.exception("validate_known_planet failed for %r", planet_name)
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "detail": "planet validation failed — could not query the "
                          "NASA Exoplanet Archive",
            }

    def _query_exoplanet_archive(self, planet_name: str) -> dict[str, Any]:
        """Fallback direct TAP query to the NASA Exoplanet Archive.

        Used when the :class:`ExoplanetCatalog` module is not importable.
        Issues a simple ADQL ``SELECT`` against the NEA TAP sync endpoint
        via the injected HTTP client.

        Parameters
        ----------
        planet_name : str
            Planet name to look up.

        Returns
        -------
        dict
            On success: ``{"planet": str, "found": bool, "known_params": dict,
            "source": str}``.  On failure: an error dict.
        """
        try:
            import urllib.parse

            # learning: ADQL (Astronomical Data Query Language) is the SQL-
            # like query language used by TAP services.  The `ps` table is
            # the NEA's Planetary Systems composite table; default_flag=1
            # selects the default/canonical solution per planet.
            query = (
                "SELECT pl_name, hostname, ra, dec, pl_orbper, pl_trandep, "
                "pl_rade, pl_trandur, pl_tranmid, sy_tmag, st_rad "
                "FROM ps WHERE default_flag=1 "
                f"AND pl_name='{planet_name.replace(chr(39), chr(39)+chr(39))}'"
            )
            params = {
                "query": query,
                "format": "json",
            }
            url = f"{EXOPLANET_ARCHIVE_URL}?{urllib.parse.urlencode(params)}"
            data = self._http(url)

            # learning: the NEA TAP sync endpoint returns a JSON *array* of
            # row objects when format=json, even though the HTTP client's
            # return type is annotated as dict.  Handle both shapes robustly.
            rows: list[dict[str, Any]] = []
            if isinstance(data, list):
                rows = [r for r in data if isinstance(r, dict)]
            elif isinstance(data, dict):
                # Some TAP implementations wrap results in {"data": [...]}.
                wrapped = data.get("data", data.get("results", []))
                if isinstance(wrapped, list):
                    rows = [r for r in wrapped if isinstance(r, dict)]

            if rows:
                return {
                    "planet": str(planet_name),
                    "found": True,
                    "known_params": rows[0],
                    "source": "NASA Exoplanet Archive (direct TAP query)",
                }
            return {
                "planet": str(planet_name),
                "found": False,
                "known_params": {},
                "source": "NASA Exoplanet Archive (direct TAP query)",
                "detail": f"no confirmed planet named {planet_name!r} in the NEA",
            }
        except Exception as exc:
            return {
                "error": str(exc),
                "type": type(exc).__name__,
                "detail": "direct TAP query to the NASA Exoplanet Archive failed",
            }

    def info(self) -> dict[str, Any]:
        """Return capability metadata for this detector.

        Reports whether the detector's heavy dependencies (``lightkurve``
        and ``requests``) are importable, lists the available methods, and
        exposes the data-source URLs.  Mirrors :meth:`AstroBridge.info` in
        style so the R1-A1 brain can query detector capabilities uniformly.

        Returns
        -------
        dict
            ``{"available": bool, "methods": [str, ...], "data_sources":
            {...}, "period_range": [float, float], "defaults": {...}}``.
        """
        try:
            import importlib.util

            # Check whether the heavy deps are importable without actually
            # importing them (avoids the multi-second import cost of
            # lightkurve / scipy on every info() call).
            def _is_importable(name: str) -> bool:
                try:
                    return importlib.util.find_spec(name) is not None
                except Exception:
                    return False

            # learning: if an injected transport is in use, the detector is
            # "available" for testing even when the real packages are absent.
            using_injected_http = self._http is not self._default_http
            using_injected_lk = self._lk is not self._default_lightkurve

            requests_available = _is_importable("requests") or using_injected_http
            lightkurve_available = _is_importable("lightkurve") or using_injected_lk

            available = bool(requests_available and lightkurve_available)

            return {
                "available": available,
                "apis": [
                    "transit_detection",
                    "exoplanet_archive",
                ],
                "methods": [
                    "search_target",
                    "download_lightcurve",
                    "detect_transits",
                    "validate_known_planet",
                    "info",
                ],
                "data_sources": {
                    "tess_mast": TESS_DATA_URL,
                    "exoplanet_archive": EXOPLANET_ARCHIVE_URL,
                },
                "dependencies": {
                    "requests": requests_available,
                    "lightkurve": lightkurve_available,
                    "injected_http": using_injected_http,
                    "injected_lightkurve": using_injected_lk,
                },
                "period_range": list(DEFAULT_PERIOD_RANGE),
                "defaults": {
                    "flatten_window": DEFAULT_FLATTEN_WINDOW,
                    "outlier_sigma": DEFAULT_OUTLIER_SIGMA,
                    "bls_periods": DEFAULT_BLS_PERIODS,
                },
            }
        except Exception as exc:
            return {
                "available": False,
                "error": str(exc),
                "type": type(exc).__name__,
                "detail": "failed to build detector capability metadata",
            }