"""
Tests for the Chrome Native Messaging host (src/native_host.py).

These cover the two things the host is responsible for: the length-prefixed
wire format Chrome speaks, and the dispatch from a decoded message to the
existing pipeline.

src.pipeline is stubbed rather than imported, so none of this needs Pillow or
Tesseract - the same approach tests/test_server.py takes for the HTTP
interface it replaces.
"""

import io
import json
import struct
import sys
import types

import pytest

from src import native_host


# What the pipeline's flyer_result_to_popup_data() produces, and therefore
# what the popup reads out of the host's answer.
EXTRACTED_RESULT = {
    "filename": "cherry_blossom_market.jpeg",
    "eventDate": "2027-03-27",
    "status": "ok",
    "needsReview": False,
}

IMAGE_BYTES = b"\xff\xd8\xff\xe0 not really a JPEG, but bytes are bytes"


def frame(message: dict) -> bytes:
    """Encode one message the way Chrome writes it to the host's stdin."""

    body = json.dumps(message).encode("utf-8")

    return struct.pack(native_host.LENGTH_FORMAT, len(body)) + body


def unframe(raw: bytes) -> list:
    """Decode every message the host wrote to its stdout."""

    messages = []
    offset = 0

    while offset < len(raw):
        (length,) = struct.unpack_from(native_host.LENGTH_FORMAT, raw, offset)
        offset += native_host.LENGTH_BYTES

        messages.append(json.loads(raw[offset : offset + length].decode("utf-8")))
        offset += length

    return messages


def serve(*messages) -> list:
    """Run the host over a canned conversation and return what it answered."""

    incoming = io.BytesIO(b"".join(frame(message) for message in messages))
    outgoing = io.BytesIO()

    assert native_host.serve(incoming, outgoing) == 0

    return unframe(outgoing.getvalue())


@pytest.fixture
def pipeline(monkeypatch):
    """
    Stand in for src.pipeline, and record what the host handed it.

    Installed into sys.modules rather than imported, which is also what proves
    the lazy imports inside run_extraction() and supported_extensions()
    resolve.
    """

    seen = {}

    def fake_extract_event_date(image_path, today=None, use_full_image=False):
        seen["path"] = image_path
        seen["exists"] = image_path.exists()
        seen["bytes"] = image_path.read_bytes()
        seen["use_full_image"] = use_full_image
        return "a FlyerResult"

    def fake_flyer_result_to_popup_data(result):
        seen["converted"] = result
        return EXTRACTED_RESULT

    module = types.ModuleType("src.pipeline")
    module.IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    module.extract_event_date = fake_extract_event_date
    module.flyer_result_to_popup_data = fake_flyer_result_to_popup_data

    monkeypatch.setitem(sys.modules, "src.pipeline", module)

    return seen


def extract_message(image_bytes=IMAGE_BYTES, filename="cherry_blossom_market.jpeg"):
    """The message the popup sends for one selected flyer."""

    import base64

    return {
        "type": "extract",
        "filename": filename,
        "imageBase64": base64.b64encode(image_bytes).decode("ascii"),
    }


def test_ping_is_still_answered():
    """
    Milestone 1 keeps working: Chrome can launch the host and get an answer.

    This needs nothing from the pipeline, which is what makes it the useful
    check that the host manifest itself is right.
    """

    assert serve({"type": "ping"}) == [{"ok": True, "message": "pong"}]


def test_a_flyer_reaches_the_pipeline_and_comes_back(pipeline):
    """One flyer in, the popup's four fields out."""

    answers = serve(extract_message())

    assert answers == [{"ok": True, "result": EXTRACTED_RESULT}]

    # The pipeline read the sent bytes, from a file carrying the flyer's own
    # name - which is where the result's filename comes from.
    assert pipeline["exists"]
    assert pipeline["bytes"] == IMAGE_BYTES
    assert pipeline["path"].name == "cherry_blossom_market.jpeg"

    # A selected flyer is OCR'd whole, the same as a command-line run.
    assert pipeline["use_full_image"] is True

    # Whatever the pipeline returned is converted by the pipeline's own
    # function rather than reassembled here.
    assert pipeline["converted"] == "a FlyerResult"

    # The flyer is not left on disk once the extraction is over.
    assert not pipeline["path"].exists()


def test_several_messages_are_answered_in_order(pipeline):
    """
    The host keeps reading until the connection closes.

    sendNativeMessage() only ever sends one message before Chrome shuts the
    host down, but nothing about the loop depends on that.
    """

    answers = serve({"type": "ping"}, extract_message(), {"type": "ping"})

    assert answers == [
        {"ok": True, "message": "pong"},
        {"ok": True, "result": EXTRACTED_RESULT},
        {"ok": True, "message": "pong"},
    ]


def test_a_closed_connection_ends_the_host():
    """Chrome closing stdin is how the host is told to exit."""

    assert serve() == []


def test_a_truncated_message_ends_the_host():
    """A connection cut mid-message is not something to answer."""

    incoming = io.BytesIO(frame({"type": "ping"})[:-4])
    outgoing = io.BytesIO()

    assert native_host.serve(incoming, outgoing) == 0
    assert outgoing.getvalue() == b""


