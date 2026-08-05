"""Flask dashboard server for the R1-A1 astromech robot.

Serves a dark-themed web UI at ``http://host:port/`` showing live
subsystem status: brain/LLM model, host type, thermal zones, power
state, personality overlay, and limbic affective state (VAD bars,
dominant affect, allostatic load).

Flask is an *optional* dependency — this module imports fine without
it; the Flask app is only created (and Flask imported) when ``run()``
is called.  This lets the dashboard package be imported on minimal
installs or in CI where Flask is not installed.
"""

from __future__ import annotations

import os
import sys
import time
import threading
import platform
from typing import Any, Optional

# ─── Deferred Flask import (requirement #7) ──────────────────────────
# Learning: try/except at module scope lets ``import dashboard`` succeed
# even when Flask is not installed.  The real import happens inside
# _create_app(), so only ``run()`` requires Flask to be present.
_FLASK_AVAILABLE = False
try:
    import flask  # noqa: F401
    _FLASK_AVAILABLE = True
except ImportError:
    pass


# ─── Constants ───────────────────────────────────────────────────────

ROBOT_NAME = "R1-A1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9298
REFRESH_INTERVAL_MS = 2000

# Power status thresholds (mirror power.monitor + config/r1a1.yaml)
POWER_LOW_PCT = 40.0
POWER_CRITICAL_PCT = 20.0


