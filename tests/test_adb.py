import sys

import pytest

from twrpscrcpy import adb as adb_module
from twrpscrcpy.adb import Adb, AdbError, DeviceEntry, find_adb


def test_find_adb_prefers_path(monkeypatch):
    monkeypatch.setattr(adb_module.shutil, "which", lambda name: f"/custom/{name}")
    assert find_adb() == "/custom/adb"


def test_find_adb_uses_android_home(tmp_path, monkeypatch):
    monkeypatch.setattr(adb_module.shutil, "which", lambda name: None)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    platform_tools = tmp_path / "sdk" / "platform-tools"
    platform_tools.mkdir(parents=True)
    binary = platform_tools / exe
    binary.write_text("")
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "sdk"))
    assert find_adb() == str(binary)


def test_device_entry_label():
    entry = DeviceEntry(serial="ABC", state="recovery", model="SM_G965N", device="crownlte")
    assert entry.label == "ABC SM_G965N (crownlte)"


def test_adb_select_requires_a_device(monkeypatch):
    client = Adb("adb")
    monkeypatch.setattr(client, "devices", lambda: [])
    with pytest.raises(AdbError, match="No adb device found"):
        client.select()
