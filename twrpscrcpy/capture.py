"""Framebuffer streaming from the recovery helper."""

from __future__ import annotations

import struct
import time

import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .adb import Adb
from .device import RecoveryDevice

HEADER = struct.Struct("<4sIIIIIII")  # magic, w, h, runs, scale, yoffset, dev_w, dev_h
MAGIC_FRAME = b"TWF1"
MAGIC_KEEPALIVE = b"TWF2"


class CaptureWorker(QThread):
    frame_ready = Signal(QImage, int, int)  # image, device width, device height
    stats = Signal(float, int, int)  # fps, device width, device height
    failed = Signal(str)

    def __init__(self, adb: Adb, device: RecoveryDevice, scale: int = 2, fps: int = 30):
        super().__init__()
        self.adb = adb
        self.device = device
        self.scale = max(1, min(8, scale))
        self.target_fps = max(1, min(60, fps))
        self._stop = False
        self._proc = None

    # -- helpers -----------------------------------------------------------
    def _read_exact(self, stream, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = stream.read(size - len(chunks))
            if not chunk:
                raise EOFError
            chunks += chunk
        return bytes(chunks)

    def stop(self) -> None:
        self._stop = True
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    # -- thread body -------------------------------------------------------
    def run(self) -> None:
        argv = (
            f"{self.device.helper_path} --fb={self.device.fb_path} "
            f"--scale={self.scale} --fps={self.target_fps}"
        )
        try:
            self._proc = self.adb.exec_out(argv)
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        proc = self._proc
        stdout = proc.stdout

        frames = 0
        last_stats = time.monotonic()
        try:
            while not self._stop:
                header = self._read_exact(stdout, HEADER.size)
                magic, width, height, runs, scale, _yoff, dev_w, dev_h = HEADER.unpack(header)
                if magic == MAGIC_KEEPALIVE:
                    pass
                elif magic == MAGIC_FRAME:
                    payload = self._read_exact(stdout, runs * 4)
                    image = self._decode(payload, width, height, runs)
                    if image is not None:
                        self.frame_ready.emit(image, dev_w, dev_h)
                else:
                    raise ValueError(f"bad frame header {magic!r}")
                frames += 1
                now = time.monotonic()
                if now - last_stats >= 0.8:
                    self.stats.emit(frames / (now - last_stats), dev_w, dev_h)
                    frames = 0
                    last_stats = now
        except (EOFError, OSError, ValueError):
            pass
        finally:
            try:
                proc.kill()
            except OSError:
                pass
            message = ""
            if not self._stop:
                try:
                    err = proc.stderr.read().decode("utf-8", "replace").strip()
                except (OSError, ValueError):
                    err = ""
                code = proc.poll()
                message = err or f"capture helper exited ({code})"
                if not message:
                    message = "capture stream ended"
                self.failed.emit(message)

    @staticmethod
    def _decode(payload: bytes, width: int, height: int, runs: int) -> QImage | None:
        if width == 0 or height == 0 or runs == 0:
            return None
        data = np.frombuffer(payload, dtype="<u2")
        counts = data[0::2].astype(np.int64)
        colors = data[1::2]
        pixels = np.repeat(colors, counts)
        if pixels.size != width * height:
            return None
        image = QImage(
            pixels.tobytes(),
            width,
            height,
            width * 2,
            QImage.Format.Format_RGB16,
        )
        return image.copy()
