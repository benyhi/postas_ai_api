@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "PYTHON_PATH=%PROJECT_ROOT%env\Scripts\python.exe"
set "PORT=%~1"

if not defined PORT set "PORT=8001"

if not exist "%PYTHON_PATH%" (
    echo Error: no se encontro el entorno virtual en "%PYTHON_PATH%".
    echo Crea el entorno e instala requirements.txt antes de iniciar la API.
    exit /b 1
)

pushd "%PROJECT_ROOT%"
"%PYTHON_PATH%" -m uvicorn main:app --host 127.0.0.1 --port "%PORT%" --reload
set "EXIT_CODE=%ERRORLEVEL%"
popd

exit /b %EXIT_CODE%