# ─── HTML Template (requirement #10) ──────────────────────────────────

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>R1-A1 Dashboard</title>
  <style>
    :root {
      --bg:        #0d1117;
      --card-bg:   #161b22;
      --border:    #30363d;
      --text:      #c9d1d9;
      --text-dim:  #8b949e;
      --text-hi:   #f0f6fc;
      --green:     #3fb950;
      --yellow:    #d29922;
      --red:       #f85149;
      --accent:    #58a6ff;
      --accent2:   #bc8cff;
      --mono:      'SF Mono','Fira Code','JetBrains Mono','Cascadia Code',
                   'Consolas','Courier New',monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--mono);
      font-size: 14px;
      padding: 1rem;
      max-width: 920px;
      margin: 0 auto;
    }
    /* ── Header ── */
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.5rem 0 0.75rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 1rem;
    }
    .title { display: flex; align-items: baseline; gap: 0.5rem; }
    .robot-name { font-size: 1.5rem; font-weight: bold; color: var(--text-hi); }
    .version { font-size: 0.8rem; color: var(--text-dim); }
    .status { display: flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; }
    .uptime { color: var(--text-dim); margin-left: 0.5rem; }
    /* ── Status dots ── */
    .dot {
      display: inline-block;
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--text-dim);
      flex-shrink: 0;
    }
    .dot.green  { background: var(--green);  box-shadow: 0 0 6px var(--green); }
    .dot.yellow { background: var(--yellow); box-shadow: 0 0 6px var(--yellow); }
    .dot.red    { background: var(--red);    box-shadow: 0 0 6px var(--red); }
    .dot.gray   { background: var(--text-dim); }
    /* ── Card grid ── */
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.9rem;
    }
    .card h2 {
      font-size: 0.7rem;
      letter-spacing: 0.12em;
      color: var(--accent);
      margin-bottom: 0.6rem;
      padding-bottom: 0.4rem;
      border-bottom: 1px solid var(--border);
      text-transform: uppercase;
    }
    .card-body { font-size: 0.82rem; line-height: 1.65; }
    .data-row {
      display: flex;
      justify-content: space-between;
      padding: 0.1rem 0;
    }
    .data-label { color: var(--text-dim); }
    .data-value { color: var(--text-hi); }
    .status-indicator {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      margin-top: 0.5rem;
      padding-top: 0.4rem;
      border-top: 1px solid var(--border);
      font-size: 0.78rem;
    }
    .unavailable { color: var(--text-dim); font-style: italic; }
    /* ── VAD bar visualization ── */
    .vad-container {
      display: flex;
      gap: 1rem;
      align-items: flex-end;
      margin: 0.4rem 0 0.6rem;
    }
    .vad-group {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.2rem;
    }
    .vad-label { font-size: 0.65rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }
    .vad-value { font-size: 0.72rem; color: var(--text-hi); font-variant-numeric: tabular-nums; }
    /* Valence: horizontal diverging bar (center origin) */
    .vad-valence {
      position: relative;
      width: 160px;
      height: 20px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      border-radius: 4px;
      overflow: hidden;
    }
    .vad-valence-center {
      position: absolute;
      left: 50%; top: 0; bottom: 0;
      width: 1px;
      background: var(--text-dim);
      z-index: 1;
    }
    .vad-valence-bar {
      position: absolute;
      top: 2px; bottom: 2px;
      border-radius: 2px;
      transition: all 0.3s ease;
      z-index: 0;
    }
    /* Arousal & Dominance: vertical bars (bottom origin) */
    .vad-vert {
      position: relative;
      width: 28px;
      height: 80px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      border-radius: 4px;
      overflow: hidden;
    }
    .vad-vert-fill {
      position: absolute;
      bottom: 0; left: 0; right: 0;
      border-radius: 2px 2px 0 0;
      transition: height 0.3s ease;
    }
    /* ── Footer ── */
    footer {
      margin-top: 1rem;
      padding-top: 0.5rem;
      border-top: 1px solid var(--border);
      color: var(--text-dim);
      font-size: 0.72rem;
      text-align: center;
    }
    @media (max-width: 600px) {
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header class='topbar'>
    <div class='title'>
      <span class='robot-name'>R1-A1</span>
      <span class='version' id='version'>v?</span>
    </div>
    <div class='status'>
      <span class='dot gray' id='overall-dot'></span>
      <span id='overall-status'>connecting...</span>
      <span class='uptime' id='uptime'></span>
    </div>
  </header>

  <main class='grid'>
    <section class='card'>
      <h2>&#9656; Brain</h2>
      <div class='card-body' id='brain-body'>
        <span class='unavailable'>loading...</span>
      </div>
    </section>
    <section class='card'>
      <h2>&#9656; Host</h2>
      <div class='card-body' id='host-body'>
        <span class='unavailable'>loading...</span>
      </div>
    </section>
    <section class='card'>
      <h2>&#9656; Thermal</h2>
      <div class='card-body' id='thermal-body'>
        <span class='unavailable'>loading...</span>
      </div>
    </section>
    <section class='card'>
      <h2>&#9656; Power</h2>
      <div class='card-body' id='power-body'>
        <span class='unavailable'>loading...</span>
      </div>
    </section>
    <section class='card'>
      <h2>&#9656; Personality</h2>
      <div class='card-body' id='personality-body'>
        <span class='unavailable'>loading...</span>
      </div>
    </section>
    <section class='card'>
      <h2>&#9656; Limbic</h2>
      <div class='card-body' id='limbic-body'>
        <span class='unavailable'>loading...</span>
      </div>
    </section>
  </main>

  <footer>
    last update: <span id='last-update'>never</span>
  </footer>

  <script>
    'use strict';
    var REFRESH_MS = 2000;

    /* ── Helpers ── */
    function $(id) { return document.getElementById(id); }
    function setText(id, t) { var e = $(id); if (e) e.textContent = t; }
    function setDot(id, s) { var e = $(id); if (e) e.className = 'dot ' + s; }
    function fmtTemp(c) { return (c != null) ? c.toFixed(1) + '&deg;C' : '--'; }
    function fmtPct(v) { return (v != null) ? v.toFixed(1) + '%' : '--'; }
    function row(label, val) {
      return '<div class="data-row"><span class="data-label">' + label +
             '</span><span class="data-value">' + val + '</span></div>';
    }
    function statusRow(st, label) {
      return '<div class="status-indicator"><span class="dot ' + st +
             '"></span>' + label + '</div>';
    }

    /* ── Status determination ── */
    function thermalStatus(t) {
      if (!t || !t.available) return 'gray';
      var f = t.flags || {};
      if (f.shutdown || f.full_stop) return 'red';
      if (f.throttle) return 'yellow';
      return 'green';
    }
    function powerStatus(p) {
      if (!p || !p.available) return 'gray';
      var soc = p.soc_pct || 0;
      if (soc <= 20) return 'red';
      if (soc <= 40) return 'yellow';
      return 'green';
    }
    function overallStatus(s) {
      var sts = [thermalStatus(s.thermal), powerStatus(s.power)];
      if (sts.indexOf('red') >= 0) return 'red';
      if (sts.indexOf('yellow') >= 0) return 'yellow';
      return 'green';
    }

    /* ── Render ── */
    function renderState(s) {
      /* Header */
      setText('version', 'v' + (s.version || '?'));
      var os = overallStatus(s);
      setDot('overall-dot', os);
      var osLabel = os === 'green' ? 'NOMINAL'
                  : os === 'yellow' ? 'CAUTION'
                  : os === 'red' ? 'ALERT' : 'UNKNOWN';
      setText('overall-status', osLabel);
      setText('uptime', 'up ' + Math.floor(s.uptime_s || 0) + 's');

      /* Brain */
      var b = s.brain || {};
      $('brain-body').innerHTML = b.available
        ? row('model', b.model || '?') +
          row('turns', b.turns || 0) +
          row('facts', b.facts || 0)
        : '<span class="unavailable">brain offline</span>';

      /* Host */
      var h = s.host || {};
      $('host-body').innerHTML = h.available
        ? row('type', h.type || '?') +
          row('platform', h.platform || '?')
        : '<span class="unavailable">host info unavailable</span>';

      /* Thermal */
      var t = s.thermal || {};
      if (t.available) {
        var html = row('host', fmtTemp(t.host_c)) +
                   row('bay', fmtTemp(t.bay_c)) +
                   row('motor', fmtTemp(t.motor_bay_c)) +
                   row('battery', fmtTemp(t.battery_c));
        var ts = thermalStatus(t);
        var tl = ts === 'green' ? 'nominal' : ts === 'yellow' ? 'throttling'
               : ts === 'red' ? 'critical' : '?';
        html += statusRow(ts, tl);
        $('thermal-body').innerHTML = html;
      } else {
        $('thermal-body').innerHTML =
          '<span class="unavailable">thermal monitor offline</span>';
      }

      /* Power */
      var p = s.power || {};
      if (p.available) {
        var html2 = row('soc', fmtPct(p.soc_pct)) +
          row('range', (p.range_m != null ? Math.round(p.range_m) + 'm' : '--'));
        if (p.voltage_v != null) html2 += row('voltage', p.voltage_v.toFixed(2) + 'V');
        if (p.current_a != null) html2 += row('current', p.current_a.toFixed(2) + 'A');
        var ps = powerStatus(p);
        var pl = p.seek_charger ? 'seek charger' : (ps === 'green' ? 'good' : 'low');
        html2 += statusRow(ps, pl);
        $('power-body').innerHTML = html2;
      } else {
        $('power-body').innerHTML =
          '<span class="unavailable">power monitor offline</span>';
      }

      /* Personality */
      var per = s.personality || {};
      if (per.available) {
        var html3 = row('remedy', (per.emoji || '') + ' ' + (per.remedy || '?'));
        if (per.description) html3 += row('desc', per.description);
        html3 += statusRow(per.active ? 'green' : 'gray',
                           per.active ? 'active' : 'inactive');
        $('personality-body').innerHTML = html3;
      } else {
        $('personality-body').innerHTML =
          '<span class="unavailable">personality inactive</span>';
      }

      /* Limbic — VAD bar visualization */
      var l = s.limbic || {};
      if (l.available) {
        var v = Math.max(-1, Math.min(1, l.valence || 0));
        var a = Math.max(0, Math.min(1, l.arousal || 0));
        var d = Math.max(0, Math.min(1, l.dominance || 0));
        var lh = '<div class="vad-container">';

        /* Valence: horizontal diverging bar (negative=left/red, positive=right/green) */
        var vPct = (Math.abs(v) * 50);
        lh += '<div class="vad-group"><div class="vad-label">Valence</div>';
        lh += '<div class="vad-valence"><div class="vad-valence-center"></div>';
        if (v < 0) {
          lh += '<div class="vad-valence-bar" style="right:50%;width:' + vPct + '%;background:var(--red);"></div>';
        } else {
          lh += '<div class="vad-valence-bar" style="left:50%;width:' + vPct + '%;background:var(--green);"></div>';
        }
        lh += '</div><div class="vad-value">' + v.toFixed(2) + '</div></div>';

        /* Arousal: vertical bar (0..1) */
        lh += '<div class="vad-group"><div class="vad-label">Arousal</div>';
        lh += '<div class="vad-vert"><div class="vad-vert-fill" style="height:' + (a * 100) + '%;background:var(--accent);"></div></div>';
        lh += '<div class="vad-value">' + a.toFixed(2) + '</div></div>';

        /* Dominance: vertical bar (0..1) */
        lh += '<div class="vad-group"><div class="vad-label">Dominance</div>';
        lh += '<div class="vad-vert"><div class="vad-vert-fill" style="height:' + (d * 100) + '%;background:var(--accent2);"></div></div>';
        lh += '<div class="vad-value">' + d.toFixed(2) + '</div></div>';

        lh += '</div>';
        lh += row('affect', l.dominant_affect || '?');
        lh += row('allostatic', (l.allostatic_load != null ? l.allostatic_load.toFixed(3) : '?'));
        $('limbic-body').innerHTML = lh;
      } else {
        $('limbic-body').innerHTML =
          '<span class="unavailable">limbic system inactive</span>';
      }

      setText('last-update', new Date().toLocaleTimeString());
    }

    /* ── Refresh loop ── */
    async function refresh() {
      try {
        var resp = await fetch('/api/state');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var state = await resp.json();
        renderState(state);
      } catch (e) {
        console.error('dashboard refresh failed:', e);
        setDot('overall-dot', 'red');
        setText('overall-status', 'CONN ERROR');
      }
    }
    setInterval(refresh, REFRESH_MS);
    refresh();
  </script>
</body>
</html>
"""


# ─── DashboardServer ─────────────────────────────────────────────────


class DashboardServer:
    """Flask web dashboard for R1-A1 subsystem monitoring.

    Parameters
    ----------
    host : str
        Bind address (default ``127.0.0.1`` — local only).
    port : int
        Listen port (default 9298, matching ``config/r1a1.yaml``).
    agent : Agent or None
        The brain agent.  Duck-typed: ``agent.llm.current_model()`` for the
        model tag, ``agent.memory.turns`` / ``agent.memory.facts`` for counts.
        Thermal and power monitors are discovered via ``agent.thermal`` /
        ``agent.power`` (or ``agent.thermal_monitor`` / ``agent.power_monitor``).
    personality_bridge : object or None
        Anything that exposes remedy info.  Duck-typed via ``get_info()``,
        ``to_dict()``, or direct attributes (``remedy``, ``emoji``,
        ``description``, ``active``).
    limbic_bridge : object or None
        Anything that exposes affective state.  Duck-typed via
        ``get_state()``, ``to_dict()``, ``state``, or direct attributes
        (``valence``, ``arousal``, ``dominance``, ``dominant_affect``,
        ``allostatic_load``).
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        agent: Optional[Any] = None,
        personality_bridge: Optional[Any] = None,
        limbic_bridge: Optional[Any] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.agent = agent
        self.personality_bridge = personality_bridge
        self.limbic_bridge = limbic_bridge

        # Server lifecycle state (populated by run() / cleared by stop())
        self._app = None
        self._server = None      # werkzeug BaseWSGIServer
        self._thread = None      # background serve thread
        self._start_time: Optional[float] = None

    # ── Public API ───────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True if the dashboard server thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def run(self) -> None:
        """Start the Flask dashboard in a background daemon thread."""
        if self._server is not None:
            return  # already running
        self._app = self._create_app()

        # Learning: werkzeug.serving.make_server gives a clean
        # serve_forever()/shutdown() pair — no signal hacking or
        # os._exit() needed for graceful stop().
        try:
            from werkzeug.serving import make_server
        except ImportError as exc:
            raise ImportError(
                "werkzeug is required (bundled with Flask). "
                "Install with: pip install flask"
            ) from exc

        self._server = make_server(
            self.host, self.port, self._app, threaded=True,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="r1a1-dashboard",
            daemon=True,
        )
        self._thread.start()
        self._start_time = time.time()

    def stop(self) -> None:
        """Shut down the dashboard server and join the thread."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._app = None

    def get_state(self) -> dict:
        """Return a snapshot of all subsystem states as a dict.

        Each subsystem value is itself a dict with an ``available`` key;
        when the subsystem is offline or not wired, ``available`` is
        ``False`` and the rest of the dict is minimal.
        """
        return {
            "robot_name": ROBOT_NAME,
            "version": self._version(),
            "timestamp": time.time(),
            "uptime_s": (
                time.time() - self._start_time
                if self._start_time is not None
                else 0
            ),
            "refresh_ms": REFRESH_INTERVAL_MS,
            "brain": self._brain_state(),
            "host": self._host_state(),
            "thermal": self._thermal_state(),
            "power": self._power_state(),
            "personality": self._personality_state(),
            "limbic": self._limbic_state(),
        }

    # ── Flask app factory (requirement #2) ───────────────────────────

    def _create_app(self):
        """Lazily create and configure the Flask application.

        Flask is imported here so the module can be loaded without it.
        Raises ``ImportError`` if Flask is not installed.
        """
        if not _FLASK_AVAILABLE:
            raise ImportError(
                "Flask is required to run the dashboard. "
                "Install with: pip install flask"
            )
        # Learning: import inside the method (not at module top) so
        # that merely importing dashboard.server never triggers a
        # Flask dependency.
        from flask import Flask, jsonify, Response

        app = Flask(__name__)
        server = self  # capture for route closures

        @app.route("/")
        def dashboard():
            return Response(DASHBOARD_HTML, mimetype="text/html")

        @app.route("/api/state")
        def api_state():
            try:
                return jsonify(server.get_state())
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route("/api/limbic")
        def api_limbic():
            try:
                return jsonify(server._limbic_state())
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route("/api/personality")
        def api_personality():
            try:
                return jsonify(server._personality_state())
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        return app

    # ── Subsystem collectors ─────────────────────────────────────────
    # Learning: each collector uses duck typing (getattr chains) instead
    # of isinstance checks.  This lets the dashboard work with any object
    # that quacks like a thermal monitor, power monitor, etc. — not just
    # our own classes — and degrades gracefully to {"available": False}
    # when a subsystem is not wired.

    def _version(self) -> str:
        """Best-effort version lookup from the parent ``src`` package."""
        try:
            from importlib import import_module
            mod = import_module("src")
            return getattr(mod, "__version__", "unknown")
        except Exception:
            pass
        try:
            import pathlib
            init = pathlib.Path(__file__).resolve().parent.parent / "__init__.py"
            for line in init.read_text().splitlines():
                if "__version__" in line and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
        return "unknown"

    def _brain_state(self) -> dict:
        """Brain / LLM model status from the agent."""
        if self.agent is None:
            return {"available": False}
        try:
            llm = getattr(self.agent, "llm", None)
            model = "unknown"
            if llm is not None:
                if hasattr(llm, "current_model"):
                    model = str(llm.current_model())
                elif hasattr(llm, "_active_model"):
                    model = str(llm._active_model)

            memory = getattr(self.agent, "memory", None)
            turns = len(memory.turns) if memory and hasattr(memory, "turns") else 0
            facts = len(memory.facts) if memory and hasattr(memory, "facts") else 0

            return {
                "available": True,
                "model": model,
                "turns": turns,
                "facts": facts,
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def _host_state(self) -> dict:
        """Host board type and platform info.

        Learning: tries ``agent.host_type`` first (set by a future
        controller), then falls back to platform detection — tegra/arm
        → jetson, Darwin → mac_ultra, else ubuntu_x86.
        """
        host_type = "unknown"
        if self.agent is not None:
            host_type = getattr(self.agent, "host_type", "unknown")

        if host_type == "unknown":
            machine = platform.machine().lower()
            system = platform.system()
            platform_str = platform.platform().lower()
            if "tegra" in platform_str or "aarch64" in machine or "arm" in machine:
                host_type = "jetson"
            elif system == "Darwin":
                host_type = "mac_ultra"
            elif "x86" in machine:
                host_type = "ubuntu_x86"

        return {
            "available": True,
            "type": host_type,
            "platform": platform.platform(),
            "machine": platform.machine(),
        }

    def _thermal_state(self) -> dict:
        """Thermal zone temperatures and policy flags."""
        mon = self._find_subsystem("thermal", "thermal_monitor")
        if mon is None:
            return {"available": False}
        try:
            report = mon.report() if hasattr(mon, "report") else {}
            if not isinstance(report, dict):
                report = {}
            flags = mon.flags() if hasattr(mon, "flags") else {}
            if not isinstance(flags, dict):
                flags = {}
            battery_c = mon.battery_c() if hasattr(mon, "battery_c") else None

            fan_ok = None
            if hasattr(mon, "fan_check"):
                fc = mon.fan_check()
                if isinstance(fc, dict):
                    fan_ok = fc.get("ok")

            return {
                "available": True,
                "host_c": report.get("host_c"),
                "bay_c": report.get("bay_c"),
                "motor_bay_c": report.get("motor_bay_c"),
                "battery_c": battery_c,
                "flags": flags,
                "fans_ok": fan_ok,
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def _power_state(self) -> dict:
        """Battery state-of-charge, range, and charger-seeking status."""
        mon = self._find_subsystem("power", "power_monitor")
        if mon is None:
            return {"available": False}
        try:
            soc = mon.soc() if hasattr(mon, "soc") else None
            range_m = mon.estimate_range_m() if hasattr(mon, "estimate_range_m") else None
            seek = mon.should_seek_charger() if hasattr(mon, "should_seek_charger") else False

            voltage_v = None
            current_a = None
            if hasattr(mon, "telemetry"):
                tel = mon.telemetry()
                if isinstance(tel, dict):
                    voltage_v = tel.get("voltage_v")
                    current_a = tel.get("current_a")

            return {
                "available": True,
                "soc_pct": soc,
                "range_m": range_m,
                "seek_charger": seek,
                "voltage_v": voltage_v,
                "current_a": current_a,
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def _personality_state(self) -> dict:
        """Personality / remedy overlay info from the bridge."""
        if self.personality_bridge is None:
            return {"available": False}
        bridge = self.personality_bridge
        try:
            # Learning: try dict-style API first, then fall back to
            # individual attributes.  This accommodates bridges that
            # expose a single get_info()/to_dict() method as well as
            # simple objects with bare attributes.
            raw: dict = {}
            if hasattr(bridge, "get_info"):
                raw = bridge.get_info() or {}
            elif hasattr(bridge, "to_dict"):
                raw = bridge.to_dict() or {}
            if not isinstance(raw, dict):
                raw = {}

            remedy = self._get_str(raw, bridge, "remedy", "unknown")
            emoji = self._get_str(raw, bridge, "emoji", "")
            description = self._get_str(raw, bridge, "description", "")

            active = True
            if "active" in raw:
                active = bool(raw["active"])
            else:
                active = bool(getattr(bridge, "active", True))

            return {
                "available": True,
                "active": active,
                "remedy": remedy,
                "emoji": emoji,
                "description": description,
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def _limbic_state(self) -> dict:
        """Limbic affective state: VAD vector, dominant affect, allostatic load."""
        if self.limbic_bridge is None:
            return {"available": False}
        bridge = self.limbic_bridge
        try:
            # Learning: same dual approach as personality — try a
            # dict-returning method first, then individual attributes.
            raw: dict = {}
            if hasattr(bridge, "get_state"):
                raw = bridge.get_state() or {}
            elif hasattr(bridge, "to_dict"):
                raw = bridge.to_dict() or {}
            elif hasattr(bridge, "state"):
                st = bridge.state
                raw = st if isinstance(st, dict) else {}
            if not isinstance(raw, dict):
                raw = {}

            valence = self._get_float(raw, bridge, "valence", 0.0)
            arousal = self._get_float(raw, bridge, "arousal", 0.0)
            dominance = self._get_float(raw, bridge, "dominance", 0.0)
            dominant_affect = self._get_str(raw, bridge, "dominant_affect", "unknown")
            allostatic_load = self._get_float(raw, bridge, "allostatic_load", 0.0)

            # Neurochemistry is optional — pass through if present.
            neuro = raw.get("neurochemistry") if isinstance(raw, dict) else None
            if neuro is None:
                neuro = getattr(bridge, "neurochemistry", None)

            return {
                "available": True,
                "valence": valence,
                "arousal": arousal,
                "dominance": dominance,
                "dominant_affect": dominant_affect,
                "allostatic_load": allostatic_load,
                "neurochemistry": neuro,
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    # ── Private helpers ─────────────────────────────────────────────

    def _find_subsystem(self, *attr_names: str) -> Optional[Any]:
        """Duck-typing search for a subsystem monitor on the agent.

        Tries ``agent.<name>`` for each name, then ``agent.subsystems[name]``.
        Returns the first match or ``None``.
        """
        if self.agent is None:
            return None
        for name in attr_names:
            obj = getattr(self.agent, name, None)
            if obj is not None:
                return obj
        subs = getattr(self.agent, "subsystems", None)
        if isinstance(subs, dict):
            for name in attr_names:
                if name in subs:
                    return subs[name]
        return None

    @staticmethod
    def _get_float(raw: dict, obj: Any, key: str, default: float = 0.0) -> float:
        """Get a float from a dict first, then from an object attribute."""
        if isinstance(raw, dict) and key in raw:
            try:
                return float(raw[key])
            except (TypeError, ValueError):
                return default
        val = getattr(obj, key, None)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return default
        return default

    @staticmethod
    def _get_str(raw: dict, obj: Any, key: str, default: str = "") -> str:
        """Get a string from a dict first, then from an object attribute."""
        if isinstance(raw, dict) and key in raw:
            return str(raw[key])
        val = getattr(obj, key, None)
        if val is not None:
            return str(val)
        return default