"""Recovery side discovery: properties, framebuffer, input devices, helper."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .adb import Adb, AdbError

ABS_MT_POSITION_X = 53
ABS_MT_POSITION_Y = 54
INPUT_PROP_DIRECT = 1


@dataclass
class InputDevice:
    name: str
    node: str
    abs_bits: int = 0
    key_bits: int = 0
    prop_bits: int = 0

    @property
    def is_touch(self) -> bool:
        mask = (1 << ABS_MT_POSITION_X) | (1 << ABS_MT_POSITION_Y)
        return (self.abs_bits & mask) == mask

    @property
    def is_direct(self) -> bool:
        return bool(self.prop_bits & (1 << INPUT_PROP_DIRECT))


@dataclass
class Geometry:
    width: int = 0
    height: int = 0
    scale: int = 1

    @property
    def device_width(self) -> int:
        return self.width * self.scale

    @property
    def device_height(self) -> int:
        return self.height * self.scale


def _bitmap_value(tokens: list[str]) -> int:
    """Kernel prints bitmaps most significant word first."""
    value = 0
    for index, token in enumerate(reversed(tokens)):
        try:
            value |= int(token, 16) << (64 * index)
        except ValueError:
            continue
    return value


def parse_input_devices(text: str) -> list[InputDevice]:
    devices: list[InputDevice] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        name = ""
        node = ""
        abs_bits = key_bits = prop_bits = 0
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("N: Name="):
                name = line[len("N: Name="):].strip().strip('"')
            elif line.startswith("H: Handlers="):
                for token in line[len("H: Handlers="):].split():
                    if token.startswith("event"):
                        node = "/dev/input/" + token
            elif line.startswith("B: ABS="):
                abs_bits = _bitmap_value(line[len("B: ABS="):].split())
            elif line.startswith("B: KEY="):
                key_bits = _bitmap_value(line[len("B: KEY="):].split())
            elif line.startswith("B: PROP="):
                prop_bits = _bitmap_value(line[len("B: PROP="):].split())
        if node:
            devices.append(
                InputDevice(
                    name=name,
                    node=node,
                    abs_bits=abs_bits,
                    key_bits=key_bits,
                    prop_bits=prop_bits,
                )
            )
    return devices


@dataclass
class RecoveryDevice:
    adb: Adb
    serial: str
    state: str = ""
    model: str = ""
    codename: str = ""
    twrp_version: str = ""
    android_version: str = ""
    fb_path: str = "/dev/graphics/fb0"
    arch: str = ""
    helper_dir: str = "/tmp/twrpscrcpy"
    helper_path: str = ""
    inputs: list[InputDevice] = field(default_factory=list)
    width: int = 0
    height: int = 0
    touch_max_x: int = 4095
    touch_max_y: int = 4095

    # -- creation ----------------------------------------------------------
    @classmethod
    def connect(cls, adb: Adb, touch_max: tuple[int, int] | None = None) -> "RecoveryDevice":
        entry = adb.select()
        dev = cls(adb=adb, serial=entry.serial, state=entry.state, model=entry.model)
        dev._load_properties()
        dev._load_framebuffer()
        dev._load_inputs()
        dev.arch = dev._read("uname -m").strip() or "aarch64"
        if touch_max:
            dev.touch_max_x, dev.touch_max_y = touch_max
        dev.install_helper()
        return dev

    def _read(self, command: str) -> str:
        try:
            return self.adb.shell(command)
        except AdbError:
            return ""

    def _load_properties(self) -> None:
        keys = {
            "ro.twrp.version": "twrp_version",
            "ro.product.device": "codename",
            "ro.build.version.release": "android_version",
        }
        for prop, attr in keys.items():
            value = self._read(f"getprop {prop}").strip()
            if value:
                setattr(self, attr, value)
        if not self.model:
            model = self._read("getprop ro.product.model").strip()
            if model and not self.model:
                self.model = model

    def _load_framebuffer(self) -> None:
        for candidate in ("/dev/graphics/fb0", "/dev/fb0"):
            if self._read(f"test -c {candidate} && echo yes").strip() == "yes":
                self.fb_path = candidate
                break
        modes = self._read(f"cat /sys/class/graphics/fb0/modes 2>/dev/null").strip()
        match = re.search(r"(\d+)x(\d+)", modes)
        if match:
            self.width, self.height = int(match.group(1)), int(match.group(2))
            return
        virtual = self._read("cat /sys/class/graphics/fb0/virtual_size 2>/dev/null").strip()
        if "," in virtual:
            w, h = virtual.split(",", 1)
            try:
                self.width, self.height = int(w), int(h)
                # double buffering: virtual height is twice the visible height
                if self.height >= 2 * self.width:
                    self.height //= 2
            except ValueError:
                pass

    def _load_inputs(self) -> None:
        text = self._read("cat /proc/bus/input/devices")
        self.inputs = parse_input_devices(text)

    # -- helper ------------------------------------------------------------
    @property
    def is_recovery(self) -> bool:
        return bool(self.twrp_version) or self.state == "recovery"

    def install_helper(self) -> None:
        arch = self.arch or "aarch64"
        name = "fbstream-arm64" if arch.startswith("aarch64") or arch.startswith("arm64") else "fbstream-arm"
        local = Path(__file__).with_name("bin") / name
        if not local.is_file():
            raise AdbError(f"helper binary missing: {local}")
        errors = []
        for directory in ("/tmp/twrpscrcpy", "/data/local/tmp/twrpscrcpy"):
            try:
                self.adb.shell(f"mkdir -p {directory}")
                self.adb.push(str(local), f"{directory}/fbstream")
                self.adb.shell(f"chmod 755 {directory}/fbstream")
                if self._read(f"test -x {directory}/fbstream && echo ok").strip() == "ok":
                    self.helper_dir = directory
                    self.helper_path = f"{directory}/fbstream"
                    return
            except AdbError as exc:
                errors.append(str(exc))
        raise AdbError("could not install helper on device: " + "; ".join(errors))

    def screen_brightness(self) -> int | None:
        """Current backlight level, or None when the kernel does not expose one."""
        output = self._read("cat /sys/class/backlight/*/brightness 2>/dev/null").strip()
        if not output:
            return None
        try:
            return int(output.split()[0])
        except (ValueError, IndexError):
            return None

    def helper_ready(self) -> bool:
        if not self.helper_path:
            return False
        return self._read(f"test -x {self.helper_path} && echo ok").strip() == "ok"

    # -- inputs ------------------------------------------------------------
    def touch_device(self) -> InputDevice:
        touch = [d for d in self.inputs if d.is_touch]
        if not touch:
            raise AdbError("no multitouch input device found on the device")
        touch.sort(key=lambda d: (not d.is_direct, "touch" not in d.name.lower()))
        return touch[0]

    def key_device_for(self, code: int) -> InputDevice | None:
        """Pick the input node that advertises this key code.

        Samsung exposes POWER/VOLUME/HOMEPAGE on gpio_keys but BACK on
        sec_touchkey; writing a code to a node that does not support it is
        silently dropped by the kernel.
        """
        candidates = [d for d in self.inputs if d.key_bits >> code & 1]
        if not candidates:
            return None
        candidates.sort(key=lambda d: ("gpio" not in d.name.lower(), d.name))
        return candidates[0]

    def describe(self) -> str:
        if self.is_recovery:
            label = f"TWRP {self.twrp_version or '?'}"
        else:
            label = "Android (not recovery)"
        parts = [self.serial, self.model or self.codename or "?", label]
        if self.width and self.height:
            parts.append(f"{self.width}x{self.height}")
        return " | ".join(parts)