def test_a_message_that_is_not_json_is_reported():
    """
    Broken JSON is answered rather than fatal: the framing is still intact.
    """

    body = b"{not json"
    incoming = io.BytesIO(
        struct.pack(native_host.LENGTH_FORMAT, len(body)) + body
    )
    outgoing = io.BytesIO()

    native_host.serve(incoming, outgoing)

    (answer,) = unframe(outgoing.getvalue())

    assert answer["ok"] is False
    assert answer["error"] == "invalid_message"


def test_an_unknown_message_type_is_reported():
    (answer,) = serve({"type": "explode"})

    assert answer["ok"] is False
    assert answer["error"] == "unknown_message_type"


def test_a_message_that_is_not_an_object_is_reported():
    (answer,) = serve(["ping"])

    assert answer["ok"] is False
    assert answer["error"] == "invalid_message"


def test_unsupported_file_types_are_refused(pipeline):
    (answer,) = serve(extract_message(filename="event_notes.pdf"))

    assert answer["ok"] is False
    assert answer["error"] == "unsupported_file_type"

    # Refused before the pipeline was involved at all.
    assert pipeline == {}


def test_a_missing_filename_is_refused(pipeline):
    (answer,) = serve(extract_message(filename=""))

    assert answer["ok"] is False
    assert answer["error"] == "missing_filename"
    assert pipeline == {}


def test_a_filename_cannot_escape_the_upload_directory(pipeline):
    """A name with a path in it is reduced to its final component."""

    serve(extract_message(filename="../../etc/cherry_blossom_market.jpeg"))

    assert pipeline["path"].name == "cherry_blossom_market.jpeg"


def test_a_message_with_no_image_is_refused(pipeline):
    (answer,) = serve({"type": "extract", "filename": "flyer.jpeg"})

    assert answer["ok"] is False
    assert answer["error"] == "empty_body"
    assert pipeline == {}


def test_an_image_that_is_not_base64_is_refused(pipeline):
    (answer,) = serve(
        {
            "type": "extract",
            "filename": "flyer.jpeg",
            "imageBase64": "not base64 at all!!",
        }
    )

    assert answer["ok"] is False
    assert answer["error"] == "invalid_encoding"
    assert pipeline == {}


def test_an_oversized_image_is_refused(pipeline, monkeypatch):
    monkeypatch.setattr(native_host, "MAX_IMAGE_BYTES", 8)

    (answer,) = serve(extract_message())

    assert answer["ok"] is False
    assert answer["error"] == "file_too_large"
    assert pipeline == {}


def test_a_failing_pipeline_becomes_an_error_answer(pipeline, monkeypatch):
    """
    A missing Tesseract, or an unreadable image, is reported and survived.

    The popup turns this into its "could not be read" state, so the host has
    to answer rather than die.
    """

    def explode(image_bytes, filename):
        raise RuntimeError("TesseractNotFoundError")

    monkeypatch.setattr(native_host, "run_extraction", explode)

    (answer,) = serve(extract_message())

    assert answer["ok"] is False
    assert answer["error"] == "extraction_failed"
    assert "TesseractNotFoundError" in answer["message"]


def test_a_pipeline_that_cannot_be_imported_is_reported(monkeypatch):
    """
    A host with no OCR stack behind it answers instead of dying.

    This is what a host registered against the wrong interpreter looks like:
    Chrome inherits none of the shell's environment, so the import fails at
    the first message. If it killed the host, the popup would see only a
    connection failure and the real reason would be lost.
    """

    def no_pipeline():
        raise ImportError("No module named 'PIL'")

    monkeypatch.setattr(native_host, "supported_extensions", no_pipeline)

    (answer,) = serve(extract_message())

    assert answer["ok"] is False
    assert answer["error"] == "pipeline_unavailable"
    assert "PIL" in answer["message"]


def test_an_unexpected_crash_does_not_kill_the_host(monkeypatch):
    """
    One bad message costs one answer, not the connection.

    The handlers report their own expected failures; this covers the net under
    everything else, so the host is always the thing that replies.
    """

    def explode(message):
        raise ValueError("something nobody predicted")

    monkeypatch.setitem(native_host.HANDLERS, "extract", explode)

    answers = serve(extract_message(), {"type": "ping"})

    assert answers[0]["ok"] is False
    assert answers[0]["error"] == "host_error"
    assert "something nobody predicted" in answers[0]["message"]

    # The conversation carried on.
    assert answers[1] == {"ok": True, "message": "pong"}


def test_supported_extensions_match_the_pipeline():
    """
    The host and the command-line runner agree about what a flyer is.

    Needs the OCR stack, because src.pipeline imports Pillow and pytesseract.
    """

    pytest.importorskip("PIL")
    pytest.importorskip("pytesseract")

    from src.pipeline import IMAGE_EXTENSIONS

    assert native_host.supported_extensions() == IMAGE_EXTENSIONS
