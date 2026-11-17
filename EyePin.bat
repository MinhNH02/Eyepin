@echo off
cd /d "%~dp0"
python -m eyepin gui %*
if errorlevel 1 pause
