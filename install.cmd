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
goto install

:use_py
set "RUNNER=py -3 "%~dp0auto_login.py""
goto install

:use_python
set "RUNNER=python "%~dp0auto_login.py""

:install

echo.
echo === 1/2 填写账号信息 ===
%RUNNER% setup
if errorlevel 1 (
    echo [!] 配置未完成
    pause
    exit /b 1
)

echo.
echo === 2/2 安装计划任务 ===
%RUNNER% install
if errorlevel 1 (
    echo [!] 安装或首次试运行未完成，请查看上方说明及日志。
    pause
    exit /b 1
)

echo.
echo 安装完成。登录 Windows 后会按计划检查校园网连接。
echo 请保留整个文件夹；移动文件夹后需要重新安装计划任务。
echo 查看日志： logs\auto_login.log
echo.
pause
exit /b 0

:missing_runtime
echo.
echo [!] 没有找到可执行版，也没有可用的 Python 3.8+。
echo     无需安装 Python：请从 GitHub Releases 下载 windows-x64.zip，
echo     将整个压缩包解压后，再双击其中的 install.cmd。
echo     源码用户可安装 Python 3.8+ 后重试。
echo.
pause
exit /b 1
