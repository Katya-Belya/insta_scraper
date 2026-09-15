"""
The smallest Chrome native messaging host this project can have: ping -> pong.

Milestone 1 of the native messaging POC. Chrome launches this process itself,
so nothing has to be started by hand - in particular `python -m src.server`
does not have to be running. No flyer, no image, no OCR: this host exists only
to prove that the extension can start a Python process and get an answer back.

The protocol Chrome speaks on the pipe is:

    <4 bytes: message length, unsigned 32-bit, native byte order>
    <that many bytes: the message, as UTF-8 JSON>

in both directions. Nothing else may ever reach stdout - one stray print, one
Windows CRLF translation, and Chrome reads the bytes as a length prefix and
drops the connection. So stdout is used through its binary buffer only, and
everything meant for a human goes to stderr, which Chrome writes to its own
log and never parses.

The one request handled here is:

    {"action": "ping"}   ->   {"ok": true, "message": "pong"}

Run by Chrome through native_host/run_host.bat on Windows; see
native_host/README.md for how to register it.
"""

import json
import struct
import sys

# The response to {"action": "ping"}. The whole point of this milestone.
PONG_RESPONSE = {"ok": True, "message": "pong"}

# Chrome's own cap on a single message from the host (1 MB). Nothing here comes
# close, but a message above it would be dropped by Chrome rather than
# delivered, so it is better to notice that here than in the extension.
MAX_MESSAGE_BYTES = 1024 * 1024

# "=I" is an unsigned 32-bit integer in native byte order with no padding,
# which is exactly how Chrome writes and expects the length prefix.
LENGTH_FORMAT = "=I"
LENGTH_BYTES = struct.calcsize(LENGTH_FORMAT)


def log(message):
    """Write a debugging line to stderr.

    stdout belongs to the protocol. stderr is the only channel a native
    messaging host can safely talk on, and Chrome collects it in its log.
    """
    print(f"[{__name__}] {message}", file=sys.stderr, flush=True)


def use_binary_stdio():
    """Stop Windows from translating the bytes on stdin and stdout.

    On Windows the standard streams default to text mode, where a 0x0A byte on
    the way out becomes 0x0D 0x0A. Both the length prefix and the JSON body are
    binary as far as that translation is concerned, so a message containing
    either byte would be corrupted. Everywhere else this is already true and
    the call is skipped.
    """
    if sys.platform != "win32":
        return

    import msvcrt
    import os

    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


def read_message():
    """Read one length-prefixed message from Chrome.

    Returns the decoded message, or None when Chrome has closed the pipe -
    which is how a native messaging host is told to shut down.
    """
    raw_length = sys.stdin.buffer.read(LENGTH_BYTES)

    # Chrome closed the pipe: no more messages are coming. A short read means
    # the same thing - the process is being torn down mid-prefix.
    if len(raw_length) < LENGTH_BYTES:
        return None

    (length,) = struct.unpack(LENGTH_FORMAT, raw_length)
    payload = sys.stdin.buffer.read(length)

    if len(payload) < length:
        raise ValueError(
            f"message ended early: expected {length} bytes, read {len(payload)}"
        )

    return json.loads(payload.decode("utf-8"))


def write_message(message):
    """Write one length-prefixed JSON message back to Chrome."""
    encoded = json.dumps(message).encode("utf-8")

    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ValueError(
            f"response is {len(encoded)} bytes, over Chrome's "
            f"{MAX_MESSAGE_BYTES} byte limit"
        )

    # Prefix and body go out together and are flushed at once: Chrome is
    # blocked waiting on them, and a half-written message would hang it.
    sys.stdout.buffer.write(struct.pack(LENGTH_FORMAT, len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def handle(message):
    """Answer one request.

    The only action this milestone knows is "ping". Anything else is answered
    rather than ignored, so the extension sees a real reply instead of the
    silence a crashed host would produce.
    """
    if not isinstance(message, dict):
        return {
            "ok": False,
            "error": "invalid_message",
            "message": "Expected a JSON object.",
        }

    action = message.get("action")

    if action == "ping":
        return dict(PONG_RESPONSE)

    return {
        "ok": False,
        "error": "unknown_action",
        "message": f"Unknown action: {action!r}",
    }


def main():
    use_binary_stdio()
    log("host started")

    while True:
        try:
            message = read_message()
        except (ValueError, UnicodeDecodeError) as error:
            # The request could not be read at all, so there is nothing to
            # answer and no way to know where the next message starts.
            log(f"unreadable request: {error}")
            return 1

        if message is None:
            log("stdin closed, exiting")
            return 0

        log(f"request: {message}")
        response = handle(message)
        log(f"response: {response}")
        write_message(response)


if __name__ == "__main__":
    sys.exit(main())
