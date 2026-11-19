@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0HHUCampusAutoLogin.exe" goto use_exe
if not exist "%~dp0auto_login.py" goto missing_runtime
py -3 -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul
if not errorlevel 1 goto use_python
goto missing_runtime

:use_exe
set "RUNNER="%~dp0HHUCampusAutoLogin.exe""
goto uninstall

:use_py
set "RUNNER=py -3 "%~dp0auto_login.py""
goto uninstall

:use_python
set "RUNNER=python "%~dp0auto_login.py""

:uninstall
echo 正在删除计划任务...
%RUNNER% uninstall
if errorlevel 1 (
    echo [!] 删除失败，请查看上方说明。任务可能已经删除。
    pause
    exit /b 1
)
echo.
echo 计划任务已删除。如果需要彻底删除，再删除本文件夹即可。
pause
exit /b 0

:missing_runtime
echo [!] 请使用完整的可执行版解压目录，或准备 Python 3.8+ 后重试。
pause
exit /b 1
