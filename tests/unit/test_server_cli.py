import sys

import pytest

from robot_jsonrpcremote_server.__main__ import _parse_addresses, build_arg_parser, run

# --- _parse_addresses ------------------------------------------------------


def test_parse_addresses_none_and_empty() -> None:
    assert _parse_addresses(None) is None
    assert _parse_addresses("") is None
    assert _parse_addresses("   ") is None


def test_parse_addresses_splits_and_strips() -> None:
    assert _parse_addresses("a, b ,c") == ["a", "b", "c"]
    assert _parse_addresses("127.0.0.1") == ["127.0.0.1"]


# --- argument parsing ------------------------------------------------------


def test_libraries_are_positional() -> None:
    args = build_arg_parser().parse_args(["MyLib", "OtherLib"])
    assert args.libraries == ["MyLib", "OtherLib"]
    assert args.mode == "tcp"


def test_port_and_bind() -> None:
    args = build_arg_parser().parse_args(["--port", "9000", "--bind", "0.0.0.0", "--bind", "127.0.0.1", "Lib"])
    assert args.port == 9000
    assert args.addresses == ["0.0.0.0", "127.0.0.1"]


def test_robot_options() -> None:
    args = build_arg_parser().parse_args(
        ["--variable", "A:1", "--variable", "B:2", "-V", "vars.py", "-d", "out", "-P", "d1", "-P", "d2", "Lib"]
    )
    assert args.variable == ["A:1", "B:2"]
    assert args.variablefile == ["vars.py"]
    assert args.outputdir == "out"
    assert args.pythonpath == ["d1", "d2"]


def test_mode_aliases() -> None:
    assert build_arg_parser().parse_args(["--pipe", "Lib"]).mode == "pipe"
    assert build_arg_parser().parse_args(["--stdio", "Lib"]).mode == "stdio"
    assert build_arg_parser().parse_args(["--tcp", "Lib"]).mode == "tcp"


# --- run() rejects unsupported modes cleanly -------------------------------


@pytest.mark.parametrize("flag", ["--pipe", "--stdio"])
def test_run_rejects_unsupported_mode(flag: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["robot-jsonrpcremote-server", flag, "MyLib"])
    with pytest.raises(SystemExit) as excinfo:
        run()
    assert excinfo.value.code == 2
