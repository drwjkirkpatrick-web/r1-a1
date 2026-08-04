"""Tests for thermal, power, and audio subsystems. All hardware is mocked.

Run: python -m unittest tests.test_thermal_power_audio -v
  or: python -m pytest tests/test_thermal_power_audio.py -v
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from thermal import ThermalMonitor          # noqa: E402
from thermal.monitor import (               # noqa: E402
    FAN_COUNT,
    SHUTDOWN_C,
    THROTTLE_C,
    BATTERY_FULL_STOP_C,
)
from power import PowerMonitor              # noqa: E402
from audio import Speaker, MicArray         # noqa: E402
from audio.speaker import CHIRPS            # noqa: E402


def make_thermal(host=40.0, bay=40.0, motor=40.0, battery=30.0, rpms=None):
    rpms = rpms if rpms is not None else [3000] * FAN_COUNT
    tach = MagicMock(side_effect=lambda i: rpms[i])
    mon = ThermalMonitor(
        host_reader=MagicMock(return_value=host),
        bay_reader=MagicMock(return_value=bay),
        motor_bay_reader=MagicMock(return_value=motor),
        battery_reader=MagicMock(return_value=battery),
        fan_tach_reader=tach,
    )
    return mon, tach


class TestThermalMonitor(unittest.TestCase):
    def test_report_returns_all_zones(self):
        mon, _ = make_thermal(host=55.0, bay=42.5, motor=38.0)
        rep = mon.report()
        self.assertEqual(rep, {"host_c": 55.0, "bay_c": 42.5, "motor_bay_c": 38.0})

    def test_nominal_temps_set_no_flags(self):
        mon, _ = make_thermal()
        mon.report()
        self.assertFalse(mon.throttle_flag)
        self.assertFalse(mon.shutdown_flag)
        self.assertFalse(mon.full_stop_flag)

    def test_throttle_flag_above_75(self):
        mon, _ = make_thermal(host=THROTTLE_C + 0.1)
        mon.report()
        self.assertTrue(mon.throttle_flag)
        self.assertFalse(mon.shutdown_flag)

    def test_no_throttle_at_exactly_75(self):
        mon, _ = make_thermal(host=THROTTLE_C)
        mon.report()
        self.assertFalse(mon.throttle_flag)

    def test_shutdown_flag_above_85_any_zone(self):
        for zone in ("host", "bay", "motor"):
            kwargs = {zone: SHUTDOWN_C + 0.1}
            mon, _ = make_thermal(**kwargs)
            mon.report()
            self.assertTrue(mon.shutdown_flag, f"zone={zone}")
            self.assertTrue(mon.throttle_flag)

    def test_battery_full_stop_above_50(self):
        mon, _ = make_thermal(battery=BATTERY_FULL_STOP_C + 0.1)
        mon.report()
        self.assertTrue(mon.full_stop_flag)
        self.assertFalse(mon.throttle_flag)  # zones still cool

    def test_battery_at_exactly_50_no_full_stop(self):
        mon, _ = make_thermal(battery=BATTERY_FULL_STOP_C)
        mon.report()
        self.assertFalse(mon.full_stop_flag)

    def test_simulate_injects_fake_temp(self):
        mon, _ = make_thermal()
        flags = mon.simulate(90.0)
        rep = mon.report()
        self.assertEqual(rep["host_c"], 90.0)
        self.assertEqual(rep["bay_c"], 90.0)
        self.assertTrue(flags["throttle"])
        self.assertTrue(flags["shutdown"])

    def test_simulate_battery_full_stop(self):
        mon, _ = make_thermal()
        flags = mon.simulate(40.0, battery_c=60.0)
        self.assertTrue(flags["full_stop"])
        self.assertFalse(flags["throttle"])

    def test_clear_simulation_restores_live_readings(self):
        mon, _ = make_thermal(host=41.0)
        mon.simulate(90.0)
        mon.clear_simulation()
        mon.reset_flags()
        rep = mon.report()
        self.assertEqual(rep["host_c"], 41.0)
        self.assertFalse(mon.throttle_flag)

    def test_fan_check_all_fans_healthy(self):
        mon, tach = make_thermal()
        result = mon.fan_check()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["fans"]), FAN_COUNT)
        self.assertEqual(tach.call_count, FAN_COUNT)
        for i in range(FAN_COUNT):
            self.assertTrue(result["fans"][i]["ok"])

    def test_fan_check_detects_stalled_fan(self):
        rpms = [3000, 3000, 0, 3000, 3000]
        mon, _ = make_thermal(rpms=rpms)
        result = mon.fan_check()
        self.assertFalse(result["ok"])
        self.assertFalse(result["fans"][2]["ok"])
        self.assertTrue(result["fans"][4]["ok"])

    def test_fan_check_without_tach_reader_fails_safe(self):
        mon = ThermalMonitor(
            host_reader=lambda: 40.0,
            bay_reader=lambda: 40.0,
            motor_bay_reader=lambda: 40.0,
        )
        self.assertFalse(mon.fan_check()["ok"])


class TestPowerMonitor(unittest.TestCase):
    def test_soc_from_dict_reader(self):
        pm = PowerMonitor(MagicMock(return_value={"soc_pct": 64.0,
                                                  "voltage_v": 25.1}))
        self.assertEqual(pm.soc(), 64.0)

    def test_soc_from_scalar_reader(self):
        pm = PowerMonitor(MagicMock(return_value=42))
        self.assertEqual(pm.soc(), 42.0)

    def test_soc_clamped_to_0_100(self):
        self.assertEqual(PowerMonitor(lambda: 137.5).soc(), 100.0)
        self.assertEqual(PowerMonitor(lambda: -3).soc(), 0.0)

    def test_estimate_range_math(self):
        pm = PowerMonitor(lambda: 50.0)
        self.assertAlmostEqual(pm.estimate_range_m(), 600.0)  # 50 * 12

    def test_estimate_range_zero_soc(self):
        pm = PowerMonitor(lambda: 0.0)
        self.assertEqual(pm.estimate_range_m(), 0.0)

    def test_should_seek_charger_below_20(self):
        self.assertTrue(PowerMonitor(lambda: 19.9).should_seek_charger())
        self.assertTrue(PowerMonitor(lambda: 0.0).should_seek_charger())

    def test_should_not_seek_charger_at_or_above_20(self):
        self.assertFalse(PowerMonitor(lambda: 20.0).should_seek_charger())
        self.assertFalse(PowerMonitor(lambda: 85.0).should_seek_charger())


class TestSpeaker(unittest.TestCase):
    def test_say_routes_text_to_voice_fn(self):
        sp = Speaker()
        voice = MagicMock(return_value="ok")
        self.assertEqual(sp.say("hello there", voice), "ok")
        voice.assert_called_once_with("hello there")

    def test_say_suppressed_while_muted(self):
        sp = Speaker()
        sp.mute_until(60)
        voice = MagicMock()
        self.assertIsNone(sp.say("hello", voice))
        voice.assert_not_called()

    def test_mute_timer_expires(self):
        sp = Speaker()
        self.assertFalse(sp.is_muted())
        sp.mute_until(0.05)
        self.assertTrue(sp.is_muted())
        time.sleep(0.08)
        self.assertFalse(sp.is_muted())

    def test_unmute_cancels_mute(self):
        sp = Speaker()
        sp.mute_until(60)
        self.assertTrue(sp.is_muted())
        sp.unmute()
        self.assertFalse(sp.is_muted())

    def test_chirp_mood_routing(self):
        beep = MagicMock()
        sp = Speaker(beep_fn=beep)
        for mood in ("happy", "sad", "alert", "confused"):
            beep.reset_mock()
            pattern = sp.chirp(mood)
            self.assertEqual(pattern, CHIRPS[mood])
            beep.assert_called_once_with(CHIRPS[mood])
        # each mood maps to a distinct canned pattern
        self.assertEqual(len({tuple(p) for p in CHIRPS.values()}), 4)

    def test_chirp_unknown_mood_raises(self):
        sp = Speaker()
        with self.assertRaises(ValueError):
            sp.chirp("angry")

    def test_chirp_suppressed_while_muted(self):
        beep = MagicMock()
        sp = Speaker(beep_fn=beep)
        sp.mute_until(60)
        pattern = sp.chirp("alert")
        self.assertEqual(pattern, CHIRPS["alert"])
        beep.assert_not_called()


class TestMicArray(unittest.TestCase):
    def test_listen_uses_injected_capture(self):
        capture = MagicMock(return_value=b"\x00\x01")
        mic = MicArray(capture_fn=capture)
        audio = mic.listen(timeout=2.5)
        capture.assert_called_once_with(2.5)
        self.assertEqual(audio, b"\x00\x01")
        self.assertEqual(mic.last_audio, b"\x00\x01")

    def test_listen_timeout_returns_none(self):
        mic = MicArray(capture_fn=MagicMock(return_value=None))
        self.assertIsNone(mic.listen(timeout=0.1))

    def test_doa_reports_degrees(self):
        mic = MicArray(capture_fn=lambda t: b"", doa_fn=lambda: 135.0)
        self.assertEqual(mic.doa(), 135.0)

    def test_doa_clamping(self):
        cases = {360.0: 0.0, 361.5: 1.5, -90.0: 270.0, 725.0: 5.0, -1.0: 359.0}
        for raw, expected in cases.items():
            mic = MicArray(capture_fn=lambda t: b"", doa_fn=lambda r=raw: r)
            self.assertAlmostEqual(mic.doa(), expected, msg=f"raw={raw}")
            self.assertGreaterEqual(mic.doa(), 0.0)
            self.assertLess(mic.doa(), 360.0)

    def test_doa_default_without_estimator(self):
        mic = MicArray(capture_fn=lambda t: b"")
        self.assertEqual(mic.doa(), 0.0)


if __name__ == "__main__":
    unittest.main()
