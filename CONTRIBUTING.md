# Contributing

Thanks for helping make twrpscrcpy better. Bug reports, TWRP compatibility
notes, and pull requests are all welcome.

## Development setup

```sh
git clone https://github.com/<you>/twrpscrcpy.git
cd twrpscrcpy
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

The GUI tests use Qt's `offscreen` platform, so no display is needed.

## Trying changes against a phone

1. Boot the phone into TWRP recovery and connect it with a data cable.
2. Check that adb sees it: `adb devices -l`.
3. Run `./run.sh` (Linux/macOS) or `run.bat` (Windows), or
   `python -m twrpscrcpy`.

Keep `adb` on your `PATH` or pass `--adb /path/to/adb`.

## Device helper

`native/fbstream.c` is a freestanding ARM Linux program that reads the
framebuffer and writes evdev events. It is cross compiled without the Android
NDK:

```sh
cd native
./build.sh
```

`build.sh` needs clang and lld. On Windows use `build.ps1` with LLVM installed
(`winget install LLVM.LLVM`). The compiled binaries are committed to
`twrpscrcpy/bin`, so normal users and CI do not need a cross compiler.

## Pull requests

- Keep the existing structure and style; the code is small on purpose.
- Add a test for parsing or pure logic changes where practical.
- Run `python -m pytest -q` before opening the PR.
- Describe the device, TWRP version, and Android version you tested with.
- Never include a real device serial or personal data in fixtures.

## License

By contributing you agree that your changes are released under the MIT
license in `LICENSE`.
