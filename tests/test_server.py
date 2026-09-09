"""
Tests for the local HTTP interface (src/server.py).

These drive a real server over a real socket on an unused port, so they cover
the request handling as Chrome will meet it: headers, status codes, CORS, and
the JSON the popup parses.

The extraction itself is stubbed. src/server.py imports the pipeline lazily
for exactly this reason, so these run without Pillow, pytesseract, or the
Tesseract binary installed.
"""

import json
import sys
import threading
import types
import urllib.error
import urllib.request

import pytest

from src import server


# What the pipeline accepts, restated here so the HTTP tests do not need the
# OCR stack installed. test_supported_extensions_match_the_pipeline below
# checks this against the real constant when the stack is available.
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# The shape src.pipeline.flyer_result_to_popup_data() returns.
EXTRACTED_RESULT = {
    "filename": "cherry_blossom_market.jpeg",
    "eventDate": "2027-03-27",
    "status": "ok",
    "needsReview": False,
}

IMAGE_BYTES = b"\xff\xd8\xff\xe0 not really a JPEG, the extractor is stubbed"

# A Chrome extension origin: chrome-extension:// and a 32-character id built
# from the letters a-p. The popup's own id differs per installation, which is
# why the server matches the shape rather than one id.
EXTENSION_ORIGIN = "chrome-extension://" + "abcdefghijklmnop" * 2


@pytest.fixture
def extractions(monkeypatch):
    """
    Replace the pipeline with a recorder.

    Every call the server makes lands in the returned list, so a test can see
    exactly which bytes and which filename reached the pipeline.
    """

    calls = []

    def fake_run_extraction(image_bytes, filename):
        calls.append({"image_bytes": image_bytes, "filename": filename})
        return dict(EXTRACTED_RESULT, filename=filename)

    monkeypatch.setattr(server, "run_extraction", fake_run_extraction)
    monkeypatch.setattr(
        server, "supported_extensions", lambda: SUPPORTED_EXTENSIONS
    )

    return calls


