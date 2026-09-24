@echo off
REM Phase 27.7.6 — Human Reviewer Session Launcher
REM Starts backend + frontend, then opens the browser

echo Starting backend (port 8000)...
cd /d D:\Workspace\insurance-agent
start /b python -m uvicorn --factory runtime.server:create_app --host 127.0.0.1 --port 8000

echo Starting frontend (port 5173)...
cd /d D:\Workspace\insurance-agent\web
start /b npx vite --port 5173

timeout /t 8 /nobreak >nul
echo.
echo ================================================
echo  Browser will open at http://localhost:5173
echo.
echo  Reviewer instructions:
echo  1. Click top nav: [审核队列]
echo  2. Enter project ID: pilot-2775-feedback-validation
echo  3. Click [加载]
echo  4. Work through R1-R6 (each item in the queue)
echo     - Read the Workspace sections A-F
echo     - Make an Approve or Reject decision
echo     - If you see something worth improving,
echo       fill the feedback form (section G) and submit
echo     - Feedback is OPTIONAL — skip if nothing to say
echo  5. When done, open DevTools Console (F12) and run:
echo     copy(JSON.parse(localStorage.getItem("webui:feedback:v1")))
echo     Paste the result to the analysis document.
echo ================================================
echo.
start http://localhost:5173
pause
