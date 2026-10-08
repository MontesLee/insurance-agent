@echo off
setlocal
REM Phase 27.7.6 - Human Reviewer Session Launcher (v2, connectivity-fixed)
REM
REM v1 defect (2026-09-24 connectivity regression): this file contained
REM non-ASCII characters saved as UTF-8; under a GBK console codepage cmd
REM misparsed the script byte-wise, the backend start line never ran, and
REM the UI opened with "Cannot reach the runtime server" on every page.
REM v2 rules: PURE ASCII ONLY in this file; health-gate before opening
REM the browser; backend output goes to a log; reuse a healthy instance
REM instead of double-starting. Ports and API contract unchanged
REM (backend 127.0.0.1:8000, vite 5173, /api proxy).
REM Chinese reviewer instructions live in
REM evaluation/human-review/reviewer-guide.md (kept out of this file).

set ROOT=D:\Workspace\insurance-agent
set BACKEND_LOG=%ROOT%\tmp\human-session-backend.log
set VITE_LOG=%ROOT%\tmp\human-session-vite.log
set HEALTH=http://127.0.0.1:8000/api/health

echo [1/4] Backend (127.0.0.1:8000) ...

powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%HEALTH%' | Out-Null; exit 0}catch{exit 1}" >nul 2>nul
if %errorlevel%==0 (
    echo       already healthy - reusing it.
    goto frontend
)

cd /d %ROOT%
if not exist tmp mkdir tmp
start /b cmd /c "python -m uvicorn --factory runtime.server:create_app --host 127.0.0.1 --port 8000 > %BACKEND_LOG% 2>&1"

echo       waiting for /api/health (up to 30s) ...
set /a TRIES=0
:waitloop
set /a TRIES+=1
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%HEALTH%' | Out-Null; exit 0}catch{exit 1}" >nul 2>nul
if %errorlevel%==0 goto healthy
if %TRIES% geq 15 goto backend_failed
timeout /t 2 /nobreak >nul
goto waitloop

:backend_failed
echo.
echo [ERROR] Backend did NOT become healthy within 30s.
echo        Backend log tail - full log: tmp\human-session-backend.log
echo ------------------------------------------------------------
powershell -NoProfile -Command "if (Test-Path '%BACKEND_LOG%') { Get-Content -Tail 15 '%BACKEND_LOG%' } else { echo '(no log file - python/uvicorn failed to start)' }"
echo ------------------------------------------------------------
echo Fix the error above, then re-run this launcher.
pause
exit /b 1

:healthy
echo       backend healthy.

:frontend
echo [2/4] Frontend (vite, port 5173) ...
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://localhost:5173 | Out-Null; exit 0}catch{exit 1}" >nul 2>nul
if %errorlevel%==0 (
    echo       already running - reusing it.
    goto open
)
cd /d %ROOT%\web
start /b cmd /c "npx vite --port 5173 > %VITE_LOG% 2>&1"
timeout /t 6 /nobreak >nul

:open
echo [3/4] Opening browser at http://localhost:5173 ...
start http://localhost:5173

echo [4/4] Reviewer quick guide (full guide: evaluation\human-review\reviewer-guide.md)
echo ================================================================
echo  Project ID : pilot-2776-human-reviewer
echo  Queue      : HR-R1 .. HR-R6 (6 items, WAITING_HUMAN)
echo  1. Top nav [Review Queue] - enter the project ID - [Load]
echo  2. Filters: All / High Risk / Need Review / Random Audit
echo     (each row shows its Review Card level + validation chips)
echo  3. For DEEP_REVIEW items open the Workspace:
echo     section A2 = Review Card, C/D/E = evidence drill-down
echo  4. Decide: Approve / Request Fix / Reject
echo     (Request Fix and Reject require a comment)
echo  5. Optional improvement feedback: section G form
echo  6. Export feedback in DevTools console (F12):
echo     copy(JSON.parse(localStorage.getItem("webui:feedback:v1")))
echo  Logs: tmp\human-session-backend.log / tmp\human-session-vite.log
echo ================================================================
pause
