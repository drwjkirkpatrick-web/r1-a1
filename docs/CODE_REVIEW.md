# R1-A1 Code Review

Deep review of `src/` (16 packages), `firmware/`, `src/cli.py`, and `tests/`.
Baseline at review time: **586 tests, all passing** (`pytest -q`, ~3.3 s).
Findings were verified by reading the code and, where marked *(verified)*, by
executing the path in a Python session. Severity classes: **bug**,
**inconsistency**, **style**, **opportunity**; safety-relevant items are
flagged ⚠.

> Note: the working tree was under active edit during this review (the four
> known findings from the prior partial review were fixed mid-session; see
> §1). Line numbers refer to the tree as of the final pass.

---

## 1. Prior known findings — verification

| Finding | Status |
|---|---|
| `RepairProcedure.execute()` double-append on re-run | **Fixed** — `src/repair/diagnostics.py:319` now early-returns when `self.completed` (verified: two runs leave `completed_steps == steps_total`). |
| Stale "weapons / shielding" docstring in `from_subsystem` | **Fixed** — docstring now names `propulsion`/`thermal_protection` (hard) and `hull`/`payload`/`life_support` (moderate), matching the code at `src/repair/diagnostics.py:370-371`. |
| Unused `typing.Optional` import in `repair/diagnostics.py` | **Fixed** — import removed. |
| `_TOOLSETS["communications"]` vs registry categories | **Not a bug** — `SUBSYSTEM_CATEGORIES` (`src/repair/registry.py:35-47`) has 9 categories including `"communications"`, so the `_TOOLSETS` key is valid. However see F15: `tools/tool.py` did not get the same update. |

---

## 2. Bugs

### F1 ⚠ — Firmware/host e-stop payload key mismatch
**bug — `firmware/r1a1_mcu.ino:259-261` vs `src/interconnect/link.py:229` and `src/interconnect/selftest.py:50-52`**
The MCU replies to `estop_sense` with `{"estopped": bool}`, but the host reads
`payload.get("estop", True)`. The key never matches, so `SerialLink.estop_sense()`
*always* reports estopped=True, and the selftest's coherence check
(`isinstance(payload.get("estop"), bool)`) always fails against real firmware.
**Fix:** pick one key (`"estop"` matches the host) and use it in both the
`estop_sense` reply and the unsolicited `estop_event` frame (`.ino:368-369`).

