@echo off
cd /d "%~dp0"
python -m eyepin gui "%USERPROFILE%\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che" %*
if errorlevel 1 pause
