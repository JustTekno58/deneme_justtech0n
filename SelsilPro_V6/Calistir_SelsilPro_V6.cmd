@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

echo.
echo ===============================
echo  SelsilPro V6 - Kurulum/Calistir
echo ===============================
echo.

REM Python bul (python veya py launcher)
set "PYEXE="
where py >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=py -3"
)

if "%PYEXE%"=="" (
  where python >nul 2>&1
  if not errorlevel 1 (
    set "PYEXE=python"
  )
)

if "%PYEXE%"=="" (
  echo [HATA] Python bulunamadi.
  echo - Python 3.10+ kurun
  echo - Kurulumda "Add python.exe to PATH" secenegini isaretleyin
  echo.
  pause
  exit /b 1
)

%PYEXE% --version
echo.

REM VENV olustur
if not exist ".venv\Scripts\python.exe" (
  echo [BILGI] Sanal ortam olusturuluyor...
  %PYEXE% -m venv .venv
  if errorlevel 1 (
    echo [HATA] venv olusturma basarisiz.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [HATA] venv aktive edilemedi.
  pause
  exit /b 1
)

echo [BILGI] pip guncelleniyor...
python -m pip install --upgrade pip
if errorlevel 1 (
  echo [HATA] pip guncelleme basarisiz.
  pause
  exit /b 1
)

echo [BILGI] Paketler kuruluyor / guncelleniyor...
pip install -r requirements.txt --upgrade
if errorlevel 1 (
  echo [HATA] requirements kurulumu basarisiz.
  pause
  exit /b 1
)

echo.
echo [BILGI] Program baslatiliyor...
python ana_ekran.py

echo.
echo [BILGI] Program kapandi. Eger sorun varsa "logs" klasorune bakin.
pause