### F2 ⚠ — Firmware CRC parse truncates 50 % of valid frames
**bug — `firmware/r1a1_mcu.ino:121-129, 237, 247`**
`json_get_int` uses `strtol` (signed 32-bit `long` on the Teensy's ARM core)
to parse the CRC. CRC-32 values ≥ 2³¹ (half of all frames, statistically)
clamp to `LONG_MAX`, so `(uint32_t)crc != expect` and the frame is rejected
with `{"reason":"crc"}`. On the bench this looks like a flaky link that drops
every other command.
**Fix:** parse the CRC with `strtoul` into a `uint32_t` (add a
`json_get_uint` helper); keep `strtol` for `seq`.

### F3 ⚠ — Wink effector channel map disagrees with firmware
**bug — `src/eye/wink.py:18-19` vs `firmware/r1a1_mcu.ino:297-309`**
`wink.py` sends eye-LED PWM on channel **2** and the shutter servo on channel
**3**. The firmware drives the eye LED only on PWM channel **1**, and maps
servo channel 2 → `SERVO_0` (shutter), anything else → `SERVO_1` (gimbal pan).
As written, a wink never lights the LED and cycles the *gimbal pan* servo
instead of the shutter. The firmware pin-map comment (`.ino:23-25`: LED ch1,
shutter ch2, pan ch3) is the authoritative side.
**Fix:** set `EYE_LED_PWM_CHANNEL = 1` and `SHUTTER_SERVO_CHANNEL = 2` in
`wink.py`, and document the channel map in one shared place.

### F4 ⚠ — `drive.rotate 0` spins the motors forever (firmware)
**bug — `firmware/r1a1_mcu.ino:275-280`**
`degrees > 0 ? pwm : -pwm` treats `degrees == 0` as negative: a zero-degree
rotate applies ±120 PWM open-loop with no stop condition. The host's
`Drive.rotate(0)` is a plausible no-op call (e.g. from
`follow_target` bearing correction) that would leave the base turning in
place until an explicit stop.
**Fix:** early-return (ack without actuating) when `degrees == 0` — and,
longer term, the open-loop forward/rotate TODOs need a duration or
closed-loop stop.

### F5 ⚠ — `SafetyController`: hazards that fall below their threshold can never clear
**bug — `src/safety/response.py:139-140, 176-178, 244-246`** *(verified)*
`evaluate()` skips (does not register/update) hazards below their configured
threshold. `clear()` requires the *tracked* hazard's current severity to be
≥ `CLEAR_HYSTERESIS` below peak — but the tracked severity is only updated
when the hazard is above threshold. So: smoke peaks at 9 (threshold 4), then
drops to 2 → `evaluate()` ignores it, the registry entry stays at severity 9,
and `clear()` refuses forever. The hazard latches in `status_report()` and
keeps `interlock()` blocking subsystems with no recovery path short of
re-instantiating the controller.
**Fix:** register every evaluated hazard (even below threshold, so the
tracked severity refreshes), or let `clear()` accept a fresh reading /
auto-expunge entries whose last evaluation was below threshold.

### F6 — `MovementRefiner` detour re-tests the original heading, not the opposite side
**bug — `src/motion/refine.py:56-65`**
The detour loop rotates `+30°`, checks, then rotates `−30°` — landing back on
the *original* heading — and checks again. The `−30°` detour direction is
never actually probed (to try it the code would need to rotate `−60°` from
the `+30°` position). The comment says "one detour attempt each way"; only
one way plus the (already-known-blocked) original ray is tried — the second
check only ever passes because of confidence decay, not because a clear
direction was found.
**Fix:** rotate `sign * DETOUR_DEG` relative to the *original* heading each
iteration (e.g. `self._drive.rotate(sign * DETOUR_DEG - (sign_prev * DETOUR_DEG if detoured_attempt else 0))`
or rotate back to center between attempts).

### F7 ⚠ — Grid/refine boundary: forward commands ≥ 2.0 m are always refused
**bug — `src/awareness/occupancy.py:72-77` + `src/motion/refine.py:51`**
The 40×40 grid at 0.1 m/cell spans ±2.0 m. `is_cell_blocked` returns True for
any cell outside the grid ("unknown = blocked"), and `raycast_clear` walks to
`max(0.5, meters)`. Any `refined_forward(meters ≥ 2.0)` therefore raycasts
into out-of-grid cells, is judged blocked, fails both detours, and stops.
The module docstring's "covers a 4 m bubble" (`occupancy.py:3`) is also
misleading — 4 m is the *diameter*; the usable radius is 2 m.
**Fix:** treat out-of-grid ray points as "unknown but not blocking" for the
clear test (or clamp the ray at the grid edge and report the limit), and fix
the docstring to "2 m radius / 4 m across".

### F8 — `BondEngine` decay is cosmetic: one interaction undoes all neglect
**bug — `src/loyalty/bond.py:117-120, 131-138`** *(verified)*
`score()` subtracts decay from the stored score on read, but decay is never
written back. `record_interaction` then adds points to the *stale* stored
score: 50 points, 40 days of silence (effective 10), one +2 interaction →
score jumps to 52, not ~12. The module narrative ("days of silence erode the
score… slides back down the ladder one level at a time") only holds until the
next interaction.
**Fix:** in `record_interaction`, first persist the decayed effective score
(`entry["score"] = self.score(operator_id)`) before adding points.

### F9 — `SolarSystem` "Sun" position is 180° off
**bug — `src/astro/solar_system.py:212-224`** *(verified numerically)*
The Sun entry reuses Earth's orbital elements, so the pipeline computes
Earth's *heliocentric* position. At J2000 the code returns RA 6.75 h / Dec
+23.0°; the true geocentric Sun was RA ≈ 18.75 h / Dec ≈ −23.0° — the exact
antipode (`Sun` and `Earth` return identical positions). A dome aimed with
this points away from the Sun. The docstring's claim that the elements
"mirror Earth's heliocentric orbit" is only half the transform — the
geocentric Sun needs the +180° flip.
**Fix:** add π to the computed ecliptic longitude (or negate x/y) for the
Sun entry before the ecliptic→equatorial rotation.

### F10 — `validate_known_planet` imports `ExoplanetCatalog` from the wrong module
**bug — `src/astro/exoplanet.py:713`** *(verified)*
`from astro.star_catalog import ExoplanetCatalog` always raises ImportError
(the class lives in `astro/exoplanet_catalog.py`), so the catalog path is
dead code and every call silently falls back to the direct TAP query. The
docstring at line 686-688 ("from the sibling star_catalog module") repeats
the wrong location.
**Fix:** `from .exoplanet_catalog import ExoplanetCatalog` (relative import
also fixes the absolute-`astro.` path assumption).

### F11 — Star catalog: Mira's RA is out of range (34.83 h)
**bug — `src/astro/star_catalog.py:213`** *(verified)*
Mira is stored with `ra_hours=34.83` — outside the documented 0–24 h range
(34.83 is the RA in *degrees*; ÷15 → ≈ 2.32 h). Position searches near Mira
silently never match it, and any consumer that validates ranges will choke.
**Fix:** set `ra_hours: 2.32`.

### F12 — Star catalog count and ordering contradict the docstrings
**bug/inconsistency — `src/astro/star_catalog.py:3, 61-63, 71-73`** *(verified)*
The module docstring and the `count()` doctest claim **60** stars; the list
has **58**. The class comment also claims the list is "ordered by descending
brightness" — it is not (e.g. Fomalhaut 1.16, Acrux 0.77, Rigil Kentaurus
−0.27 sit at the end). `brightest()` sorts defensively so behavior is right,
but the documented invariant is false.
**Fix:** correct the count (or add two stars), and either sort the literal by
magnitude or drop the ordering claim.

### F13 — `cli.py config` resolves the config path one directory too high
**bug — `src/cli.py:145-148`** *(verified)*
Three `dirname()` calls from `src/cli.py` land at the *parent of the project
root* (`/home/walker/projects/config/r1a1.yaml`), so `r1a1 config` always
reports "not found". Two `dirname()` calls is correct.
**Fix:** drop one `os.path.dirname`, or build from
`Path(__file__).resolve().parents[1]`.

### F14 — `doctor()` exit code ignores FAIL statuses
**bug — `src/cli.py:32-40`**
`ok` is only cleared when a check *raises*; a check returning a `"FAIL …"`
string (e.g. `_check_interconnect` on an import error) still yields exit 0.
**Fix:** treat statuses starting with `"FAIL"`/`"ERROR"` as failures when
computing the return code.

### F15 ⚠ — `tools.VALID_SUBSYSTEMS` missing `"communications"`
**inconsistency — `src/tools/tool.py:34-43` vs `src/repair/registry.py:35-47`**
The repair registry has 9 categories; the tool bay validates against 8
(no `"communications"`). No tool can service a comms subsystem and
`ToolBay.select_tool("communications")` raises `ValueError` — the exact
"mismatched category lists" class of bug the prior review hunted. Two module-
level copies of the category list (`registry.SUBSYSTEM_CATEGORIES`,
`tools.tool.VALID_SUBSYSTEMS`) guarantee future drift.
**Fix:** single-source the list (import `SUBSYSTEM_CATEGORIES` from
`repair.registry`, or move it to a shared constants module) and add comms
tools.

### F16 — `SerialLink.roundtrip`/recv accept any frame as "the reply"
**bug — `src/interconnect/link.py:194-216`**
`roundtrip()` returns the first CRC-valid frame received, with no check that
`cmd`/`seq` match the request. The firmware emits unsolicited `heartbeat`
frames every second and unsolicited `estop_event` frames on transitions
(`.ino:363-378`), so a roundtrip can consume a heartbeat and report it as the
command's reply (and `heartbeat()` counts any buffered frame as liveness).
The retry path re-sends with a new seq, making stale-reply confusion worse.
**Fix:** match replies by `cmd` (and ideally `seq`); buffer or drop
unsolicited frames explicitly (e.g. treat `heartbeat`/`estop_event` cmd
values as telemetry, not replies).

### F17 ⚠ — `Drive.estop_soft` does not latch if `link.send` raises
**bug ⚠ — `src/motion/drive.py:87-94`**
The docstring promises "Latches estop_latched **regardless of outcome**", but
if `link.send()` raises (dead serial), the latch is never set and the raw
exception propagates — motion commands remain unblocked after a failed
e-stop. On a 38 kg robot, a failed e-stop must fail *closed*.
**Fix:** wrap in try/finally (`finally: self.estop_latched = True`) and
re-raise as `EstopTimeoutError`/a send-failure error.

### F18 — Thermal fan check boundary contradicts its own constant comment
**bug — `src/thermal/monitor.py:26, 136`**
`MIN_FAN_RPM = 1  # tach reading at or below this counts as a stalled/dead fan`
but the check is `ok = rpm >= MIN_FAN_RPM`, so rpm == 1 counts as OK.
**Fix:** `rpm > MIN_FAN_RPM` (or change the comment/constant to
`MIN_HEALTHY_FAN_RPM = 2`).

### F19 — Thermal host-rate pairs ΔT from one interval with Δt from another
**bug — `src/thermal/monitor.py:90-113`**
`host_rate_c_per_s()` computes `(prev − prev2) / (last_ts − prev_ts)` — the
temperature delta of the older interval divided by the time delta of the
newer one. With uniform polling it's fine; with jittered sampling the rate is
wrong. (The newest sample's temperature is never stored, which forces this.)
**Fix:** keep `(temp, ts)` pairs and compute the rate across one consistent
pair.

### F20 — `PowerMonitor.telemetry()` reads the sensor twice per call
**bug — `src/power/monitor.py:49-57`**
`telemetry()` calls `_raw()`, then `self.soc()`, which calls `_raw()` again —
two sensor reads whose values can disagree (the returned dict mixes fields
from the first read with `soc_pct` from the second).
**Fix:** compute `soc` from the single `_raw()` result already in hand.

### F21 — `Memory.save()` crashes on a bare filename persist path
**bug — `src/brain/memory.py:70`**
`os.makedirs(os.path.dirname(self.persist_path))` raises `FileNotFoundError`
when `persist_path` has no directory component (e.g. `"memory.json"` →
`dirname == ""`).
**Fix:** `os.makedirs(dir, exist_ok=True)` only when `dir` is non-empty.

### F22 — Projector cooldown timer races with lamp relight
**bug (race) ⚠ — `src/projector/beam.py:59-80`**
`_cooldown_done()` runs on the `threading.Timer` thread: if `on()` executes
concurrently with the timer firing, `cancel()` can lose the race and
`_cooldown_done` then calls `fan_fn(False)` *after* `on()` re-enabled the fan
— lamp lit, fan off, on a projector whose whole policy is thermal protection.
**Fix:** guard with a lock, or use a monotonic `cooldown_until` timestamp
checked in `on()`/a tick method instead of a callback thread.

### F23 — `requirements.txt` extras markers never install optional deps
**bug — `requirements.txt:4-6`**
`flask>=3.0; extra == "dashboard"` is not valid in a plain requirements file —
the `extra` marker is only defined in package metadata, so pip skips those
lines entirely. `pip install -r requirements.txt` never installs Flask,
lightkurve, or numpy.
**Fix:** move optional deps to `pyproject.toml` `[project.optional-dependencies]`,
or split into `requirements-dashboard.txt` / `requirements-exoplanet.txt`.

---

## 3. Inconsistencies

### F24 — `cliff.safest_turn` docstring disagrees with code for "rear"
**inconsistency — `src/awareness/cliff.py:48-50, 55-56`**
Docstring: rear tripped → "we pick 'left' (arbitrary but consistent)".
Code: rear → `'back'`. (Code behavior is arguably better; fix the docstring.)

### F25 — Proximity "caution" zone reported as "slow zone"
**inconsistency — `src/awareness/proximity.py:36-37, 50-51`**
Distances in [1.0, 2.0) m map to factor 0.6 (the "caution" band in the
docstring table) but the reason string says "slow zone" for every factor < 1.0.
**Fix:** label 0.6 as "caution zone".

### F26 — Watchdog documents `estop_sense` but never uses it
**inconsistency ⚠ — `src/awareness/watchdog.py:33-37, 51-53` vs `tick()` 123-170**
The docstring says the link must provide `estop_sense(timeout)`; `tick()`
only calls `heartbeat()`. The physical e-stop loop state is never polled by
the supervisor, so software never learns the mushroom was pressed (the MCU
kills motion locally, but the host keeps planning motion).
**Fix:** poll `estop_sense` in `tick()` and treat True/unreadable as
estop-requiring; or trim the docstring contract.

### F27 — `MovementRefiner` API: drive is both injected and passed per-call
**inconsistency — `src/motion/refine.py:29-34, 76-77`**
`refined_forward` uses `self._drive`; `follow_target` takes a separate
`drive` argument. Two sources of truth for the same actuator.
**Fix:** drop the parameter and use `self._drive` everywhere.

### F28 — `follow_target` bypasses the proximity/cliff policy
**inconsistency ⚠ — `src/motion/refine.py:76-101`**
The pursuit step rotates/advances purely from mmWave geometry — no
`ProximityPolicy` advice, no cliff check, no raycast — while
`refined_forward` (same module) enforces all three. Following a human toward
a staircase drives blind.
**Fix:** route the final advance through the same policy gate.

### F29 — `MissionQueue.tick` docstring overstates what it does
**inconsistency — `src/missions/queue.py:89-98`**
"Record that a mission COMPLETE'd" — the method never transitions the named
mission; it only validates existence and sweeps. A caller reading the
docstring will expect `tick("m1")` to complete `m1`.
**Fix:** rename/document as "sweep after the caller has transitioned the
mission", or accept a status argument.

### F30 — Dependency on a CANCELLED/unknown mission blocks forever
**inconsistency — `src/missions/queue.py:135-161`**
`_sweep` cascades on FAILED deps and unblocks on COMPLETE deps, but a
CANCELLED dependency (terminal, never COMPLETE, never FAILED) leaves
dependents BLOCKED for eternity; a `depends_on` id that was never added does
the same, silently.
**Fix:** cascade CANCELLED to dependents (fail or cancel them), and validate
`depends_on` references at `add()` time.

### F31 — Dashboard: `POWER_LOW_PCT`/`POWER_CRITICAL_PCT` defined but unused; JS hardcodes 40/20
**inconsistency — `src/dashboard/server.py:42-44, 311-317`**
The Python constants "mirror config/r1a1.yaml" but are never referenced;
thresholds live as literals in the embedded JS. Also `get_state()` includes a
`comms` section the HTML never renders (dead data).
**Fix:** either render server-side values or delete the constants; add a
comms card or drop the collector.

### F32 — Dashboard limbic collector reads the wrong API shape
**inconsistency — `src/dashboard/server.py:923-963` vs `src/brain/limbic.py:242-281`**
The collector calls `get_state()` and looks for top-level `valence`/
`arousal`/`dominance`, but `LimbicBridge.get_state()` nests those under
`vad`; the flat six-field snapshot the dashboard wants is exactly what
`get_affect_summary()` exists for. Against a live bridge the VAD bars show
zeros.
**Fix:** prefer `get_affect_summary()` when present, fall back to `get_state()`
+ `vad` nesting.

### F33 — Test files use three different import bootstrap conventions
**inconsistency — `tests/*.py`**
Some insert `../src` into `sys.path`, some insert the project root, and
`pytest.ini` already sets `pythonpath = .` (making both redundant);
`src/motion/refine.py:20-23` carries a try/except import fallback purely to
tolerate this. Pick one layout (prefer `pythonpath = . src` in pytest.ini)
and delete the per-file shims and the fallback import.

### F34 — Duplicated constants across modules
**inconsistency**
- `SECONDS_PER_DAY` in `src/missions/mission.py:38` and `src/loyalty/bond.py:34`.
- The navigational-star table exists twice in `src/astro/navigation.py`
  (`_NAVIGATIONAL_STARS` at :94-107 and the literal inside `constellations()`
  at :410-423).
- Three near-identical haversine implementations: `navigation.py:357-398`,
  `star_catalog.py:272-315`, `exoplanet_catalog.py:269-314`.
**Fix:** hoist shared constants and the haversine into one module
(e.g. `astro/_math.py`); `constellations()` should copy from
`_NAVIGATIONAL_STARS`.

### F35 — Clock injection convention broken in a few places
**inconsistency — `src/audio/speaker.py:63,71`, `src/interconnect/link.py:144,161`, `src/motion/express.py`**
Most of the codebase injects `clock`/`sleeper` for deterministic tests;
`Speaker.mute_until/is_muted` call `time.monotonic()` directly, and
`SerialLink.recv` uses `time.monotonic()` directly (the sleeper is injected
but the clock is not).
**Fix:** inject clocks consistently.

---

## 4. Style / dead code

- **S1** `src/repair/diagnostics.py:192-194` — `report()` branch for
  `sub["subsystem"] is None` is unreachable (`run_all_checks` only iterates
  existing subsystems).
- **S2** `src/quirks/registry.py:92` — `int(self._draw() * len(candidates)) % len(candidates)`:
  the `%` is dead (draw < 1.0 guarantees the int is already in range).
- **S3** `src/brain/llm_client.py:46-52` — `_requests_http_client` is legacy
  dead code; `server_alive` also bypasses the injected `http_client` and
  imports `requests` directly (:102-115), so the transport isn't mockable and
  a stdlib-only install can't probe.
- **S4** `src/motion/center_leg.py:43-52` — `drive_guard` docstring narrates a
  rejected design ("Returns the drive … is NOT supported"); trim to the actual
  contract.
- **S5** `src/motion/express.py:21-32` — `wiggle` docstring says each *pair*
  returns to heading; an odd `pulses` count leaves a +5° residual. Validate
  even counts or restore heading at the end.
- **S6** `src/motion/drive.py:50-56` — `forward` docstring says speed is
  "0.0-1.0 normalized" but only `speed <= 0` is rejected; no upper bound and
  no `meters` validation (negative meters drives backward while the command
  is named `forward`). Clamp or validate.
- **S7** `src/brain/agent.py:124-132` — prompt assembly builds `full_prompt`
  twice when both prefix and context exist; correct but redundant — compose
  once.
- **S8** `src/eye/camera.py:79-90` — `ambient_lux` docstring says "lux scales
  with `gain / exposure`"; the code computes `(ref/exposure) / gain`
  (inverse gain). Fix the docstring. Missing-key access (`tele["exposure_us"]`)
  also raises bare `KeyError` instead of a wrapped error.
- **S9** `src/eye/wink.py:43-46` — `wink(count=1.5)` raises a raw `TypeError`
  from `range()`; validate int.
- **S10** `src/astro/exoplanet.py:552-555, 662-673` — `detect_transits` return
  dict includes `depth_ppm`, which the docstring's key list omits.
- **S11** `src/awareness/mmwave.py:79-81` — `human_present()` re-polls the
  hardware instead of reusing a `scan()` result, so it can disagree with a
  scan from the same cycle; and `track()` (:92-105) silently uses only the
  first sensor that reports a given id.
- **S12** `src/awareness/fusion.py:54-57` — fresh marks are decayed in the
  same cycle (update → decay), so a brand-new hit starts at 0.81/1.0
  confidence. Harmless but surprising; consider decaying before marking.
- **S13** `src/awareness/ultrasonic.py:33-38` — a 0.0/no-echo reading clamps
  to 0.02 m, i.e. "nothing detected" becomes "obstacle at 2 cm" (fail-safe
  but causes phantom stops). Distinguish no-echo from a real close reading.
- **S14** `src/quirks/quirk.py:95-103` — `Quirk.age_days()` sets the *droid's*
  age, not the quirk's age-since-acquisition; the name invites misuse.
- **S15** `src/missions/mission.py:102,137-143` — `priority=True` passes the
  int check (bool is int); `progress_pct` returns 0.0 for step-less missions
  even when COMPLETE, skewing `progress_report` averages.
- **S16** `src/repair/registry.py:173-175` — duplicate subsystem names in the
  constructor silently overwrite earlier entries in `_by_name` while both
  stay in `subsystems` — the two views diverge. Validate uniqueness.

---

## 5. Security / safety notes (physical robot)

1. **E-stop chain integrity** — F1, F2, F17, F26 are the findings that matter
   most: the soft e-stop path (host → MCU) and the sense path (MCU → host)
   each have a hole. Recommend an integration test that runs `run_selftest`
   against a firmware-simulator asserting key/schema agreement (the
   `estop`/`estopped` mismatch would have been caught immediately).
2. **Unvalidated motion magnitude** — `Drive.forward` accepts any speed
   (S6); firmware clamps `speed` to [0,1] but host-side validation is the
   documented contract and should agree.
3. **Dashboard XSS surface** — `src/dashboard/server.py` inserts
   remedy/description/node strings into `innerHTML` unescaped. Localhost-only
   by default, but binding to `0.0.0.0` is one config change away. Escape or
   use `textContent` builders.
4. **ADQL/LIKE escaping** — `exoplanet_catalog` doubles single quotes
   (good) but does not escape `%`/`_` wildcards in name/host/factory LIKE
   queries (:748, :801, :1076); a name containing `%` silently becomes a
   wildcard. Low risk (read-only API) but easy to fix.
5. **`_check_brain` in doctor** — `src/cli.py:51-53` constructs
   `LLMClient()` with no injected client, which imports `requests` at
   construction; on a stdlib-only install `doctor` reports brain ERROR
   (caught, but marks the run failed for an optional dependency).
6. **Thermal fail-open for missing battery reader** —
   `src/thermal/monitor.py:119-120` returns 0.0 °C when no battery reader is
   wired, so the 50 °C full-stop can never trip on an unwired probe. Consider
   a distinct "sensor absent" flag rather than a benign-looking 0.0.

---

## 6. Improvement opportunities (ranked by value)

1. **Protocol contract tests between host and firmware** (catches F1–F4,
   F16 class): one schema — commands, payload keys, CRC semantics — shared by
   `link.py`, a firmware simulator, and the `.ino` comments. Highest value
   per line written; the current bugs are all cross-boundary.
2. **SafetyController lifecycle redesign** (F5): below-threshold evaluations
   must still refresh tracked state; add auto-expiry. Add tests for the
   peak→drop→clear path with custom thresholds.
3. **Single-source the subsystem category list** (F15) and shared constants
   (F34). Removes a whole class of drift bugs.
4. **Refiner/grid contract** (F6, F7): make the grid radius an explicit
   parameter of `MovementRefiner`, test detour direction selection and the
   >2 m command path.
5. **E-stop latching hardening** (F17, F26): `try/finally` latch; watchdog
   polls `estop_sense`. Add tests simulating `link.send` raising.
6. **Bond decay persistence** (F8): one-line fix, plus a regression test for
   neglect-then-interact.
7. **Untested/weakly tested paths worth tests**: `cli.py` (`main` dispatch,
   `_show_config`, `_selftest` — note `_selftest` reads real `sys.argv[2]`
   instead of the injected `argv` at `cli.py:189-190`), firmware edge cases
   via a simulator, `Memory.save` with a bare filename (F21), odd-count
   `wiggle` (S5), thermal rate under irregular sampling (F19).
8. **Threading model documentation** (F22, dashboard collectors poll
   agent-attached monitors from Flask threads while a control loop mutates
   them): document which objects are single-threaded-by-contract, add locks
   where sharing is intended.
9. **Naming/UX consistency**: `Quirk.age_days` (S14), `Drive.forward` speed
   units (S6), mission `tick` (F29).
10. **Cleanup pass**: dead code (S1–S3), duplicated haversine (F34),
    redundant modulo (S2), redundant prompt assembly (S7).

---

## 7. Summary

| Severity | Count |
|---|---|
| bug (incl. ⚠ safety-relevant) | 19 (F1–F14, F16–F23; 8 flagged ⚠) |
| inconsistency | 12 (F15, F24–F34) |
| style / dead code | 16 (S1–S16) |
| security/safety notes | 6 (§5) |
| opportunities | 10 (§6) |

**Total: 57 findings** (plus 4 prior findings verified fixed, §1).

The codebase is unusually well-documented and test-backed for a hobby robot;
the systemic weaknesses are (a) the host↔firmware protocol boundary, which
has no shared schema and is where every critical bug lives, and (b) category/
constant lists duplicated across modules that have already drifted once.
