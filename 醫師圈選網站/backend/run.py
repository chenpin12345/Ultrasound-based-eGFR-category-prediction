"""啟動網站：只綁本機，找一個空的連接埠，開啟瀏覽器。關閉這個視窗就會停止網站。"""
from __future__ import annotations

import os
import socket
import threading
import webbrowser

import uvicorn

from app.main import create_app

HOST = '127.0.0.1'
PORTS = range(8100, 8120)  # 主系統用 8000–8019


def free_port() -> int:
    for port in PORTS:
        with socket.socket() as sock:
            try:
                sock.bind((HOST, port))
                return port
            except OSError:
                continue
    raise SystemExit('找不到可用的連接埠（8100–8119）。請關閉其他程式後再試一次。')


def main() -> None:
    port = free_port()
    url = f'http://{HOST}:{port}'
    print(f'醫師圈選網站已啟動：{url}')
    print('使用期間請不要關閉這個視窗。')
    if not os.environ.get('CIRCLE_NO_BROWSER'):
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    uvicorn.run(create_app(), host=HOST, port=port, log_level='warning', log_config=None)


if __name__ == '__main__':
    main()
