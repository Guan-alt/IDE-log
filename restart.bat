@echo off
setlocal enabledelayedexpansion
chcp 936 >nul 2>&1
title OTA ����ƽ̨��������

echo ========================================
echo        OTA ����ƽ̨��������
echo ========================================
echo.

echo [1/4] ����� exe...
tasklist /FI "IMAGENAME eq OTA-Test-Platform.exe" 2>nul | find /I "OTA-Test-Platform.exe" >nul
if %errorlevel% equ 0 (
    taskkill /F /IM OTA-Test-Platform.exe >nul 2>&1
    echo   ��ֹͣ��� exe ����
    timeout /t 2 /nobreak >nul
) else (
    echo   �� exe ����
)

echo.
echo [2/4] ֹͣ python ����...
tasklist /FI "IMAGENAME eq python.exe" 2>nul | find /I "python.exe" >nul
if %errorlevel% equ 0 (
    taskkill /F /IM python.exe >nul 2>&1
    echo   ��ֹͣ python ����
    timeout /t 1 /nobreak >nul
) else (
    echo   �� python ����
)

echo.
echo [3/4] ������������...
cd /d "%~dp0"
start "" /min python app.py

echo.
echo [4/4] �ȴ���������...
set "ok=0"
for /l %%i in (1,1,8) do (
    timeout /t 1 /nobreak >nul
    powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/' -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" >nul 2>&1
    if !errorlevel! equ 0 (
        set "ok=1"
        goto :done
    )
    echo   �ȴ���... (%%i)
)

:done
echo.
if "%ok%"=="1" (
    echo ========================================
    echo   �����ɹ�
    echo   �����ַ: http://127.0.0.1:5000
    echo ========================================
) else (
    echo ========================================
    echo   ����ʧ�ܣ����� app.py �Ƿ��д���
    echo ========================================
)
echo.
pause
