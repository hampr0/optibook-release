@echo off
chcp 949 > nul
title 신성미래서적 - Optibook-IMS 실행기

cd /d "%~dp0"

echo ========================================================
echo   신성미래서적 도서검수시스템 (Optibook-IMS) 시작 중...
echo ========================================================

if not exist "main.py" (
    echo.
    echo [경고] main.py 파일을 찾을 수 없습니다!
    echo 압축(ZIP) 파일 안에서 직접 실행하지 마시고,
    echo 반드시 [압축 풀기]를 완료한 폴더 안에서 실행해 주세요.
    echo.
    pause
    exit /b 1
)

set PYTHON_EXE=

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :CHECK_PKG
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3.12 -c "import sys" >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=py -3.12"
        goto :CHECK_PKG
    )
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :CHECK_PKG
)

:CHECK_PKG
if "%PYTHON_EXE%"=="" (
    echo.
    echo [오류] 파이썬(Python 3.12)을 시스템에서 찾을 수 없습니다!
    echo 파이썬 3.12가 설치되어 있는지 확인해 주세요.
    echo.
    pause
    exit /b 1
)

echo 파이썬 실행기: %PYTHON_EXE%

%PYTHON_EXE% -c "import pymysql, PyQt6, pandas" >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo 필수 라이브러리(PyQt6, pymysql, pandas 등)를 확인/설치 중입니다...
    echo 잠시만 기다려 주세요 (최초 1회만 진행)...
    %PYTHON_EXE% -m pip install pymysql cryptography PyQt6 pandas openpyxl python-dotenv Pillow
    echo.
)

echo 프로그램 창이 열릴 때까지 잠시만 기다려 주세요...
echo.

%PYTHON_EXE% main.py

if %errorlevel% neq 0 (
    echo.
    echo ========================================================
    echo [프로그램 종료 알림]
    echo 오류 코드: %errorlevel%
    echo 오류 원인은 폴더 내 optibook_error.log 파일을 확인하세요.
    echo ========================================================
    echo.
    pause
)
