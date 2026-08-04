"""Tests for eye (camera + wink), display (screen), and projector (beam).

All hardware is mocked: capture functions, MCU links, framebuffer writers,
lamp/fan drivers, and a fake timer factory for the cooldown path. No real
devices, no sleeping, no threads.
"""

import os
import sys
import unittest
from unittest.mock import Mock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from eye.camera import EyeCamera
from eye.wink import (
    EYE_LED_PWM_CHANNEL,
    LED_OFF_DUTY,
    LED_ON_DUTY,
    SHUTTER_CLOSED_DEG,
    SHUTTER_OPEN_DEG,
    SHUTTER_SERVO_CHANNEL,
    Wink,
)
from display.screen import GLYPHS, HEIGHT, WIDTH, Screen
from projector.beam import COOLDOWN_S, Beam


class FakeTimer:
    """Deterministic stand-in for threading.Timer."""

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback()


class FakeTimerFactory:
    def __init__(self):
        self.timers = []

    def __call__(self, delay, callback):
        timer = FakeTimer(delay, callback)
        self.timers.append(timer)
        return timer

    @property
    def last(self):
        return self.timers[-1]


# ---------------------------------------------------------------------------
# eye.camera
# ---------------------------------------------------------------------------


class TestEyeCamera(unittest.TestCase):
    def test_snapshot_returns_bytes_from_capture_fn(self):
        capture = Mock(return_value=b"\xff\xd8JPEGDATA")
        cam = EyeCamera(capture_fn=capture)
        frame = cam.snapshot()
        self.assertEqual(frame, b"\xff\xd8JPEGDATA")
        capture.assert_called_once_with()

    def test_snapshot_rejects_non_bytes(self):
        cam = EyeCamera(capture_fn=lambda: "not bytes")
        with self.assertRaises(TypeError):
            cam.snapshot()

    def test_caption_calls_vlm_client_object(self):
        cam = EyeCamera(capture_fn=lambda: b"FRAME")
        vlm = Mock()
        vlm.caption.return_value = "a human waving"
        result = cam.caption(vlm)
        self.assertEqual(result, "a human waving")
        vlm.caption.assert_called_once()
        args, _ = vlm.caption.call_args
        self.assertEqual(args[0], b"FRAME")

    def test_caption_calls_vlm_callable(self):
        cam = EyeCamera(capture_fn=lambda: b"FRAME")
        calls = []

        def vlm(image, prompt):
            calls.append((image, prompt))
            return "a doorway"

        self.assertEqual(cam.caption(vlm, prompt="what?"), "a doorway")
        self.assertEqual(calls, [(b"FRAME", "what?")])

    def test_caption_rejects_bad_client(self):
        cam = EyeCamera(capture_fn=lambda: b"FRAME")
        with self.assertRaises(TypeError):
            cam.caption(42)

    def test_ambient_lux_from_exposure_telemetry(self):
        # Reference point: 1/30 s exposure at unity gain -> calibration lux.
        cam = EyeCamera(
            capture_fn=lambda: b"",
            telemetry_fn=lambda: {"exposure_us": 1_000_000.0 / 30.0, "gain": 1.0},
        )
        self.assertAlmostEqual(cam.ambient_lux(), 250.0)
        # Darker scene: longer exposure -> lower lux.
        cam_dark = EyeCamera(
            capture_fn=lambda: b"",
            telemetry_fn=lambda: {"exposure_us": 1_000_000.0 / 5.0, "gain": 2.0},
        )
        self.assertLess(cam_dark.ambient_lux(), 250.0)

    def test_ambient_lux_requires_telemetry(self):
        cam = EyeCamera(capture_fn=lambda: b"")
        with self.assertRaises(RuntimeError):
            cam.ambient_lux()

    def test_face_present_routes_through_detector(self):
        capture = Mock(return_value=b"FRAME")
        detector = Mock(return_value=True)
        cam = EyeCamera(capture_fn=capture, detector=detector)
        self.assertTrue(cam.face_present())
        detector.assert_called_once_with(b"FRAME")

        detector.return_value = False
        self.assertFalse(cam.face_present())

    def test_face_present_defaults_false_without_detector(self):
        cam = EyeCamera(capture_fn=lambda: b"FRAME")
        self.assertFalse(cam.face_present())


