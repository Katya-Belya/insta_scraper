#!/usr/bin/env python3
"""
Register the Native Messaging host with Chrome on this machine.

Chrome only launches a host it has been told about, and it is told through a
manifest stored in a per-user directory (or, on Windows, a registry key). The
manifest has to carry two things that differ on every machine: the absolute
path to native_host/flyer_extractor_host.py, and the id Chrome assigned to the
unpacked extension.

This fills both in from com.flyer_extractor.host.json and writes the result
where Chrome looks. The template itself is only ever read: everything this
script generates goes into native_host/installed/, which is gitignored.

    python native_host/install_host.py <extension-id>

The extension id is the 32-letter string shown under "Flyer Event Extractor"
at chrome://extensions with Developer mode on. It changes if the extension is
removed and loaded again, so rerun this when it does.

This is a development convenience, not an installer: it registers the host for
the user running it, for a repository checkout that stays where it is. Real
packaging is deliberately out of scope for the prototype.
"""

import argparse
import json
import re
import shlex
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent

# The manifest with the placeholders still in it, which this script fills in.
TEMPLATE_PATH = HERE / "com.flyer_extractor.host.json"

# The Python program that runs the host.
HOST_SCRIPT = HERE / "flyer_extractor_host.py"

# Where the generated, machine-specific files go: the launcher Chrome starts
# and, on Windows, the filled-in manifest the registry points at. Never the
# template's own directory entry, so installing cannot overwrite the template.
INSTALL_DIR = HERE / "installed"

# Chrome builds an extension id from the letters a-p only, and it is always 32
# of them. Checking that here turns a typo into a message rather than into a
# host Chrome silently never launches.
EXTENSION_ID = re.compile(r"[a-p]{32}")

# Where each browser keeps its per-user host manifests, relative to $HOME.
#
# Chrome and Chromium read different directories, and a user may have either,
# so the manifest is written to every one of these that already exists.
MANIFEST_DIRECTORIES = {
    "linux": [
        ".config/google-chrome/NativeMessagingHosts",
        ".config/chromium/NativeMessagingHosts",
        ".config/google-chrome-beta/NativeMessagingHosts",
    ],
    "darwin": [
        "Library/Application Support/Google/Chrome/NativeMessagingHosts",
        "Library/Application Support/Chromium/NativeMessagingHosts",
    ],
}


def write_launcher(python_executable: str, windows: bool) -> Path:
    """
    Write the small program Chrome starts, which runs the host script.

    The host is launched through the same interpreter this script is run with,
    so a project virtual environment stays in use: Chrome inherits none of the
    shell's environment, and a host started as bare `python3` would be the
    system interpreter, without Pillow or pytesseract.

    A host manifest has no field for extra arguments - Chrome runs `path` with
    only the caller's origin on the command line - so the interpreter and the
    script are tied together here instead. It also avoids depending on the
    script's executable bit and on the shebang being honored, and on Windows,
    where Chrome cannot run a .py file directly, it is the only way in.

    Chrome's own arguments are passed through; the host ignores them.
    """

    INSTALL_DIR.mkdir(exist_ok=True)

    if windows:
        launcher = INSTALL_DIR / "flyer_extractor_host.bat"
        # "@echo off" is not cosmetic: an echoed command would land on stdout,
        # which is the Native Messaging wire. -u keeps replies unbuffered.
        launcher.write_text(
            "@echo off\r\n"
            f'"{python_executable}" -u "{HOST_SCRIPT}" %*\r\n',
            encoding="utf-8",
            newline="",
        )
    else:
        launcher = INSTALL_DIR / "flyer_extractor_host.sh"
        launcher.write_text(
            "#!/bin/sh\n"
            f'exec {shlex.quote(python_executable)} -u {shlex.quote(str(HOST_SCRIPT))} "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)

    return launcher


def build_manifest(extension_id: str, launcher: Path) -> dict:
    """Fill the template in for this machine, without changing the template."""

    manifest = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    manifest["path"] = str(launcher)
    manifest["allowed_origins"] = [f"chrome-extension://{extension_id}/"]

    return manifest


def install_posix(manifest: dict) -> list[Path]:
    """Write the manifest into every Chrome profile directory that exists."""

    home = Path.home()
    directories = MANIFEST_DIRECTORIES.get(sys.platform)

    if directories is None:
        raise SystemExit(
            f"Unsupported platform: {sys.platform}. "
            "Copy the manifest into Chrome's NativeMessagingHosts directory "
            "by hand."
        )

    written = []

    for relative in directories:
        directory = home / relative

        # Only profiles Chrome has actually created are written to. Creating
        # the others would leave manifests for browsers that are not installed.
        if not directory.parent.exists():
            continue

        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{manifest['name']}.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        written.append(path)

    return written


def install_windows(manifest: dict) -> list[Path]:
    """
    Write the manifest into native_host/installed/ and point the registry at it.

    Windows Chrome does not read a directory: it reads
    HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts\\<name>, whose default
    value is the full path of the manifest file.
    """

    import winreg

    INSTALL_DIR.mkdir(exist_ok=True)
    path = INSTALL_DIR / f"{manifest['name']}.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    key_path = rf"Software\Google\Chrome\NativeMessagingHosts\{manifest['name']}"

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, str(path))

    return [path]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Register the flyer extraction Native Messaging host."
    )
    parser.add_argument(
        "extension_id",
        help="The extension's id from chrome://extensions (32 letters a-p)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help=(
            "Interpreter Chrome should run the host with "
            "(default: the one running this script)"
        ),
    )

    args = parser.parse_args(argv)
    extension_id = args.extension_id.strip()

    if not EXTENSION_ID.fullmatch(extension_id):
        print(
            f"Error: {extension_id!r} is not a Chrome extension id. "
            "Copy it from chrome://extensions.",
            file=sys.stderr,
        )
        return 1

    python_executable = shutil.which(args.python) or args.python

    if not Path(python_executable).exists():
        print(f"Error: no such interpreter: {python_executable}", file=sys.stderr)
        return 1

    windows = sys.platform.startswith("win")
    launcher = write_launcher(python_executable, windows)
    manifest = build_manifest(extension_id, launcher)

    if windows:
        written = install_windows(manifest)
    else:
        written = install_posix(manifest)

    if not written:
        print(
            "Error: found no Chrome profile directory to install into. "
            "Start Chrome once, then run this again.",
            file=sys.stderr,
        )
        return 1

    for path in written:
        print(f"Registered {manifest['name']} at {path}")

    print(f"Host command: {launcher} -> {python_executable} {HOST_SCRIPT}")
    print("Reload the extension at chrome://extensions to pick this up.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
