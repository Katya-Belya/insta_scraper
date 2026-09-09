"""
A small local HTTP interface around the existing extraction pipeline.

The Chrome extension cannot run Tesseract, so the popup posts the flyer the
user selected to this server and gets back the same four fields the popup
already knows how to read.

No extraction logic lives here. This module only moves bytes: it validates the
request, saves the uploaded flyer to a temporary file, hands that file to
src.pipeline.extract_event_date(), and returns the result as JSON.

Run it alongside Chrome:

    python -m src.server

The server listens on 127.0.0.1 only, so it is reachable from the machine
running it and from nowhere else.

The request the popup makes is:

    POST /extract
    X-Flyer-Filename: cherry_blossom_market.jpeg   (percent-encoded)
    <raw image bytes as the body>

and the response is the popup's pipeline result:

    {"filename": "...", "eventDate": "2027-03-27", "status": "ok",
     "needsReview": false}

Errors answer with {"error": "<machine-readable reason>", "message": "..."},
which is how the popup decides between its invalid-file and error states.

Only the extension may call this server from a browser: see ALLOWED_ORIGIN
below.
"""

import argparse
import json
import re
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


# Local only. Binding to 0.0.0.0 would expose flyer OCR to the network, and
# nothing about this server is meant to leave the machine.
HOST = "127.0.0.1"

# An arbitrary high port, chosen to be unlikely to collide with a dev server.
# The extension's manifest grants access to this exact port.
DEFAULT_PORT = 8756

# The one route the popup calls.
EXTRACT_PATH = "/extract"

# The original filename travels in a header rather than in the body, so the
# body stays exactly the image bytes and needs no multipart parsing.
FILENAME_HEADER = "X-Flyer-Filename"

# Flyers are photographs, not archives. A cap keeps a malformed or hostile
# request from making the server read an unbounded body into memory.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# The only browser origin allowed to call this server.
#
# Binding to loopback keeps other machines out, but it does not keep out the
# browser on this one: any page the user visits can post to a local port. The
# origin check is what stops that. A Chrome extension origin is
# chrome-extension:// followed by the extension's 32-character id, which Chrome
# builds from the letters a-p only, so the pattern is exact rather than a
# prefix match - "chrome-extension://x.evil.com" is not an extension.
#
# The id itself is not pinned: an unpacked extension is given a different id in
# every clone of this repository, so pinning one would mean editing this file
# per machine.
ALLOWED_ORIGIN = re.compile(r"chrome-extension://[a-p]{32}")


def supported_extensions():
    """
    The image types the pipeline accepts.

    Imported from src.pipeline so the server and the command-line runner can
    never disagree about what counts as a flyer.

    Imported inside the function for the same reason as run_extraction below.
    """

    from src.pipeline import IMAGE_EXTENSIONS

    return IMAGE_EXTENSIONS


def run_extraction(image_bytes: bytes, filename: str) -> dict:
    """
    Run the existing pipeline over one uploaded flyer.

    The pipeline reads from a path and takes the flyer's name from that path,
    so the upload is written into a temporary directory under its original
    name. The directory - and the flyer in it - is deleted as soon as the
    extraction finishes: ingested flyers are third-party content, and the
    repository already keeps them out of version control for that reason.

    `use_full_image=True` matches what process_flyers() does for a
    command-line run, so a flyer gets the same treatment either way.

    src.pipeline is imported here rather than at module scope because it pulls
    in Pillow and pytesseract. Keeping the import local means this module can
    be imported - and its HTTP behavior tested - without the OCR stack
    installed, in the same spirit as the note at the top of src/ocr.py.
    """

    from src.pipeline import extract_event_date, flyer_result_to_popup_data

    with tempfile.TemporaryDirectory() as directory:
        image_path = Path(directory) / filename
        image_path.write_bytes(image_bytes)

        result = extract_event_date(image_path, use_full_image=True)

    return flyer_result_to_popup_data(result)


def is_allowed_origin(origin: str) -> bool:
    """Whether a browser at `origin` is allowed to call this server."""

    return ALLOWED_ORIGIN.fullmatch(origin) is not None


def safe_filename(header_value: str) -> str:
    """
    Turn the filename header into a name that is safe to write.

    Only the final path component survives, so a name such as
    "../../etc/passwd" becomes "passwd" and cannot escape the temporary
    directory the upload is written into.
    """

    return Path(unquote(header_value or "").strip()).name


