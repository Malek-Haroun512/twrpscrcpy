"""Launch twrpscrcpy as a real ``__main__`` module for PyInstaller."""

from twrpscrcpy.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