@pytest.fixture
def base_url():
    """Run the server on an operating-system-assigned port for one test."""

    running_server = server.create_server(port=0)
    host, port = running_server.server_address[:2]

    # The short poll interval only affects how quickly shutdown() is noticed,
    # which is otherwise half a second per test.
    thread = threading.Thread(
        target=running_server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    thread.start()

    try:
        yield f"http://{host}:{port}"

    finally:
        running_server.shutdown()
        running_server.server_close()
        thread.join(timeout=5)


def request(url, method="POST", data=None, headers=None):
    """
    Make one request and return (status, parsed body, response headers).

    urllib raises on a non-2xx status, but an error response here is a normal
    outcome with a body worth reading, so it is unwrapped rather than raised.
    """

    call = urllib.request.Request(
        url, data=data, headers=headers or {}, method=method
    )

    try:
        with urllib.request.urlopen(call) as response:
            body = response.read()
            return response.status, body, dict(response.headers)

    except urllib.error.HTTPError as error:
        body = error.read()
        return error.code, body, dict(error.headers)


def post_flyer(
    base_url,
    filename,
    image_bytes=IMAGE_BYTES,
    path="/extract",
    origin=EXTENSION_ORIGIN,
):
    """
    Post one flyer the way the popup does.

    `origin=None` stands for a caller that is not a browser, such as curl.
    """

    headers = {"Content-Type": "image/jpeg"}

    if filename is not None:
        headers[server.FILENAME_HEADER] = filename

    if origin is not None:
        headers["Origin"] = origin

    status, body, response_headers = request(
        base_url + path, data=image_bytes, headers=headers
    )

    return status, json.loads(body), response_headers


def test_extract_returns_the_popup_result(base_url, extractions):
    status, payload, _ = post_flyer(base_url, "cherry_blossom_market.jpeg")

    assert status == 200
    assert payload == EXTRACTED_RESULT

    # The whole image reached the pipeline, under its own name.
    assert extractions == [
        {
            "image_bytes": IMAGE_BYTES,
            "filename": "cherry_blossom_market.jpeg",
        }
    ]


def test_extract_allows_the_extension_to_call_it(base_url, extractions):
    status, _, headers = post_flyer(base_url, "cherry_blossom_market.jpeg")

    # The grant is made to the extension that asked, not to every origin, and
    # without it the browser discards the response.
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == EXTENSION_ORIGIN
    assert headers["Content-Type"] == "application/json; charset=utf-8"

    # The answer depends on who asked, so it must not be cached across origins.
    assert headers["Vary"] == "Origin"


def test_a_web_page_may_not_call_the_extractor(base_url, extractions):
    """
    Loopback keeps other machines out; this keeps other pages out.

    Any site the user visits can post to a local port, so an origin that is
    not the extension is refused outright.
    """

    status, payload, headers = post_flyer(
        base_url, "flyer.png", origin="https://example.com"
    )

    assert status == 403
    assert payload["error"] == "forbidden_origin"

    # No grant, so the page cannot read the refusal either.
    assert "Access-Control-Allow-Origin" not in headers

    # The flyer is never extracted for a caller that is not allowed to have it.
    assert extractions == []


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "file://",
        "http://127.0.0.1:8756",
        "moz-extension://" + "abcdefghijklmnop" * 2,
        "chrome-extension://",
        "chrome-extension://tooshort",
        "chrome-extension://" + "z" * 32,
        "chrome-extension://" + "abcdefghijklmnop" * 2 + ".example.com",
        "https://example.com/chrome-extension://" + "abcdefghijklmnop" * 2,
    ],
)
def test_only_chrome_extension_origins_are_accepted(
    base_url, extractions, origin
):
    """
    Everything that is not a Chrome extension origin is refused.

    Including the near misses: another browser's extension scheme, an id of
    the wrong shape, and an origin that merely contains an extension origin.
    """

    status, payload, _ = post_flyer(base_url, "flyer.png", origin=origin)

    assert status == 403
    assert payload["error"] == "forbidden_origin"
    assert extractions == []


def test_a_caller_that_is_not_a_browser_is_served(base_url, extractions):
    """
    curl and the command line still work.

    A browser always sends Origin on a cross-origin request, so a request
    without one is not what the origin check is defending against.
    """

    status, payload, headers = post_flyer(
        base_url, "cherry_blossom_market.jpeg", origin=None
    )

    assert status == 200
    assert payload == EXTRACTED_RESULT

    # There is no origin to grant access to, so nothing is granted.
    assert "Access-Control-Allow-Origin" not in headers


def test_preflight_is_answered(base_url, extractions):
    status, _, headers = request(
        base_url + "/extract",
        method="OPTIONS",
        headers={"Origin": EXTENSION_ORIGIN},
    )

    # The custom filename header makes the upload a non-simple request, so
    # Chrome asks permission before sending it.
    assert status == 204
    assert headers["Access-Control-Allow-Origin"] == EXTENSION_ORIGIN
    assert "POST" in headers["Access-Control-Allow-Methods"]
    assert server.FILENAME_HEADER in headers["Access-Control-Allow-Headers"]


def test_preflight_from_a_web_page_is_refused(base_url, extractions):
    status, payload, headers = request(
        base_url + "/extract",
        method="OPTIONS",
        headers={"Origin": "https://example.com"},
    )

    # Refused at the preflight, so the upload itself is never sent.
    assert status == 403
    assert json.loads(payload)["error"] == "forbidden_origin"
    assert "Access-Control-Allow-Origin" not in headers


def test_percent_encoded_filenames_are_decoded(base_url, extractions):
    status, payload, _ = post_flyer(base_url, "caf%C3%A9%20night.png")

    assert status == 200
    assert extractions[0]["filename"] == "café night.png"

    # The result names the flyer the user chose, not the encoded header.
    assert payload["filename"] == "café night.png"


