import pytest

from twrpscrcpy.__main__ import parse_args


def test_cli_defaults():
    args = parse_args([])
    assert args.scale == 3
    assert args.fps == 30
    assert args.serial is None
    assert args.list is False


def test_cli_scale_is_validated():
    assert parse_args(["--scale", "1"]).scale == 1
    with pytest.raises(SystemExit):
        parse_args(["--scale", "9"])


def test_cli_accepts_touch_max():
    assert parse_args(["--touch-max", "1079x1919"]).touch_max == "1079x1919"


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(["--version"])
    assert exc.value.code == 0
    assert "twrpscrcpy 1.0.0" in capsys.readouterr().out
