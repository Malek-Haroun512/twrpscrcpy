#!/bin/sh
# Start twrpscrcpy (requires PySide6, numpy, adb in PATH).
cd "$(dirname "$0")"
exec python3 -m twrpscrcpy "$@"
