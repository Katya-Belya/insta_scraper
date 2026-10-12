"""
Tests for native_host/install_host.py, the development-time host registration.

These check what the installer writes, and above all what it must not write:
the tracked manifest template com.flyer_extractor.host.json is only ever read.
Every generated file is redirected into a temporary directory, so nothing here
touches a real Chrome profile or registry.
"""

import importlib.util
import json
import os
import struct
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "native_host" / "com.flyer_extractor.host.json"

EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"


@pytest.fixture
def install_host(tmp_path, monkeypatch):
    """The installer module, with its output directory moved to tmp_path."""

    spec = importlib.util.spec_from_file_location(
        "install_host", ROOT / "native_host" / "install_host.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "INSTALL_DIR", tmp_path / "installed")
    return module


@pytest.fixture
def chrome_home(tmp_path, monkeypatch):
    """A home directory in which Chrome has created its Linux profile."""

    home = tmp_path / "home"
    (home / ".config" / "google-chrome").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    return home


def test_the_host_name_is_the_one_the_extension_connects_to():
    manifest = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    assert manifest["name"] == "com.flyer_extractor.host"

    background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    assert 'NATIVE_HOST_NAME = "com.flyer_extractor.host"' in background


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX install path")
def test_posix_install_leaves_the_template_alone(install_host, chrome_home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    template_before = TEMPLATE.read_bytes()

    assert install_host.main([EXTENSION_ID, "--python", sys.executable]) == 0

    assert TEMPLATE.read_bytes() == template_before

    installed = chrome_home / ".config/google-chrome/NativeMessagingHosts"
    manifest = json.loads(
        (installed / "com.flyer_extractor.host.json").read_text(encoding="utf-8")
    )

    launcher = install_host.INSTALL_DIR / "flyer_extractor_host.sh"
    assert manifest["path"] == str(launcher)
    assert manifest["allowed_origins"] == [f"chrome-extension://{EXTENSION_ID}/"]
    # Chrome has no "args" field; the launcher carries the interpreter instead.
    assert "args" not in manifest
    assert os.access(launcher, os.X_OK)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="runs a POSIX launcher")
def test_the_posix_launcher_runs_the_host(install_host, chrome_home, monkeypatch):
    """Start the launcher the way Chrome does and ping the host through it."""

    monkeypatch.setattr(sys, "platform", "linux")
    assert install_host.main([EXTENSION_ID, "--python", sys.executable]) == 0

    launcher = install_host.INSTALL_DIR / "flyer_extractor_host.sh"
    body = json.dumps({"type": "ping"}).encode("utf-8")

    # Chrome passes the caller's origin as the first argument.
    completed = subprocess.run(
        [str(launcher), f"chrome-extension://{EXTENSION_ID}/"],
        input=struct.pack("=I", len(body)) + body,
        capture_output=True,
        timeout=30,
        cwd="/",
    )

    assert completed.returncode == 0, completed.stderr
    (length,) = struct.unpack("=I", completed.stdout[:4])
    assert json.loads(completed.stdout[4 : 4 + length]) == {
        "ok": True,
        "message": "pong",
    }


def test_windows_install_writes_outside_the_template(install_host, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    registry = {}

    class Key:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        REG_SZ=1,
        CreateKey=lambda root, path: Key(path),
        SetValueEx=lambda key, name, reserved, kind, value: registry.__setitem__(
            key.path, value
        ),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)

    template_before = TEMPLATE.read_bytes()

    assert install_host.main([EXTENSION_ID, "--python", sys.executable]) == 0

    assert TEMPLATE.read_bytes() == template_before

    manifest_path = install_host.INSTALL_DIR / "com.flyer_extractor.host.json"
    key = r"Software\Google\Chrome\NativeMessagingHosts\com.flyer_extractor.host"
    assert registry == {key: str(manifest_path)}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    launcher = install_host.INSTALL_DIR / "flyer_extractor_host.bat"
    assert manifest["path"] == str(launcher)
    assert "args" not in manifest

    # CRLF exactly, @echo off first, and Chrome's arguments passed through.
    assert launcher.read_bytes() == (
        "@echo off\r\n"
        f'"{sys.executable}" -u "{install_host.HOST_SCRIPT}" %*\r\n'
    ).encode("utf-8")
