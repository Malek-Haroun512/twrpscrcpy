from twrpscrcpy.adb import Adb
from twrpscrcpy.device import InputDevice, RecoveryDevice
from twrpscrcpy.input import EVENT, InputController


def make_device(max_x=4095, max_y=4095):
    touch = InputDevice(
        name="sec_touchscreen",
        node="/dev/input/event1",
        abs_bits=(1 << 53) | (1 << 54),
        prop_bits=1 << 1,
    )
    return RecoveryDevice(
        adb=Adb("adb"),
        serial="ABC",
        inputs=[touch],
        width=1440,
        height=2560,
        touch_max_x=max_x,
        touch_max_y=max_y,
        helper_path="/tmp/twrpscrcpy/fbstream",
    )


def test_raw_coordinates_cover_the_full_range():
    controller = InputController(Adb("adb"), make_device())
    assert controller._raw(0, 0) == (0, 0)
    assert controller._raw(1439, 2559) == (4095, 4095)


def test_raw_coordinates_clamp_garbage():
    controller = InputController(Adb("adb"), make_device())
    assert controller._raw(-100, -100) == (0, 0)
    assert controller._raw(5000, 5000) == (4095, 4095)


def test_raw_coordinates_respect_touch_max():
    controller = InputController(Adb("adb"), make_device(max_x=1079, max_y=1919))
    assert controller._raw(1439, 2559) == (1079, 1919)


def test_linux_input_event_layout():
    packed = EVENT.pack(0, 0, 3, 53, 1234)
    assert len(packed) == 24
    assert EVENT.unpack(packed) == (0, 0, 3, 53, 1234)
