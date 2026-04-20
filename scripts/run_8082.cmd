@echo off
setlocal
cd /d "%~dp0.."
set "PYTHONPATH=%CD%"
"C:\Users\50588\AppData\Local\Programs\Python\Python39\python.exe" -m uvicorn overnight_bt.app:app --host 127.0.0.1 --port 8082