class ExtractionHandler(BaseHTTPRequestHandler):
    """Answers the popup's extraction request."""

    # Reported in the Server: header. Without this the class name leaks.
    server_version = "FlyerExtractor/1.0"

    def do_OPTIONS(self):
        """
        Answer the preflight Chrome sends before the real POST.

        The custom filename header makes the upload a non-simple request, so
        the browser asks permission first.
        """

        if self._refuse_disallowed_origin():
            return

        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        if self._refuse_disallowed_origin():
            return

        if self.path != EXTRACT_PATH:
            self._send_json(
                404,
                {
                    "error": "not_found",
                    "message": f"Unknown path: {self.path}",
                },
            )
            return

        filename = safe_filename(self.headers.get(FILENAME_HEADER, ""))

        if not filename:
            self._send_json(
                400,
                {
                    "error": "missing_filename",
                    "message": f"{FILENAME_HEADER} header is required.",
                },
            )
            return

        if Path(filename).suffix.lower() not in supported_extensions():
            self._send_json(
                400,
                {
                    "error": "unsupported_file_type",
                    "message": f"{filename} is not a supported image file.",
                },
            )
            return

        # A missing or unparsable Content-Length means there is no way to know
        # how much of the body to read, so the upload is refused rather than
        # guessed at.
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        if content_length <= 0:
            self._send_json(
                400,
                {
                    "error": "empty_body",
                    "message": "The request body must contain the image.",
                },
            )
            return

        if content_length > MAX_UPLOAD_BYTES:
            self._send_json(
                413,
                {
                    "error": "file_too_large",
                    "message": (
                        "The image is larger than "
                        f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                    ),
                },
            )
            return

        image_bytes = self.rfile.read(content_length)

        # Anything the pipeline raises - an unreadable image, a missing
        # Tesseract binary - becomes one error response instead of a dropped
        # connection, so the popup can say what went wrong.
        try:
            result = run_extraction(image_bytes, filename)

        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            self._send_json(
                500,
                {
                    "error": "extraction_failed",
                    "message": f"{type(error).__name__}: {error}",
                },
            )
            return

        self._send_json(200, result)

    def _refuse_disallowed_origin(self) -> bool:
        """
        Turn away a browser that is not the extension, and say so.

        A request with no Origin header at all is not from a browser - it is
        curl, a test, or another local tool - and is allowed through: a browser
        always sends Origin on a cross-origin request, so nothing that this
        check is meant to stop can arrive without one.

        Returns True when the request was refused and already answered.
        """

        origin = self.headers.get("Origin")

        if origin is None or is_allowed_origin(origin):
            return False

        self._send_json(
            403,
            {
                "error": "forbidden_origin",
                "message": f"{origin} may not call this server.",
            },
        )
        return True

    def _allowed_origin(self):
        """
        The origin to grant access to in the response, if there is one.

        None means the response carries no grant: either the caller sent no
        Origin, or it sent one this server refuses. A browser that is refused
        discards the response, which is the point of the check.
        """

        origin = self.headers.get("Origin")

        if origin is not None and is_allowed_origin(origin):
            return origin

        return None

    def _send_cors_headers(self):
        """
        Allow the extension - and only the extension - to read the response.

        Binding to loopback stops other machines, not other pages in the
        user's own browser, so the grant is made to one origin rather than to
        "*", and the origin is echoed back because the extension's id differs
        between installations.
        """

        # The response body is the same either way, but whether it may be read
        # depends on who asked, so it must not be cached across origins.
        self.send_header("Vary", "Origin")

        allowed_origin = self._allowed_origin()

        if allowed_origin is None:
            return

        self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            f"Content-Type, {FILENAME_HEADER}",
        )
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """
    Build the server without starting it.

    Separate from main() so tests can run one on an unused port. Passing 0
    lets the operating system choose that port.
    """

    return ThreadingHTTPServer((HOST, port), ExtractionHandler)


def main(argv=None) -> int:
    """Command-line entry point: start the server and serve until Ctrl-C."""

    parser = argparse.ArgumentParser(
        description="Serve the flyer extraction pipeline over local HTTP."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )

    args = parser.parse_args(argv)

    server = create_server(args.port)
    host, port = server.server_address[:2]

    print(f"Flyer extractor listening on http://{host}:{port}{EXTRACT_PATH}")
    print("Press Ctrl-C to stop.")

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print("\nStopping.")

    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
