# Native messaging host (POC milestone 1: ping -> pong)

Proves that the Chrome extension can start a Python process by itself and get
an answer back:

```text
Chrome extension
    |
    |  {"action": "ping"}
    v
native_host/ping_host.py
    |
    |  {"ok": true, "message": "pong"}
    v
Chrome extension
```

No flyer, no image, no OCR, and **no `python -m src.server`**: Chrome launches
the host itself for the duration of the message.

## Files

| File | What it is |
| --- | --- |
| `ping_host.py` | The host. Standard library only. Reads one length-prefixed JSON message from stdin, answers `ping` with `pong`, writes the reply length-prefixed to stdout, logs to stderr. |
| `run_host.bat` | What Chrome actually starts on Windows, because Chrome cannot run a `.py` file directly. |
| `com.insta_scraper.native_host.template.json` | Template for the host manifest. Copy it, then fill in your extension ID. |
| `register_host.bat` | Writes the `HKCU` registry key that tells Chrome where the host manifest is. |

## Setup (Windows)

1. **Load the extension** and copy its ID.

   `chrome://extensions` -> Developer mode -> Load unpacked -> pick the
   `extension/` folder. The ID is the 32-letter string under the extension's
   name.

2. **Copy the manifest template:**

   ```bat
   copy native_host\com.insta_scraper.native_host.template.json native_host\com.insta_scraper.native_host.json
   ```

3. **Insert your extension ID** in the copy, in `allowed_origins`. Replace
   `REPLACE_WITH_YOUR_CHROME_EXTENSION_ID` and keep the `chrome-extension://`
   prefix and the trailing slash:

   ```json
   "allowed_origins": [
     "chrome-extension://abcdefghijklmnopabcdefghijklmnop/"
   ]
   ```

4. **Register the host** (one command, no administrator rights needed):

   ```bat
   native_host\register_host.bat
   ```

5. **Restart Chrome.** Chrome reads the registry at startup.

## Trigger the ping

Click the extension's toolbar icon, then the **Ping Native Host** button at the
bottom of the popup. The line under it shows either
`Native host replied: pong` or the reason it failed.

## Paths

`path` in the host manifest is `run_host.bat`, which Chrome resolves relative
to the directory holding the manifest, so there is nothing machine-specific to
edit. If Chrome reports it cannot find the host, put the absolute path there
instead, with doubled backslashes:

```json
"path": "C:\\Users\\you\\insta_scraper\\native_host\\run_host.bat"
```

`register_host.bat` derives the manifest's absolute path from its own location,
so it needs no editing either.

`run_host.bat` calls `python`, so Python must be on `PATH`. If it is not, the
batch file has a commented-out `py -3` line to switch to.

## When it fails

The popup shows Chrome's own error text. The usual causes:

- *"Specified native messaging host not found"* - the registry key is missing
  (step 4), or Chrome was not restarted (step 5), or the `name` in the manifest
  does not match the registry key name.
- *"Access to the specified native messaging host is forbidden"* - the
  extension ID in `allowed_origins` is wrong, or the `chrome-extension://`
  prefix or trailing slash is missing.
- *"Native host has exited"* - the host itself failed. Python is not on `PATH`,
  or something wrote to stdout that was not a message. Chrome logs the host's
  stderr; start Chrome with `--enable-logging --v=1` and read
  `chrome_debug.log` in the user data directory.

## Undo

```bat
reg delete "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.insta_scraper.native_host" /f
```
