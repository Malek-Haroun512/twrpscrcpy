import struct

from twrpscrcpy.capture import CaptureWorker


def test_decode_rle_frame():
    # Two runs: three red pixels then one green pixel, 2x2 image.
    payload = struct.pack("<4H", 3, 0xF800, 1, 0x07E0)
    image = CaptureWorker._decode(payload, 2, 2, 2)
    assert image is not None
    assert (image.width(), image.height()) == (2, 2)
    assert image.pixelColor(0, 0).red() == 255
    assert image.pixelColor(1, 0).red() == 255
    assert image.pixelColor(0, 1).red() == 255
    assert image.pixelColor(1, 1).green() == 255


def test_decode_rejects_wrong_pixel_count():
    payload = struct.pack("<2H", 1, 0xF800)
    assert CaptureWorker._decode(payload, 4, 4, 1) is None


def test_decode_rejects_empty_frame():
    assert CaptureWorker._decode(b"", 0, 0, 0) is None
