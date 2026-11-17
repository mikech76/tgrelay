import asyncio
import logging
import logging.handlers
import os
import sys
import threading

from appdir import ensure_env, fatal, log_path


def _setup_logging():
    handlers = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())

    path = log_path('tgrelay.log')
    if path:
        try:
            handlers.append(logging.handlers.RotatingFileHandler(
                path, maxBytes=1_000_000, backupCount=2, encoding='utf-8'))
        except OSError:
            pass

    logging.basicConfig(
        level=logging.DEBUG if os.environ.get('MTPROXY_DEBUG') else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=handlers,
    )


def run_server():
    if sys.platform == 'win32' and sys.version_info < (3, 14):
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy())

    _setup_logging()

    from server import start_server
    try:
        asyncio.run(start_server())
    except Exception as exc:            # нет прокси, занят порт и т.п.
        logging.getLogger(__name__).exception("server failed")
        fatal(str(exc))
        os._exit(1)


def main():
    if ensure_env() == 'created':
        return

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    from tray_app import TrayApp
    TrayApp().run()


if __name__ == '__main__':
    main()
