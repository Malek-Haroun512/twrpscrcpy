"""Entry point for the twrpscrcpy application."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .adb import Adb, AdbError, find_adb
from .device import RecoveryDevice
from .ui import MainWindow


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="twrpscrcpy",
        description="scrcpy-like screen viewer and controller for TWRP recovery.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--serial", help="adb serial of the device")
    parser.add_argument("--adb", default=find_adb(), help="path to the adb binary")
    parser.add_argument("--scale", type=int, default=3, choices=range(1, 5), help="capture downscale (1 = native)")
    parser.add_argument("--fps", type=int, default=30, help="maximum capture frame rate")
    parser.add_argument(
        "--touch-max",
        metavar="XxY",
        help="raw touchscreen maximum coordinates (default 4095x4095)",
    )
    parser.add_argument("--list", action="store_true", help="list connected devices and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    adb = Adb(args.adb, args.serial)

    if args.list:
        try:
            for entry in adb.devices():
                print(entry.label, entry.state)
        except AdbError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0

    app = QApplication(sys.argv[:1])
    app.setApplicationName("twrpscrcpy")

    touch_max = None
    if args.touch_max:
        try:
            raw_x, raw_y = args.touch_max.lower().split("x", 1)
            touch_max = (int(raw_x), int(raw_y))
        except ValueError:
            QMessageBox.critical(None, "twrpscrcpy", "--touch-max expects something like 4095x4095")
            return 2

    try:
        device = RecoveryDevice.connect(adb, touch_max=touch_max)
    except AdbError as exc:
        QMessageBox.critical(None, "twrpscrcpy", "Cannot connect to the device:\n\n" + str(exc))
        return 1

    if not device.is_recovery:
        answer = QMessageBox.question(
            None,
            "twrpscrcpy",
            "The device does not look like it is running TWRP recovery.\n\n"
            "Screen capture needs root access to the framebuffer, which usually only "
            "works in recovery.\n\nContinue anyway?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return 0

    window = MainWindow(adb, device, scale=args.scale, fps=args.fps)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