# ---------------------------------------------------------------------------
# eye.wink
# ---------------------------------------------------------------------------

EXPECTED_WINK_SEQUENCE = [
    {"cmd": "pwm", "channel": EYE_LED_PWM_CHANNEL, "duty": LED_ON_DUTY},
    {
        "cmd": "servo",
        "channel": SHUTTER_SERVO_CHANNEL,
        "position_deg": SHUTTER_CLOSED_DEG,
    },
    {
        "cmd": "servo",
        "channel": SHUTTER_SERVO_CHANNEL,
        "position_deg": SHUTTER_OPEN_DEG,
    },
    {"cmd": "pwm", "channel": EYE_LED_PWM_CHANNEL, "duty": LED_OFF_DUTY},
]


class TestWink(unittest.TestCase):
    def test_single_wink_command_sequence(self):
        link = Mock()
        Wink(link).wink()
        self.assertEqual(link.call_count, 4)
        self.assertEqual(
            link.call_args_list, [call(c) for c in EXPECTED_WINK_SEQUENCE]
        )

    def test_wink_count_repeats_sequence(self):
        link = Mock()
        Wink(link).wink(count=2)
        self.assertEqual(link.call_count, 8)
        self.assertEqual(
            link.call_args_list, [call(c) for c in EXPECTED_WINK_SEQUENCE * 2]
        )

    def test_wink_rejects_zero_count(self):
        with self.assertRaises(ValueError):
            Wink(Mock()).wink(count=0)

    def test_link_object_with_send_method(self):
        class LinkObj:
            def __init__(self):
                self.commands = []

            def send(self, command):
                self.commands.append(command)

        link = LinkObj()
        Wink(link).wink()
        self.assertEqual(link.commands, EXPECTED_WINK_SEQUENCE)


# ---------------------------------------------------------------------------
# display.screen
# ---------------------------------------------------------------------------


