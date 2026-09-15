@echo off
rem Registers the native messaging host with Chrome for the current user.
rem
rem Chrome finds a native messaging host on Windows through the registry, not
rem through a directory: it reads the path of the host manifest out of
rem HKCU\Software\Google\Chrome\NativeMessagingHosts\<host name>.
rem
rem HKCU (current user) is used deliberately - it needs no administrator rights
rem and nothing is installed machine-wide.
rem
rem Run this once, after copying the template manifest and filling in your
rem extension ID:
rem
rem   native_host\register_host.bat
rem
rem To undo it:
rem
rem   reg delete "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.insta_scraper.native_host" /f

setlocal

set "HOST_NAME=com.insta_scraper.native_host"
set "MANIFEST=%~dp0%HOST_NAME%.json"

if not exist "%MANIFEST%" (
    echo Host manifest not found: "%MANIFEST%"
    echo.
    echo Copy the template first, then put your extension ID in it:
    echo   copy "%~dp0%HOST_NAME%.template.json" "%MANIFEST%"
    exit /b 1
)

rem /ve writes the key's default value, which is where Chrome looks for the
rem manifest path. /f overwrites a previous registration without prompting.
reg add "HKCU\Software\Google\Chrome\NativeMessagingHosts\%HOST_NAME%" /ve /t REG_SZ /d "%MANIFEST%" /f

if errorlevel 1 (
    echo Registration failed.
    exit /b 1
)

echo Registered %HOST_NAME% -^> "%MANIFEST%"
echo Restart Chrome for the change to take effect.
exit /b 0
