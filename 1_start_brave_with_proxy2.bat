@echo off
cd /d "%~dp0"

Scripts\mitmdump.exe -s video_capture.py --set save_dir=captured --set url_pattern="segment_\d+"

pause