class TestScreen(unittest.TestCase):
    def make_screen(self):
        writer = Mock()
        sleep_fn = Mock()
        return Screen(writer, sleep_fn=sleep_fn), writer, sleep_fn

    def test_show_canned_glyphs(self):
        screen, writer, _ = self.make_screen()
        for name in ("smile", "neutral", "alert"):
            screen.show(name)
        self.assertEqual(writer.call_count, 3)
        for i, name in enumerate(("smile", "neutral", "alert")):
            frame = writer.call_args_list[i].args[0]
            self.assertIsInstance(frame, bytes)
            self.assertEqual(frame.decode(), "\n".join(GLYPHS[name]))

    def test_show_unknown_glyph_raises(self):
        screen, _, _ = self.make_screen()
        with self.assertRaises(ValueError):
            screen.show("angry")

    def test_gauge_full_and_empty(self):
        screen, writer, _ = self.make_screen()
        screen.gauge(100)
        full = writer.call_args.args[0].decode()
        self.assertIn("#" * 20, full)
        self.assertIn("100.0%", full)

        screen.gauge(0)
        empty = writer.call_args.args[0].decode()
        self.assertIn("-" * 20, empty)
        self.assertNotIn("#" * 20 + "#", empty)

    def test_gauge_clamps_out_of_range(self):
        screen, writer, _ = self.make_screen()
        screen.gauge(250)
        self.assertIn("100.0%", writer.call_args.args[0].decode())
        screen.gauge(-10)
        self.assertIn("0.0%", writer.call_args.args[0].decode())

    def test_scroll_text_emits_multiple_frames_and_sleeps(self):
        screen, writer, sleep_fn = self.make_screen()
        screen.scroll_text("HELLO")
        # padded = WIDTH + len + WIDTH spaces -> len(text) + 2*WIDTH - WIDTH + 1 steps
        expected_steps = len("HELLO") + WIDTH + 1
        self.assertEqual(writer.call_count, expected_steps)
        self.assertEqual(sleep_fn.call_count, expected_steps)
        # One frame shows the text flush against the left edge.
        text_lines = [
            c.args[0].decode().splitlines()[HEIGHT // 2]
            for c in writer.call_args_list
        ]
        self.assertTrue(any(line.startswith("HELLO") for line in text_lines))

    def test_scroll_text_rejects_empty(self):
        screen, _, _ = self.make_screen()
        with self.assertRaises(ValueError):
            screen.scroll_text("")

    def test_sleep_blanks_and_wake_restores_neutral(self):
        screen, writer, _ = self.make_screen()
        screen.sleep()
        self.assertTrue(screen.asleep)
        blank = writer.call_args.args[0].decode()
        self.assertEqual(blank.strip(), "")

        screen.wake()
        self.assertFalse(screen.asleep)
        self.assertEqual(writer.call_args.args[0].decode(), "\n".join(GLYPHS["neutral"]))


# ---------------------------------------------------------------------------
# projector.beam
# ---------------------------------------------------------------------------


class TestBeam(unittest.TestCase):
    def make_beam(self):
        lamp, fan, brightness, output = Mock(), Mock(), Mock(), Mock()
        timers = FakeTimerFactory()
        beam = Beam(
            lamp_fn=lamp,
            fan_fn=fan,
            brightness_fn=brightness,
            output_fn=output,
            timer_factory=timers,
        )
        return beam, lamp, fan, brightness, output, timers

    def test_on_lights_lamp_with_fan(self):
        beam, lamp, fan, *_ = self.make_beam()
        beam.on()
        self.assertTrue(beam.is_on)
        fan.assert_called_once_with(True)
        lamp.assert_called_once_with(True)

    def test_off_kills_lamp_then_cooldown_timer(self):
        beam, lamp, fan, _, _, timers = self.make_beam()
        beam.on()
        beam.off()
        self.assertFalse(beam.is_on)
        lamp.assert_called_with(False)
        # Cooldown timer scheduled for exactly COOLDOWN_S; fan still on.
        self.assertTrue(beam.cooling_down)
        self.assertEqual(timers.last.delay, COOLDOWN_S)
        self.assertEqual(COOLDOWN_S, 30.0)
        self.assertTrue(timers.last.started)
        fan.assert_called_once_with(True)  # no fan-off yet
        # Timer fires -> fan stops.
        timers.last.fire()
        fan.assert_called_with(False)
        self.assertFalse(beam.cooling_down)

    def test_on_during_cooldown_cancels_timer(self):
        beam, lamp, fan, _, _, timers = self.make_beam()
        beam.on()
        beam.off()
        timer = timers.last
        beam.on()
        self.assertTrue(timer.cancelled)
        self.assertFalse(beam.cooling_down)
        self.assertTrue(beam.is_on)
        # Fan never turned off across the cycle.
        for c in fan.call_args_list:
            self.assertEqual(c, call(True))

    def test_repeated_off_replaces_cooldown_timer(self):
        beam, _, _, _, _, timers = self.make_beam()
        beam.on()
        beam.off()
        first = timers.last
        beam.off()
        self.assertTrue(first.cancelled)
        self.assertIsNot(timers.last, first)

    def test_show_requires_lamp_on(self):
        beam, _, _, _, output, _ = self.make_beam()
        with self.assertRaises(RuntimeError):
            beam.show(b"frame")
        output.assert_not_called()

    def test_show_pushes_frame_to_output(self):
        beam, _, _, _, output, _ = self.make_beam()
        beam.on()
        beam.show("map")
        output.assert_called_once_with("map")

    def test_mirror_camera_snapshots_and_shows(self):
        beam, _, _, _, output, _ = self.make_beam()
        camera = Mock()
        camera.snapshot.return_value = b"LIVEFEED"
        beam.on()
        frame = beam.mirror_camera(camera)
        camera.snapshot.assert_called_once_with()
        output.assert_called_once_with(b"LIVEFEED")
        self.assertEqual(frame, b"LIVEFEED")

    def test_set_brightness_clamps(self):
        beam, _, _, brightness, _, _ = self.make_beam()
        self.assertEqual(beam.set_brightness(0.5), 0.5)
        self.assertEqual(beam.set_brightness(2.0), 1.0)
        self.assertEqual(beam.set_brightness(-0.3), 0.0)
        self.assertEqual(
            brightness.call_args_list, [call(0.5), call(1.0), call(0.0)]
        )
        self.assertEqual(beam.brightness, 0.0)


if __name__ == "__main__":
    unittest.main()
