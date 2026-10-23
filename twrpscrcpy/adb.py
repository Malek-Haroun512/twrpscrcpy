"""Thin wrapper around the adb command line tool."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Hide the console windows that Windows would otherwise flash for every
# adb call made by the GUI.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class AdbError(RuntimeError):
    pass


@dataclass
class DeviceEntry:
    serial: str
    state: str
    product: str = ""
    model: str = ""
    device: str = ""
    transport: str = ""

    @property
    def label(self) -> str:
        parts = [self.serial]
        if self.model:
            parts.append(self.model)
        if self.device:
            parts.append(f"({self.device})")
        return " ".join(parts)


class Adb:
    def __init__(self, adb: str = "adb", serial: str | None = None):
        self.adb = adb
        self.serial = serial

    # -- low level ---------------------------------------------------------
    def _base(self) -> list[str]:
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def _run(self, args: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                self._base() + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
        except FileNotFoundError as exc:
            raise AdbError(f"adb not found: {self.adb}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError("adb command timed out") from exc

    # -- device discovery --------------------------------------------------
    def devices(self) -> list[DeviceEntry]:
        proc = self._run(["devices", "-l"], timeout=15)
        if proc.returncode != 0:
            raise AdbError(proc.stderr.strip() or "adb devices failed")
        entries: list[DeviceEntry] = []
        for line in proc.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(\S+)\s+(\S+)(.*)$", line)
            if not match:
                continue
            serial, state, rest = match.groups()
            info: dict[str, str] = {}
            for token in rest.split():
                if ":" in token:
                    key, _, value = token.partition(":")
                    info[key] = value
            entries.append(
                DeviceEntry(
                    serial=serial,
                    state=state,
                    product=info.get("product", ""),
                    model=info.get("model", ""),
                    device=info.get("device", ""),
                    transport=info.get("transport_id", ""),
                )
            )
        return entries

    def select(self) -> DeviceEntry:
        entries = self.devices()
        usable = [e for e in entries if e.state in ("device", "recovery")]
        if not usable:
            raise AdbError(
                "No adb device found. Connect the phone (recovery mode) and "
                "make sure adb debugging is enabled."
            )
        if self.serial:
            for entry in usable:
                if entry.serial == self.serial:
                    return entry
            raise AdbError(f"Device {self.serial} not found")
        if len(usable) > 1:
            raise AdbError(
                "More than one device is connected, pick one with --serial:\n  "
                + "\n  ".join(e.label for e in usable)
            )
        self.serial = usable[0].serial
        return usable[0]

    # -- device operations -------------------------------------------------
    def shell(self, command: str, timeout: float = 30) -> str:
        proc = self._run(["shell", command], timeout=timeout)
        if proc.returncode != 0:
            raise AdbError(proc.stderr.strip() or proc.stdout.strip() or "shell failed")
        return proc.stdout

    def shell_bool(self, command: str, timeout: float = 15) -> bool:
        try:
            self.shell(command, timeout=timeout)
            return True
        except AdbError:
            return False

    def push(self, local: str, remote: str, timeout: float = 60) -> None:
        proc = self._run(["push", local, remote], timeout=timeout)
        if proc.returncode != 0:
            raise AdbError(proc.stderr.strip() or "adb push failed")

    def popen(self, args: list[str], **kwargs) -> subprocess.Popen:
        kwargs.setdefault("creationflags", _CREATE_NO_WINDOW)
        return subprocess.Popen(self._base() + args, **kwargs)

    def exec_out(self, argv: str) -> subprocess.Popen:
        """Start a command on the device with raw binary stdout."""
        return self.popen(
            ["exec-out", argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

    def shell_stdin(self, argv: str) -> subprocess.Popen:
        """Start a command with a raw binary stdin (no pty)."""
        return self.popen(
            ["shell", "-T", argv],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=0,
        )


def find_adb() -> str:
    """Locate adb on PATH or in the usual Android SDK install locations."""
    found = shutil.which("adb")
    if found:
        return found

    exe = "adb.exe" if sys.platform == "win32" else "adb"
    candidates: list[Path] = []
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "platform-tools" / exe)

    home = Path.home()
    if sys.platform == "win32":
        for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            root = os.environ.get(variable)
            if root:
                candidates.append(Path(root) / "Android" / "Sdk" / "platform-tools" / exe)
        candidates.append(home / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / exe)
    elif sys.platform == "darwin":
        candidates += [
            home / "Library" / "Android" / "sdk" / "platform-tools" / exe,
            Path("/opt/homebrew/bin") / exe,
            Path("/usr/local/bin") / exe,
        ]
    else:
        candidates += [
            home / "Android" / "Sdk" / "platform-tools" / exe,
            Path("/usr/bin") / exe,
            Path("/usr/local/bin") / exe,
            Path("/snap/bin") / exe,
        ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return "adb"
