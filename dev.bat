@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 936 >nul
cd /d "%~dp0"

set "BACK_PORT=8102"
set "FRONT_PORT=5174"

rem ===== 先杀后起：幂等启动，任何时刻运行都得到最新代码 =====
rem 先杀掉已占用前后端端口的旧进程（含子进程），再迁移并启动，保证前后端总是最新。
call :kill_ports

rem ===== 检测 .venv 下的 python 直接用于 uvicorn（单进程，便于安全关闭）=====
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv\Scripts\python.exe，请先运行 uv sync
    exit /b 1
)
echo === 启动数据库（Docker PostgreSQL）===
docker compose up -d db >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker PostgreSQL 启动失败，请确认 Docker Desktop 正在运行。
    exit /b 1
)

echo === 启动任务队列（Redis）===
docker compose up -d redis >nul 2>&1
if errorlevel 1 (
    echo [错误] Redis 启动失败，请确认 Docker Desktop 正在运行。
    exit /b 1
)
echo === 应用数据库迁移 ===
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 (
    echo [错误] 数据库迁移失败，拒绝启动。
    exit /b 1
)

echo === 后台启动 uvicorn :%BACK_PORT% ===
start "ynfight-backend" /b cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %BACK_PORT%"
rem ===== wait for backend port before starting frontend =====
set /a BACK_READY=0
for /l %%i in (1,1,30) do (
    netstat -ano | findstr %BACK_PORT% | findstr LISTENING >nul
    if not errorlevel 1 (
        set /a BACK_READY=1
        goto backend_ready
    )
    ping -n 2 127.0.0.1 >nul
)
:backend_ready
if !BACK_READY!==0 (
    echo [ERROR] backend did not listen on port %BACK_PORT%
    goto shutdown
)


echo === 后台启动 vite :%FRONT_PORT% ===
start "ynfight-frontend" /b cmd /c "cd /d %~dp0frontend && node node_modules\vite\bin\vite.js --host 127.0.0.1 --port %FRONT_PORT%"

rem ===== 健康检查：轮询等待前后端端口响应；超时则关闭 =====
set /a READY_BACK=0
set /a READY_FRONT=0
for /l %%i in (1,1,30) do (
    if !READY_BACK!==0 (
        netstat -ano | findstr /c:":%BACK_PORT% " | findstr "LISTENING" >nul
        if not errorlevel 1 set /a READY_BACK=1
    )
    if !READY_FRONT!==0 (
        netstat -ano | findstr /c:":%FRONT_PORT% " | findstr "LISTENING" >nul
        if not errorlevel 1 set /a READY_FRONT=1
    )
    if !READY_BACK!==1 if !READY_FRONT!==1 goto ready
    ping -n 2 127.0.0.1 >nul
)
:ready
if !READY_BACK!==0 (
    echo [错误] 后端超时未启动（30s），正在关闭...
    goto shutdown
)
if !READY_FRONT!==0 (
    echo [错误] 前端超时未启动（30s），正在关闭...
    goto shutdown
)

echo.
echo 前后端已在后台启动：
echo   后端 API   http://localhost:%BACK_PORT%/api/docs
echo   前端页面   http://localhost:%FRONT_PORT%
echo.
echo 安全退出：输入 q 回车退出（同时关闭前后端，杀掉两个进程）。
echo ------------------------------------------------------------

:loop
set /p "KEY=输入 q 回车退出："
if /i "%KEY%"=="q" goto shutdown
goto loop

:shutdown
echo.
echo 正在关闭前后端...
call :kill_ports
echo 已安全关闭，无残留进程。
exit /b 0

rem ===== 按端口杀进程（含子进程），最多重试 3 次 =====
:kill_ports
set /a TRY=0
:kill_retry
set /a TRY+=1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /c:":%BACK_PORT% " ^| findstr "LISTENING"') do taskkill /F /T /PID %%P >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /c:":%FRONT_PORT% " ^| findstr "LISTENING"') do taskkill /F /T /PID %%P >nul 2>&1
set /a STILL=0
netstat -ano | findstr /c:":%BACK_PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 set /a STILL=1
netstat -ano | findstr /c:":%FRONT_PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 set /a STILL=1
if !STILL!==1 (
    if !TRY! LSS 3 (
        ping -n 2 127.0.0.1 >nul
        goto kill_retry
    )
)
goto :eof
