from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from twrpscrcpy.ui import lock_overlay_visible

W, H = 400, 800


def blank():
    image = QImage(W, H, QImage.Format.Format_RGB32)
    image.fill(QColor(30, 30, 30))
    return image


def painted(center=False, handle=False):
    image = blank()
    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    if center:
        painter.setBrush(QColor(150, 150, 150))
        painter.drawRect(QRect(152, 264, 96, 152))
    if handle:
        painter.setBrush(QColor(255, 153, 0))
        painter.drawRect(QRect(24, 656, 108, 56))
    painter.end()
    return image


def test_lock_overlay_needs_both_shapes():
    assert lock_overlay_visible(painted(center=True, handle=True))
    assert not lock_overlay_visible(painted(center=True, handle=False))
    assert not lock_overlay_visible(painted(center=False, handle=True))
    assert not lock_overlay_visible(blank())


def test_lock_overlay_ignores_dark_grey():
    image = blank()
    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(100, 100, 100))
    painter.drawRect(QRect(152, 264, 96, 152))
    painter.setBrush(QColor(255, 153, 0))
    painter.drawRect(QRect(24, 656, 108, 56))
    painter.end()
    assert not lock_overlay_visible(image)


def test_lock_overlay_handles_empty_image():
    assert not lock_overlay_visible(None)
    assert not lock_overlay_visible(QImage())
