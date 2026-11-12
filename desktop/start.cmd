@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .env (
    copy .env.example .env >nul
    echo.
    echo   Создан файл .env
    echo   Впишите в него:
    echo     SECRET  - 32 символа (hex), можно сгенерировать командой:
    echo       python -c "import secrets; print(secrets.token_hex(16))"
    echo     PROXIES - ваши HTTP-прокси, формат user:pass@host:port
    echo.
    notepad .env
    pause
    exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo Python не найден. Установите Python 3 с python.org
    echo и поставьте галочку "Add python.exe to PATH".
    pause
    exit /b 1
)

python -m pip install -r requirements-windows.txt --quiet
if errorlevel 1 (
    echo Не удалось установить зависимости.
    pause
    exit /b 1
)

echo.
echo   Запускаю MTProto и SOCKS5. Ссылки появятся в трее.
echo   Остановить: правый клик по иконке - Exit, либо Ctrl+C.
echo.
python main.py
pause
