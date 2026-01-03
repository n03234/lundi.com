import sys
import os
import subprocess
import webbrowser
import threading
import queue
import time
import urllib.request
import urllib.error
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PROJECT_ROOT = os.path.dirname(HERE)
PORT = int(os.environ.get('SNS_PORT', '5000'))
BASE_URL = f'http://127.0.0.1:{PORT}'


class ServerManager:
    def __init__(self):
        self.proc = None
        self._q = queue.Queue()
        self._threads = []

    def start(self):
        if self.proc and self.proc.poll() is None:
            return True
        # Run package-local runner so imports work from project root
        cmd = [PY, '-m', 'sns_app.run']
        # start subprocess in project root so module imports work
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=PROJECT_ROOT,
            bufsize=1,
            universal_newlines=True,
        )
        # start reader threads
        t1 = threading.Thread(target=self._reader_thread, args=(self.proc.stdout, 'OUT'), daemon=True)
        t2 = threading.Thread(target=self._reader_thread, args=(self.proc.stderr, 'ERR'), daemon=True)
        t1.start(); t2.start()
        self._threads = [t1, t2]
        return True

    def _reader_thread(self, stream, tag):
        try:
            for line in iter(stream.readline, ''):
                if not line:
                    break
                self._q.put((tag, line.rstrip('\n')))
        except Exception:
            pass

    def read_logs(self):
        lines = []
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            lines.append(item)
        return lines

    def stop(self):
        if not self.proc:
            return
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None


def health_check(timeout=0.5):
    url = f'{BASE_URL}/health'
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def open_browser():
    webbrowser.open(BASE_URL)


def main():
    mgr = ServerManager()

    root = tk.Tk()
    root.title('Mini SNS Launcher')
    root.geometry('640x420')

    top = tk.Frame(root, padx=12, pady=8)
    top.pack(fill='x')

    status_var = tk.StringVar(value='サーバ: 停止')

    lbl = tk.Label(top, text='Mini SNS ランチャー', font=('Segoe UI', 14))
    lbl.pack(side='left')

    status_lbl = tk.Label(top, textvariable=status_var)
    status_lbl.pack(side='right')

    btn_frame = tk.Frame(root, padx=12, pady=8)
    btn_frame.pack(fill='x')

    def start_cb():
        mgr.start()
        status_var.set('サーバ: 起動中 (starting...)')
        root.after(300, poll_health)

    def stop_cb():
        mgr.stop()
        status_var.set('サーバ: 停止')

    btn_start = tk.Button(btn_frame, text='サーバ起動', width=16, command=start_cb)
    btn_start.pack(side='left', padx=6)

    btn_open = tk.Button(btn_frame, text='ブラウザで開く', width=16, command=open_browser, state='disabled')
    btn_open.pack(side='left', padx=6)

    btn_stop = tk.Button(btn_frame, text='サーバ停止', width=16, command=stop_cb)
    btn_stop.pack(side='left', padx=6)

    # Log area
    log_label = tk.Label(root, text='サーバログ')
    log_label.pack(anchor='w', padx=12)
    log_text = tk.Text(root, height=14, wrap='none')
    log_text.pack(fill='both', expand=True, padx=12, pady=(0,12))

    def poll_health():
        if mgr.is_running() and health_check(timeout=0.3):
            status_var.set('サーバ: 起動中 (ready)')
            btn_open.config(state='normal')
        else:
            if mgr.is_running():
                status_var.set('サーバ: 起動中 (starting...)')
                btn_open.config(state='disabled')
                root.after(500, poll_health)
            else:
                status_var.set('サーバ: 停止')
                btn_open.config(state='disabled')

    def poll_logs_periodic():
        for tag, line in mgr.read_logs():
            t = f'[{tag}] {line}\n'
            log_text.insert('end', t)
            log_text.see('end')
        root.after(200, poll_logs_periodic)

    def on_close():
        try:
            mgr.stop()
        except Exception:
            pass
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', on_close)
    root.after(200, poll_logs_periodic)
    root.mainloop()


if __name__ == '__main__':
    main()
