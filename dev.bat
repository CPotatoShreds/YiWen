@echo off
setlocal EnableExtensions
chcp 936 >nul
cd /d "%~dp0"

set "BACK_PORT=8102"
set "FRONT_PORT=5174"

rem ===== 端口预检：被占用则拒绝启动（防双实例 / 误杀他人进程）=====
for %%P in (%BACK_PORT% %FRONT_PORT%) do (
    netstat -ano | findstr /c:":%%P " | findstr "LISTENING" >nul
    if not errorlevel 1 (
        echo [错误] 端口 %%P 已被占用，拒绝启动。请先关闭占用该端口的进程。
        exit /b 1
    )
)

rem ===== 后端：用 .venv 里的 python 直接跑 uvicorn（单一进程，便于安全关闭）=====
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv\Scripts\python.exe，请先运行 uv sync。
    exit /b 1
)
echo === 启动数据库（Docker PostgreSQL）===
docker compose up -d
if errorlevel 1 (
    echo [错误] Docker PostgreSQL 启动失败，请确认 Docker Desktop 已运行。
    exit /b 1
)

echo === 应用数据库迁移 ===
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 (
    echo [错误] 数据库迁移失败，拒绝启动。
    exit /b 1
)

echo === 启动后端 uvicorn :%BACK_PORT% ===
start "ynfight-backend" /b cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %BACK_PORT%"

echo === 启动前端 vite :%FRONT_PORT% ===
start "ynfight-frontend" /b cmd /c "cd /d %~dp0frontend && node node_modules\vite\bin\vite.js --host 127.0.0.1 --port %FRONT_PORT%"

rem ===== 健康检查：约 4 秒后两端口都应已在监听，否则报错并回滚 =====
ping -n 5 127.0.0.1 >nul
netstat -ano | findstr /c:":%BACK_PORT% " | findstr "LISTENING" >nul
if errorlevel 1 (
    echo [错误] 后端未能启动，请检查上面的报错。正在关闭...
    goto shutdown
)
netstat -ano | findstr /c:":%FRONT_PORT% " | findstr "LISTENING" >nul
if errorlevel 1 (
    echo [错误] 前端未能启动，请检查上面的报错。正在关闭...
    goto shutdown
)

echo.
echo 前后端已在本窗口运行：
echo   后端 API   http://localhost:%BACK_PORT%/api/docs
echo   前端页面   http://localhost:%FRONT_PORT%
echo.
echo 安全退出：输入 q 后回车（会同时关闭前后端，不残留进程）
echo ------------------------------------------------------------

:loop
set /p "KEY=输入 q 后回车退出："
if /i "%KEY%"=="q" goto shutdown
goto loop

:shutdown
echo.
echo 正在关闭前后端...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /c:":%BACK_PORT% " ^| findstr "LISTENING"') do taskkill /F /T /PID %%P >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /c:":%FRONT_PORT% " ^| findstr "LISTENING"') do taskkill /F /T /PID %%P >nul 2>&1
echo 已全部关闭，无残留进程。
exit /b 0
