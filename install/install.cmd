@echo off
rem Installs Nemerle for the current user. Options are those of install.ps1, e.g. -Editor none, -Build, -Uninstall.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
