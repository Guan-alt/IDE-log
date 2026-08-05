"""打包专用入口 - 简化版

打包后由 PyInstaller 生成 exe，运行时：
- 模板/静态资源在 _MEIPASS 临时目录
- 数据库/日志在 exe 同级 data/ 目录（持久化，不打包数据）
- 启动前自动清理占用端口的旧服务进程
- 服务启动后自动打开默认浏览器
"""
import os
import subprocess
import threading
import webbrowser
from app import create_app


def kill_port_holders(port):
    """杀掉占用指定端口的进程（避免多实例冲突），失败不阻断启动"""
    try:
        result = subprocess.run(
            ['netstat', '-ano'], capture_output=True, text=True, shell=True
        )
        pids = set()
        for line in result.stdout.splitlines():
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(parts[-1])
        my_pid = str(os.getpid())
        killed = False
        for pid in pids:
            if pid == my_pid:
                continue
            subprocess.run(['taskkill', '/PID', pid, '/F'],
                           capture_output=True, text=True, shell=True)
            print(f'已终止占用端口 {port} 的进程 (PID={pid})')
            killed = True
        if not killed:
            print(f'端口 {port} 空闲，无需清理')
    except Exception as e:
        print(f'清理端口 {port} 失败（忽略）: {e}')


def _open_browser(url, delay=1.5):
    """延迟打开浏览器，等待服务就绪"""
    import time
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == '__main__':
    PORT = 5000
    # 启动前清理占用端口的旧服务进程
    kill_port_holders(PORT)
    app = create_app()
    print("=" * 50)
    print("  OTA测试平台")
    print(f"  访问地址: http://127.0.0.1:{PORT}")
    print("=" * 50)
    # 后台线程：服务就绪后自动打开默认浏览器
    threading.Thread(
        target=_open_browser,
        args=(f'http://127.0.0.1:{PORT}',),
        daemon=True
    ).start()
    # 打包模式：关闭 debug 和 reloader
    app.run(host='0.0.0.0', port=PORT, debug=False)
