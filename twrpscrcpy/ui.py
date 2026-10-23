"""Qt user interface for twrpscrcpy."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QImage, QKeySequence, QPainter, QTransform
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QWidget,
)

from .adb import Adb
from .capture import CaptureWorker
from .device import RecoveryDevice
from .input import KEY_BACK, KEY_HOME, KEY_POWER, KEY_VOLUMEDOWN, KEY_VOLUMEUP, InputController


def lock_overlay_visible(image: QImage | None) -> bool:
    """Detect TWRP's screensaver: a grey padlock plus the orange slider handle.

    Both shapes are sampled from the already rendered frame, so this costs no
    device round trip. Requiring the grey padlock and the orange handle at the
    same time keeps it from matching ordinary TWRP pages.
    """
    if image is None or image.isNull():
        return False
    img = image.convertToFormat(QImage.Format.Format_RGB32)
    width, height = img.width(), img.height()
    if width < 32 or height < 32:
        return False
    stride = img.bytesPerLine() // 4
    pixels = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(height, stride, 4)
    blue = pixels[:, :width, 0].astype(np.int16)
    green = pixels[:, :width, 1].astype(np.int16)
    red = pixels[:, :width, 2].astype(np.int16)

    grey = (abs(red - green) <= 12) & (abs(green - blue) <= 12) & (red >= 105) & (red <= 205)
    orange = (red > 170) & (green > 100) & (green < 215) & (blue < 100)

    center = grey[int(height * 0.33):int(height * 0.52), int(width * 0.38):int(width * 0.62)]
    handle = orange[int(height * 0.82):int(height * 0.89), int(width * 0.06):int(width * 0.33)]
    if center.size < 100 or handle.size < 100:
        return False
    return bool(center.mean() > 0.35 and handle.mean() > 0.15)



class ScreenView(QWidget):
    """Draws the streamed recovery screen and turns mouse input into touches."""

    def __init__(self, controller: InputController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self._image: QImage | None = None
        self._dev_width = 0
        self._dev_height = 0
        self._rotation = 0
        self._transform = QTransform()
        self._message = "Waiting for the device..."
        self._pressed = False
        self.setMinimumSize(240, 320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # -- state -------------------------------------------------------------
    def set_frame(self, image: QImage, dev_width: int, dev_height: int) -> None:
        self._image = image
        self._dev_width = max(1, dev_width)
        self._dev_height = max(1, dev_height)
        self._message = ""
        self.update()

    def set_message(self, message: str) -> None:
        self._message = message
        self.update()

    def rotate(self, degrees: int = 90) -> None:
        self._rotation = (self._rotation + degrees) % 360
        self.update()

    @property
    def rotation(self) -> int:
        return self._rotation

    @property
    def image(self) -> QImage | None:
        return self._image

    # -- geometry ----------------------------------------------------------
    def _update_transform(self) -> None:
        if self._image is None or self._image.isNull():
            self._transform = QTransform()
            return
        src_w = self._image.width()
        src_h = self._image.height()
        avail_w = max(1, self.width())
        avail_h = max(1, self.height())
        if self._rotation in (90, 270):
            scale = min(avail_w / src_h, avail_h / src_w)
        else:
            scale = min(avail_w / src_w, avail_h / src_h)
        transform = QTransform()
        transform.translate(avail_w / 2, avail_h / 2)
        transform.rotate(self._rotation)
        transform.scale(scale, scale)
        transform.translate(-src_w / 2, -src_h / 2)
        self._transform = transform

    def _to_device(self, pos: QPointF) -> tuple[float, float] | None:
        if self._image is None or self._image.isNull():
            return None
        inverse, ok = self._transform.inverted()
        if not ok:
            return None
        point = inverse.map(pos)
        if not (0 <= point.x() < self._image.width() and 0 <= point.y() < self._image.height()):
            return None
        x = point.x() * self._dev_width / self._image.width()
        y = point.y() * self._dev_height / self._image.height()
        return x, y

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0c0c10"))
        self._update_transform()
        if self._image is not None and not self._image.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.setTransform(self._transform)
            painter.drawImage(0, 0, self._image)
            painter.resetTransform()
        else:
            painter.setPen(QColor("#9aa0a6"))
            font = painter.font()
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(24, 24, -24, -24),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._message,
            )

    # -- input -------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.controller.key(KEY_BACK)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._to_device(event.position())
        if point is None:
            return
        self._pressed = True
        self.controller.cancel_gestures()
        self.controller.touch_down(*point)

    def mouseMoveEvent(self, event) -> None:
        if not self._pressed:
            return
        point = self._to_device(event.position())
        if point is not None:
            self.controller.touch_move(*point)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.controller.touch_up()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.controller.scroll(-1 if delta > 0 else 1)


class MainWindow(QMainWindow):
    def __init__(self, adb: Adb, device: RecoveryDevice, scale: int = 3, fps: int = 30):
        super().__init__()
        self.adb = adb
        self.device = device
        self.controller = InputController(adb, device)
        self.capture: CaptureWorker | None = None
        self.scale = scale
        self.fps = fps
        self._frame_seq = 0
        self._last_wake = 0.0
        self._warning_shown = False

        self.view = ScreenView(self.controller)
        self.setCentralWidget(self.view)
        self.setWindowTitle(f"twrpscrcpy - {device.serial}")
        self.resize(520, 900)

        self._build_toolbar()
        self._build_status()
        self._install_shortcuts()
        self._keep_awake_timer = QTimer(self)
        self._keep_awake_timer.setInterval(15_000)
        self._keep_awake_timer.timeout.connect(self._keep_awake)
        self._keep_awake_timer.start()
        self.start_capture()
        self._auto_woke = False
        QTimer.singleShot(2500, self._auto_wake)

    # -- toolbar -----------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = QToolBar("Controls", self)
        bar.setMovable(False)
        self.addToolBar(bar)

        def add(text: str, tip: str, slot):
            action = QAction(text, self)
            action.setToolTip(tip)
            action.triggered.connect(slot)
            bar.addAction(action)
            return action

        add("Power", "Power key", lambda: self._key(KEY_POWER))
        add("Vol-", "Volume down", lambda: self._key(KEY_VOLUMEDOWN))
        add("Vol+", "Volume up", lambda: self._key(KEY_VOLUMEUP))
        add("Back", "Back key (Esc)", lambda: self._key(KEY_BACK))
        add("Home", "Home key (return to the TWRP main menu)", lambda: self._key(KEY_HOME))
        bar.addSeparator()
        add("Wake", "Wake the screen and swipe the unlock slider", self.wake)
        add("Rotate", "Rotate the preview 90 degrees", lambda: self.view.rotate(90))
        bar.addSeparator()

        add("Screenshot", "Save the current frame as PNG (Ctrl+S)", self.save_screenshot)
        add("Reconnect", "Restart the capture stream (F5)", self.start_capture)

    def _build_status(self) -> None:
        self.device_label = QLabel(self.device.describe())
        self.stats_label = QLabel("starting...")
        self.statusBar().addWidget(self.device_label, 1)

        self.scale_box = QComboBox()
        for value, label in ((1, "1x full"), (2, "2x"), (3, "3x"), (4, "4x fast")):
            self.scale_box.addItem(label, value)
        index = self.scale_box.findData(self.scale)
        self.scale_box.setCurrentIndex(index if index >= 0 else 2)
        self.scale_box.setToolTip("Capture quality: lower is sharper but slower")
        self.scale_box.currentIndexChanged.connect(self._scale_changed)
        self.statusBar().addPermanentWidget(self.scale_box)

        self.awake_box = QCheckBox("stay awake")
        self.awake_box.setChecked(True)
        self.awake_box.setToolTip("Keep tapping the screen so TWRP does not lock it")
        self.statusBar().addPermanentWidget(self.awake_box)
        self.statusBar().addPermanentWidget(self.stats_label)

    def _install_shortcuts(self) -> None:
        back = QAction(self)
        back.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        back.triggered.connect(lambda: self._key(KEY_BACK))
        self.addAction(back)

        restart = QAction(self)
        restart.setShortcut(QKeySequence(Qt.Key.Key_F5))
        restart.triggered.connect(self.start_capture)
        self.addAction(restart)

        shot = QAction(self)
        shot.setShortcut(QKeySequence("Ctrl+S"))
        shot.triggered.connect(self.save_screenshot)
        self.addAction(shot)

        fullscreen = QAction(self)
        fullscreen.setShortcut(QKeySequence(Qt.Key.Key_F11))
        fullscreen.triggered.connect(self._toggle_fullscreen)
        self.addAction(fullscreen)

    # -- actions -----------------------------------------------------------
    def _key(self, code: int) -> None:
        import threading

        threading.Thread(target=self.controller.key, args=(code,), daemon=True).start()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def wake(self) -> None:
        """Turn the panel on and dismiss TWRP's lock screen when it is showing."""
        now = time.monotonic()
        if now - self._last_wake < 3.0:
            return
        self._last_wake = now
        self._keep_awake_timer.start()  # restart the check phase
        brightness = self.device.screen_brightness()
        locked = lock_overlay_visible(self.view.image)
        if brightness == 0:
            self._key(KEY_POWER)
            # The panel and touch controller need a moment; wait for the lock
            # overlay to show up instead of guessing a fixed delay.
            QTimer.singleShot(2500, self._unlock_when_ready)
            return
        if locked:
            self._start_unlock()
            return
        self.statusBar().showMessage("The screen is already awake", 2500)

    def _unlock_when_ready(self, tries: int = 0) -> None:
        """Poll the streamed frame for TWRP's lock overlay, then swipe."""
        if lock_overlay_visible(self.view.image):
            self._start_unlock()
        elif tries < 8:
            QTimer.singleShot(500, lambda: self._unlock_when_ready(tries + 1))

    def _start_unlock(self) -> None:
        self.controller.unlock_swipe(attempts=1)
        QTimer.singleShot(4000, self._unlock_if_locked)

    def _unlock_if_locked(self) -> None:
        if lock_overlay_visible(self.view.image):
            self.controller.unlock_swipe(attempts=1)

    def _auto_wake(self) -> None:
        """TWRP keeps the panel off after its timeout: wake it when we connect."""
        if self._auto_woke:
            return
        self._auto_woke = True
        if self.device.screen_brightness() == 0 or lock_overlay_visible(self.view.image):
            self.wake()

    def _keep_awake(self) -> None:
        if not self.awake_box.isChecked():
            return
        if lock_overlay_visible(self.view.image):
            self.wake()
            return
        if time.monotonic() - self._last_wake < 6.0:
            return  # an unlock or wake is still in flight
        if self.device.screen_brightness() == 0:
            self.wake()
            return
        self.controller.nudge()

    def _scale_changed(self) -> None:
        value = self.scale_box.currentData()
        if value and value != self.scale:
            self.scale = int(value)
            self.start_capture()

    def save_screenshot(self) -> None:
        image = self.view.image
        if image is None:
            self.statusBar().showMessage("Nothing to save yet", 3000)
            return
        pictures = Path.home() / "Pictures"
        if not pictures.is_dir():
            pictures = Path.home()
        default = str(pictures / time.strftime("twrp-%Y%m%d-%H%M%S.png"))
        path, _ = QFileDialog.getSaveFileName(self, "Save screenshot", default, "PNG image (*.png)")
        if not path:
            return
        if image.save(path, "PNG"):
            self.statusBar().showMessage(f"Saved {path}", 5000)
        else:
            QMessageBox.warning(self, "twrpscrcpy", "Could not save the image")

    # -- capture -----------------------------------------------------------
    def start_capture(self) -> None:
        try:
            if not self.device.helper_ready():
                self.device.install_helper()
        except Exception as exc:  # noqa: BLE001 - shown to the user
            QMessageBox.warning(self, "twrpscrcpy", f"Could not install the helper:\n{exc}")
            return
        if self.capture is not None:
            self.capture.stop()
            self.capture.wait(1500)
            self.capture = None
        self.view.set_message("Connecting to the capture helper...")
        self.stats_label.setText("starting...")
        worker = CaptureWorker(self.adb, self.device, scale=self.scale, fps=self.fps)
        worker.frame_ready.connect(self._on_frame)
        worker.stats.connect(self._on_stats)
        worker.failed.connect(self._on_failed)
        self.capture = worker
        worker.start()

    def _on_frame(self, image: QImage, dev_width: int, dev_height: int) -> None:
        self._frame_seq += 1
        self.view.set_frame(image, dev_width, dev_height)
        self.controller.set_geometry(dev_width, dev_height)

    def _on_stats(self, fps: float, dev_width: int, dev_height: int) -> None:
        self.stats_label.setText(f"{dev_width}x{dev_height}  |  {fps:0.1f} fps")

    def _on_failed(self, message: str) -> None:
        self.view.set_message(
            "Capture stopped:\n" + message + "\n\nPress F5 or Reconnect to try again."
        )
        self.stats_label.setText("disconnected")
        if not self._warning_shown:
            self._warning_shown = True
            QMessageBox.warning(self, "twrpscrcpy", "Capture stopped:\n" + message)

    # -- lifecycle ---------------------------------------------------------
    def closeEvent(self, event) -> None:
        if self.capture is not None:
            self.capture.stop()
            self.capture.wait(1500)
        self.controller.close()
        super().closeEvent(event)
