@echo off
rem Launcher Chrome starts for the com.insta_scraper.native_host host.
rem
rem Chrome cannot run a .py file directly on Windows, so the host manifest
rem points at this batch file and this batch file runs Python.
rem
rem "@echo off" on the first line is not cosmetic: an echoed command would be
rem written to stdout, and stdout is the native messaging pipe. Anything
rem printed here that is not a length-prefixed message corrupts the protocol.
rem
rem %~dp0 is this file's own directory (with a trailing backslash), so the host
rem is found no matter which directory Chrome happens to start it from.

setlocal

rem -u keeps Python from buffering stdout, so a reply reaches Chrome as soon
rem as it is written rather than when the process exits.
python -u "%~dp0ping_host.py"

rem If "python" is not on PATH, comment out the line above and use the Windows
rem launcher instead:
rem py -3 -u "%~dp0ping_host.py"

exit /b %ERRORLEVEL%
