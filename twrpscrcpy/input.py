"""evdev injection: touch gestures and hardware keys."""

from __future__ import annotations

import struct
import threading
import time

from .adb import Adb, AdbError
from .device import RecoveryDevice

EV_SYN = 0
EV_KEY = 1
EV_ABS = 3

SYN_REPORT = 0
ABS_MT_SLOT = 0x2F
ABS_MT_TOUCH_MAJOR = 0x30
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
ABS_MT_PRESSURE = 0x3A
ABS_MT_CUSTOM = 0x3E  # Samsung sec_touchscreen "external input" flag
BTN_TOUCH = 0x14A

KEY_BACK = 158
KEY_HOME = 172  # KEY_HOMEPAGE; the Samsung gpio-keys node does not expose 102
KEY_POWER = 116
KEY_VOLUMEUP = 115
KEY_VOLUMEDOWN = 114

EVENT = struct.Struct("<qqHHi")  # struct input_event on 64 bit kernels
TOUCH_PRESSURE = 80
TOUCH_SIZE = 20


class EventInjector:
    """A long lived `fbstream --inject <node>` process fed with raw events."""

    def __init__(self, adb: Adb, helper_path: str, node: str):
        self.adb = adb
        self.helper_path = helper_path
        self.node = node
        self._proc = None

    def _ensure(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True
        try:
            self._proc = self.adb.shell_stdin(f"{self.helper_path} --inject {self.node}")
            return True
        except OSError:
            self._proc = None
            return False

    def send(self, events, retry: bool = False) -> None:
        if not events:
            return
        payload = b"".join(EVENT.pack(0, 0, t, c, v) for t, c, v in events)
        for _ in range(2 if retry else 1):
            if not self._ensure():
                return
            try:
                self._proc.stdin.write(payload)
                self._proc.stdin.flush()
                return
            except (BrokenPipeError, OSError, ValueError):
                # The panel may have been suspended: the helper exits when a
                # write to the input node fails. Restart it and try once more.
                self.close()

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass


class InputController:
    def __init__(self, adb: Adb, device: RecoveryDevice):
        self.adb = adb
        self.device = device
        self.touch = EventInjector(adb, device.helper_path, device.touch_device().node)
        self._key_nodes: dict[int, str] = {}
        for code in (KEY_POWER, KEY_VOLUMEUP, KEY_VOLUMEDOWN, KEY_BACK, KEY_HOME):
            key_device = device.key_device_for(code)
            if key_device is not None:
                self._key_nodes[code] = key_device.node
        self._key_injectors: dict[str, EventInjector] = {}
        self.width = device.width
        self.height = device.height
        self.max_x = device.touch_max_x
        self.max_y = device.touch_max_y
        self._down = False
        self._tracking = 1000
        self._lock = threading.RLock()
        self._key_lock = threading.Lock()
        self._pressed_key: int | None = None
        self._generation = 0
        self._gesture_active = False

    # -- geometry ----------------------------------------------------------
    def set_geometry(self, width: int, height: int) -> None:
        if width > 0 and height > 0:
            self.width, self.height = width, height

    def _raw(self, x: float, y: float) -> tuple[int, int]:
        width = max(1, self.width - 1)
        height = max(1, self.height - 1)
        rx = int(round(max(0.0, min(width, x)) * self.max_x / width))
        ry = int(round(max(0.0, min(height, y)) * self.max_y / height))
        return rx, ry

    # -- low level touch ---------------------------------------------------
    def reset_touch(self) -> None:
        """Close any contact left behind by an interrupted gesture.

        If the injector died between a press and its release (the panel can be
        suspended mid-gesture), TWRP keeps believing a finger is down and
        ignores every new touch. Sending a release on both slots clears it.
        """
        self.touch.send(
            [
                (EV_ABS, ABS_MT_SLOT, 0),
                (EV_ABS, ABS_MT_TRACKING_ID, -1),
                (EV_ABS, ABS_MT_SLOT, 1),
                (EV_ABS, ABS_MT_TRACKING_ID, -1),
                (EV_ABS, ABS_MT_PRESSURE, 0),
                (EV_KEY, BTN_TOUCH, 0),
                (EV_SYN, SYN_REPORT, 0),
            ],
            retry=True,
        )

    def touch_down(self, x: float, y: float) -> None:
        if self._down:
            self.touch_move(x, y)
            return
        self.reset_touch()
        rx, ry = self._raw(x, y)
        self._tracking += 1
        self._down = True
        self.touch.send(
            [
                (EV_ABS, ABS_MT_SLOT, 0),
                (EV_ABS, ABS_MT_TRACKING_ID, self._tracking),
                (EV_ABS, ABS_MT_CUSTOM, 1),
                (EV_ABS, ABS_MT_POSITION_X, rx),
                (EV_ABS, ABS_MT_POSITION_Y, ry),
                (EV_ABS, ABS_MT_TOUCH_MAJOR, TOUCH_SIZE),
                (EV_ABS, ABS_MT_PRESSURE, TOUCH_PRESSURE),
                (EV_KEY, BTN_TOUCH, 1),
                (EV_SYN, SYN_REPORT, 0),
            ],
            retry=True,
        )

    def touch_move(self, x: float, y: float) -> None:
        if not self._down:
            return
        rx, ry = self._raw(x, y)
        self.touch.send(
            [
                (EV_ABS, ABS_MT_SLOT, 0),
                (EV_ABS, ABS_MT_POSITION_X, rx),
                (EV_ABS, ABS_MT_POSITION_Y, ry),
                (EV_ABS, ABS_MT_TOUCH_MAJOR, TOUCH_SIZE),
                (EV_ABS, ABS_MT_PRESSURE, TOUCH_PRESSURE),
                (EV_SYN, SYN_REPORT, 0),
            ],
            retry=True,
        )

    def touch_up(self) -> None:
        if not self._down:
            return
        self._down = False
        self.touch.send(
            [
                (EV_ABS, ABS_MT_SLOT, 0),
                (EV_ABS, ABS_MT_TRACKING_ID, -1),
                (EV_KEY, BTN_TOUCH, 0),
                (EV_SYN, SYN_REPORT, 0),
            ],
            retry=True,
        )

    # -- keys --------------------------------------------------------------
    def _key_injector(self, code: int) -> "EventInjector | None":
        node = self._key_nodes.get(code)
        if node is None:
            return None
        injector = self._key_injectors.get(node)
        if injector is None:
            injector = EventInjector(self.adb, self.device.helper_path, node)
            self._key_injectors[node] = injector
        return injector

    def key(self, code: int, hold: float = 0.06) -> None:
        injector = self._key_injector(code)
        if injector is None:
            return
        with self._key_lock:
            self._pressed_key = code
            injector.send([(EV_KEY, code, 1), (EV_SYN, SYN_REPORT, 0)])
            time.sleep(hold)
            injector.send([(EV_KEY, code, 0), (EV_SYN, SYN_REPORT, 0)])
            self._pressed_key = None

    def release_keys(self) -> None:
        """Never leave a key logically held when the injector goes away."""
        with self._key_lock:
            code, self._pressed_key = self._pressed_key, None
            if code is not None:
                injector = self._key_injector(code)
                if injector is not None:
                    injector.send([(EV_KEY, code, 0), (EV_SYN, SYN_REPORT, 0)])

    # -- gestures ----------------------------------------------------------
    def cancel_gestures(self) -> None:
        self._generation += 1

    def busy(self) -> bool:
        return self._down or self._gesture_active

    def _async(self, fn) -> None:
        self._generation += 1
        generation = self._generation

        def runner():
            with self._lock:
                if generation != self._generation:
                    return
                self._gesture_active = True
                try:
                    fn(generation)
                finally:
                    self._gesture_active = False

        threading.Thread(target=runner, daemon=True).start()

    def tap(self, x: float, y: float, hold: float = 0.08) -> None:
        def action(generation):
            self.touch_down(x, y)
            time.sleep(hold)
            self.touch_up()

        self._async(action)

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        duration: float = 0.3,
        steps: int = 24,
    ) -> None:
        def action(generation):
            self.touch_down(x1, y1)
            time.sleep(0.02)
            for index in range(1, steps + 1):
                if generation != self._generation:
                    break
                x = x1 + (x2 - x1) * index / steps
                y = y1 + (y2 - y1) * index / steps
                self.touch_move(x, y)
                time.sleep(duration / steps)
            self.touch_up()

        self._async(action)

    def scroll(self, direction: int) -> None:
        """direction -1 = up (content moves down), +1 = down."""
        cx = self.width / 2
        top = self.height * 0.35
        bottom = self.height * 0.65
        if direction < 0:
            self.swipe(cx, bottom, cx, top, duration=0.22, steps=14)
        else:
            self.swipe(cx, top, cx, bottom, duration=0.22, steps=14)

    def unlock_swipe(self, attempts: int = 2) -> None:
        """Drag the TWRP 'Swipe to Unlock' slider from left to right.

        TWRP's screensaver ignores quick flings: the slider only follows a
        slow drag (about 1.5 s from the left edge to the right edge).
        """

        def action(generation):
            y = self.height * 0.88
            for attempt in range(max(1, attempts)):
                if generation != self._generation:
                    return
                if attempt:
                    time.sleep(1.2)
                self.touch_down(self.width * 0.10, y)
                time.sleep(0.15)
                for index in range(1, 61):
                    if generation != self._generation:
                        self.touch_up()
                        return
                    x = self.width * (0.10 + 0.84 * index / 60)
                    self.touch_move(x, y)
                    time.sleep(0.025)
                time.sleep(0.12)
                self.touch_up()

        self._async(action)

    def nudge(self) -> None:
        """A harmless tap in the status bar, used to defeat TWRP's screen timeout."""
        if self.busy():
            return

        def action(generation):
            self.touch_down(self.width * 0.5, self.height * 0.012)
            time.sleep(0.03)
            self.touch_up()

        self._async(action)

    def close(self) -> None:
        self.release_keys()
        if self._down:
            self.touch_up()
        self.reset_touch()
        self.touch.close()
        for injector in self._key_injectors.values():
            injector.close()
        self._key_injectors.clear()
