#!/usr/bin/env python3
"""
The program Chrome launches for the Native Messaging host.

Chrome starts this file directly, by the absolute path recorded in the host
manifest, from a working directory of its own choosing and with none of this
project's environment set up. So the only job here is to make `src` importable
and hand over to src/native_host.py, which is where the protocol and the
pipeline call actually live.

This file is deliberately thin: it is the one part of the host that has to be
an executable script on disk, and a script Chrome runs is an awkward place to
keep logic that wants testing.

Nothing may be printed here. stdout is the Native Messaging wire.
"""

import sys
from pathlib import Path

# The repository root, two levels up from native_host/flyer_extractor_host.py.
# resolve() first, so the path is correct even when Chrome was pointed at a
# symlink to this script.
ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.native_host import main  # noqa: E402 - must follow the sys.path setup

if __name__ == "__main__":
    raise SystemExit(main())
