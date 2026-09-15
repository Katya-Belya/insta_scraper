"""
A Chrome Native Messaging host around the existing extraction pipeline.

This is the transport that replaces src/server.py for the popup. The extension
cannot run Tesseract, and it should not have to ask the user to start anything:
Chrome launches this process itself the moment the popup sends it a message,
and closes it again when the answer comes back.

No extraction logic lives here. Like the HTTP server before it, this module
only moves bytes: it reads one message from stdin, writes the flyer to a
temporary file, hands that file to src.pipeline.extract_event_date(), and
writes the result back to stdout.

Chrome does not run this module directly. It runs native_host/
flyer_extractor_host.py, which puts the repository root on sys.path and calls
main() below.

## The wire format

Native Messaging frames every message with its length, so stdin and stdout are
binary and carry no newlines of their own:

    [4 bytes: message length, native byte order][that many bytes of UTF-8 JSON]

Because stdout *is* the wire, nothing else may ever be written to it. A stray
print() would be read as a length prefix and break the connection. Diagnostics
go to stderr, which Chrome collects in its own log.

## The messages

Milestone 1, which proves Chrome can launch this process at all:

    ->  {"type": "ping"}
    <-  {"ok": true, "message": "pong"}

Milestone 2, one flyer through the pipeline:

    ->  {"type": "extract",
         "filename": "cherry_blossom_market.jpeg",
         "imageBase64": "<the image bytes, base64>"}
    <-  {"ok": true,
         "result": {"filename": "...", "eventDate": "2027-03-27",
                    "status": "ok", "needsReview": false}}

`result` is exactly what flyer_result_to_popup_data() produces, so a flyer
described by this host and a flyer described by a command-line run carry the
same four fields.

Anything that goes wrong answers in one shape rather than dying, so the popup
always has something to show:

    <-  {"ok": false, "error": "<machine-readable reason>", "message": "..."}
"""

import base64
import binascii
import json
import struct
import sys
import tempfile
import traceback
from pathlib import Path


# The length prefix is four bytes in the machine's own byte order, which is
# what Chrome writes and expects. "=I" is that: standard 4-byte size, native
# order, no struct padding.
LENGTH_FORMAT = "=I"
LENGTH_BYTES = struct.calcsize(LENGTH_FORMAT)

# Flyers are photographs, not archives. The cap matches MAX_UPLOAD_BYTES in
# src/server.py and keeps a malformed message from being decoded into memory
# unbounded. It applies to the decoded image, not to the base64 text.
MAX_IMAGE_BYTES = 20 * 1024 * 1024

# Chrome refuses to deliver a message larger than this to a host, so a flyer
# whose base64 is bigger never reaches read_message() at all. Named here so
# the limitation is written down next to the code it governs.
MAX_MESSAGE_BYTES = 64 * 1024 * 1024


def supported_extensions():
    """
    The image types the pipeline accepts.

    Imported from src.pipeline so this host and the command-line runner can
    never disagree about what counts as a flyer.

    Imported inside the function for the same reason as run_extraction below.
    """

    from src.pipeline import IMAGE_EXTENSIONS

    return IMAGE_EXTENSIONS


def run_extraction(image_bytes: bytes, filename: str) -> dict:
    """
    Run the existing pipeline over one flyer and return the popup's fields.

    The pipeline reads from a path and takes the flyer's name from that path,
    so the image is written into a temporary directory under its original
    name. The directory - and the flyer in it - is deleted as soon as the
    extraction finishes: ingested flyers are third-party content, and the
    repository already keeps them out of version control for that reason.

    `use_full_image=True` matches what process_flyers() does for a
    command-line run, so a flyer gets the same treatment either way.

    src.pipeline is imported here rather than at module scope because it pulls
    in Pillow and pytesseract. Keeping the import local means this module can
    be imported - and its framing and dispatch tested - without the OCR stack
    installed, in the same spirit as the note at the top of src/ocr.py.
    """

    from src.pipeline import extract_event_date, flyer_result_to_popup_data

    with tempfile.TemporaryDirectory() as directory:
        image_path = Path(directory) / filename
        image_path.write_bytes(image_bytes)

        result = extract_event_date(image_path, use_full_image=True)

    return flyer_result_to_popup_data(result)


def safe_filename(name: str) -> str:
    """
    Turn the name the popup sent into a name that is safe to write.

    Only the final path component survives, so a name such as
    "../../etc/passwd" becomes "passwd" and cannot escape the temporary
    directory the flyer is written into.
    """

    return Path((name or "").strip()).name


def failure(error: str, message: str) -> dict:
    """The one shape every refusal and every crash answers in."""

    return {"ok": False, "error": error, "message": message}


def handle_ping() -> dict:
    """
    Answer the message that proves Chrome can launch this process.

    Kept from milestone 1: it is the one check that needs neither an image nor
    the OCR stack, so it stays the quickest way to tell a broken host manifest
    apart from a broken pipeline.
    """

    return {"ok": True, "message": "pong"}


