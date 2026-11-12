import asyncio
import logging
import logging.handlers
import os
import sys
import threading


def _setup_logging():
    handlers = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'mtproxy.log')
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
    asyncio.run(start_server())


def main():
    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    from tray_app import TrayApp
    TrayApp().run()


if __name__ == '__main__':
    main()