def test_a_filename_cannot_escape_the_upload_directory(base_url, extractions):
    status, _, _ = post_flyer(base_url, "../../secrets/passwords.png")

    # Only the final path component survives, so the upload is written where
    # the server intends and nowhere else.
    assert status == 200
    assert extractions[0]["filename"] == "passwords.png"


def test_unsupported_file_types_are_refused(base_url, extractions):
    status, payload, _ = post_flyer(base_url, "event_notes.pdf")

    assert status == 400
    assert payload["error"] == "unsupported_file_type"

    # The pipeline is never asked to open a file it cannot read.
    assert extractions == []


def test_a_missing_filename_is_refused(base_url, extractions):
    status, payload, _ = post_flyer(base_url, None)

    assert status == 400
    assert payload["error"] == "missing_filename"
    assert extractions == []


def test_an_empty_body_is_refused(base_url, extractions):
    status, payload, _ = post_flyer(base_url, "flyer.png", image_bytes=b"")

    assert status == 400
    assert payload["error"] == "empty_body"
    assert extractions == []


def test_an_oversized_upload_is_refused(base_url, extractions, monkeypatch):
    monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 8)

    status, payload, _ = post_flyer(base_url, "flyer.png")

    assert status == 413
    assert payload["error"] == "file_too_large"
    assert extractions == []


def test_a_failing_pipeline_becomes_an_error_response(
    base_url, extractions, monkeypatch
):
    def explode(image_bytes, filename):
        raise RuntimeError("tesseract is not installed")

    monkeypatch.setattr(server, "run_extraction", explode)

    status, payload, _ = post_flyer(base_url, "flyer.png")

    # The popup gets a reason instead of a dropped connection.
    assert status == 500
    assert payload["error"] == "extraction_failed"
    assert "tesseract is not installed" in payload["message"]


def test_an_unknown_path_is_not_found(base_url, extractions):
    status, payload, _ = post_flyer(base_url, "flyer.png", path="/nope")

    assert status == 404
    assert payload["error"] == "not_found"
    assert extractions == []


def test_run_extraction_hands_the_flyer_to_the_pipeline(monkeypatch):
    """
    The upload reaches the pipeline as a real file, named as the user named it.

    src.pipeline is stubbed rather than imported, so this covers the file
    handling without needing Pillow or Tesseract. It is also what proves the
    lazy import in run_extraction() resolves.
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

    fake_pipeline = types.ModuleType("src.pipeline")
    fake_pipeline.extract_event_date = fake_extract_event_date
    fake_pipeline.flyer_result_to_popup_data = fake_flyer_result_to_popup_data
    monkeypatch.setitem(sys.modules, "src.pipeline", fake_pipeline)

    result = server.run_extraction(IMAGE_BYTES, "cherry_blossom_market.jpeg")

    assert result == EXTRACTED_RESULT

    # The pipeline read the uploaded bytes, from a file carrying the flyer's
    # own name - which is where the result's filename comes from.
    assert seen["exists"]
    assert seen["bytes"] == IMAGE_BYTES
    assert seen["path"].name == "cherry_blossom_market.jpeg"

    # A selected flyer is OCR'd whole, the same as a command-line run.
    assert seen["use_full_image"] is True

    # Whatever the pipeline returned is converted by the pipeline's own
    # function rather than reassembled here.
    assert seen["converted"] == "a FlyerResult"

    # The flyer is not left on disk once the extraction is over.
    assert not seen["path"].exists()


def test_supported_extensions_match_the_pipeline():
    """
    The server and the command-line runner agree about what a flyer is.

    Needs the OCR stack, because src.pipeline imports Pillow and pytesseract.
    """

    pytest.importorskip("PIL")
    pytest.importorskip("pytesseract")

    from src.pipeline import IMAGE_EXTENSIONS

    assert server.supported_extensions() == IMAGE_EXTENSIONS
    assert IMAGE_EXTENSIONS == SUPPORTED_EXTENSIONS
