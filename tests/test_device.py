from twrpscrcpy.adb import Adb
from twrpscrcpy.device import InputDevice, RecoveryDevice, _bitmap_value, parse_input_devices

DEVICES_TEXT = """
Input device #0
N: Name="sec_touchscreen"
H: Handlers=event1
B: PROP=2
B: ABS=60000000000000

Input device #1
N: Name="sec_touchkey"
H: Handlers=event0
B: KEY=40000000 0 0

Input device #2
N: Name="gpio_keys"
H: Handlers=event8
B: KEY=100000000000 1C000000000000 0

Input device #3
N: Name="no-handler"
"""


def test_bitmap_is_most_significant_word_first():
    assert _bitmap_value(["1"]) == 1
    assert _bitmap_value(["1", "0"]) == 1 << 64
    assert _bitmap_value(["0", "1"]) == 1


def test_parse_input_devices():
    devices = parse_input_devices(DEVICES_TEXT)
    assert [d.name for d in devices] == ["sec_touchscreen", "sec_touchkey", "gpio_keys"]
    assert devices[0].node == "/dev/input/event1"
    assert devices[0].is_touch
    assert devices[0].is_direct


def test_touch_device_prefers_direct_touchscreen():
    device = RecoveryDevice(adb=Adb("adb"), serial="ABC", inputs=parse_input_devices(DEVICES_TEXT))
    assert device.touch_device().name == "sec_touchscreen"


def test_keys_go_to_the_supporting_node():
    device = RecoveryDevice(adb=Adb("adb"), serial="ABC", inputs=parse_input_devices(DEVICES_TEXT))
    assert device.key_device_for(158).node == "/dev/input/event0"  # BACK
    assert device.key_device_for(116).node == "/dev/input/event8"  # POWER
    assert device.key_device_for(172).node == "/dev/input/event8"  # HOME
    assert device.key_device_for(9999) is None


def test_key_device_prefers_gpio_when_several_match():
    inputs = [
        InputDevice(name="sec_touchkey", node="/dev/input/event0", key_bits=1 << 116),
        InputDevice(name="gpio_keys", node="/dev/input/event8", key_bits=1 << 116),
    ]
    device = RecoveryDevice(adb=Adb("adb"), serial="ABC", inputs=inputs)
    assert device.key_device_for(116).node == "/dev/input/event8"


def test_is_recovery():
    device = RecoveryDevice(adb=Adb("adb"), serial="ABC", twrp_version="3.6.2_9-0")
    assert device.is_recovery
    assert "TWRP 3.6.2_9-0" in device.describe()
    assert not RecoveryDevice(adb=Adb("adb"), serial="ABC").is_recovery