def handle_extract(message: dict) -> dict:
    """
    Answer one flyer with the pipeline's reading of it.

    The image arrives base64-encoded because a Native Messaging message is
    JSON, and JSON has no way to carry raw bytes.
    """

    filename = safe_filename(message.get("filename", ""))

    if not filename:
        return failure(
            "missing_filename",
            "The message must name the flyer it carries.",
        )

    # The pipeline has to be importable before anything can be asked of it.
    #
    # This is the failure to expect in practice: Chrome inherits none of the
    # shell's environment, so a host registered against the wrong interpreter
    # finds no Pillow and no pytesseract. Saying so is the difference between
    # a fixable message and a host that vanishes.
    try:
        extensions = supported_extensions()

    except ImportError as error:
        traceback.print_exc(file=sys.stderr)

        return failure(
            "pipeline_unavailable",
            (
                f"The extraction pipeline could not be imported: {error}. "
                "Register the host against the interpreter that has this "
                "project's requirements installed."
            ),
        )

    if Path(filename).suffix.lower() not in extensions:
        return failure(
            "unsupported_file_type",
            f"{filename} is not a supported image file.",
        )

    encoded = message.get("imageBase64")

    if not encoded:
        return failure(
            "empty_body",
            "The message must carry the image as imageBase64.",
        )

    try:
        # validate=True so text that is not base64 at all is refused here,
        # rather than silently decoding to whatever survived.
        image_bytes = base64.b64decode(encoded, validate=True)

    except (binascii.Error, ValueError) as error:
        return failure(
            "invalid_encoding",
            f"imageBase64 is not valid base64: {error}",
        )

    if not image_bytes:
        return failure(
            "empty_body",
            "The message must carry the image as imageBase64.",
        )

    if len(image_bytes) > MAX_IMAGE_BYTES:
        return failure(
            "file_too_large",
            f"The image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
        )

    # Anything the pipeline raises - an unreadable image, a missing Tesseract
    # binary - becomes one answer instead of a dead host, so the popup can say
    # that the flyer could not be read.
    try:
        result = run_extraction(image_bytes, filename)

    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        # The traceback is the only way to tell a missing Tesseract apart from
        # a corrupt JPEG, and stderr is where Chrome keeps it.
        traceback.print_exc(file=sys.stderr)

        return failure(
            "extraction_failed",
            f"{type(error).__name__}: {error}",
        )

    return {"ok": True, "result": result}


# Every message type this host answers.
HANDLERS = {
    "ping": lambda message: handle_ping(),
    "extract": handle_extract,
}


def handle_message(message) -> dict:
    """Route one decoded message to the handler for its type."""

    if not isinstance(message, dict):
        return failure(
            "invalid_message",
            "A message must be a JSON object.",
        )

    message_type = message.get("type")
    handler = HANDLERS.get(message_type)

    if handler is None:
        return failure(
            "unknown_message_type",
            f"Unknown message type: {message_type!r}",
        )

    return handler(message)


def read_message(stream):
    """
    Read one length-prefixed message, or None when the stream is finished.

    Chrome closes stdin when it has nothing more to send, which is the host's
    signal to exit. A prefix that arrives only partly means the connection was
    cut mid-message, and is treated the same way.
    """

    header = stream.read(LENGTH_BYTES)

    if len(header) < LENGTH_BYTES:
        return None

    (length,) = struct.unpack(LENGTH_FORMAT, header)
    body = stream.read(length)

    if len(body) < length:
        return None

    return json.loads(body.decode("utf-8"))


def write_message(stream, payload: dict) -> None:
    """
    Write one length-prefixed message and flush it.

    The flush matters: Chrome is waiting on this exact process, and a buffered
    answer would look to the popup like a host that never replied.
    """

    body = json.dumps(payload).encode("utf-8")

    stream.write(struct.pack(LENGTH_FORMAT, len(body)))
    stream.write(body)
    stream.flush()


def serve(input_stream, output_stream) -> int:
    """
    Answer messages until the other end closes the connection.

    One message in, one message out. The popup uses sendNativeMessage(), which
    sends a single message and lets Chrome close the host afterwards, so in
    practice this loop runs once per selected flyer - but looping costs
    nothing and means a future connect()-based caller works unchanged.
    """

    while True:
        try:
            message = read_message(input_stream)

        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            # The framing is still intact - only the payload was unreadable -
            # so this is answerable rather than fatal.
            write_message(
                output_stream,
                failure("invalid_message", f"Could not decode message: {error}"),
            )
            continue

        if message is None:
            return 0

        # Nothing a single message does may take the host down: Chrome would
        # report only that the host "exited", and the popup would have nothing
        # to show but a connection failure. Every handler already answers its
        # own expected failures; this is the net under the unexpected ones.
        try:
            answer = handle_message(message)

        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            traceback.print_exc(file=sys.stderr)
            answer = failure("host_error", f"{type(error).__name__}: {error}")

        write_message(output_stream, answer)


def main(argv=None) -> int:
    """
    Entry point Chrome reaches through native_host/flyer_extractor_host.py.

    stdin and stdout are used as binary streams, because the wire format is
    binary and because text-mode stdout on Windows would rewrite "\\n" inside
    the length prefix and corrupt it.

    Chrome passes the calling extension's origin, and on Windows a window
    handle, as command-line arguments. Neither is needed here: the host
    manifest's allowed_origins already decides who may connect.
    """

    return serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
