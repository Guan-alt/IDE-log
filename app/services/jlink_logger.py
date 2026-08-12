import subprocess
import threading
import time
import os
from datetime import datetime, timedelta
import logging
import tempfile

logger = logging.getLogger(__name__)

# JLinkRTTLogger.exe 常见安装路径
JLINK_RTTC_LOGGER_PATHS = [
    r"C:\Program Files\SEGGER\JLink\JLinkRTTLogger.exe",
    r"C:\Program Files (x86)\SEGGER\JLink\JLinkRTTLogger.exe",
]

def find_rtt_logger():
    """查找 JLinkRTTLogger.exe 路径"""
    # 优先从环境变量 PATH 查找
    for path in os.environ.get('PATH', '').split(os.pathsep):
        full = os.path.join(path, 'JLinkRTTLogger.exe')
        if os.path.exists(full):
            return full
    # 查找常见安装路径
    for path in JLINK_RTTC_LOGGER_PATHS:
        if os.path.exists(path):
            return path
    return 'JLinkRTTLogger.exe'


class JLinkLogger:
    """JLink RTT日志采集器，通过 JLinkRTTLogger.exe 持续采集RTT日志"""

    def __init__(self, name, device_sn, jlink_path='', jlink_serial='',
                 rtt_channel=0, target_device='NRF52840_xxAA',
                 interface='SWD', speed=4000):
        self.name = name or 'JLink'
        self.device_sn = device_sn or ''
        self.jlink_serial = jlink_serial or ''
        self.rtt_channel = rtt_channel or 0
        self.target_device = target_device or 'NRF52840_xxAA'
        self.interface = interface or 'SWD'
        self.speed = speed or 4000
        self.rtt_logger_path = find_rtt_logger()
        self.process = None
        self.thread = None
        self.file_thread = None
        self.is_running = False
        self.buffer = []
        self._lock = threading.Lock()
        self._log_file = None
        self._last_pos = 0
        self._retry_count = 0          # 连接失败重试计数
        self._MAX_RETRIES = 3          # 最多重试3次
        self._RETRY_DELAY = 5          # 重试间隔（秒）

    def _start_process(self):
        """启动（或重启）JLinkRTTLogger 进程并发送交互参数。
        成功返回 True，失败返回 False。可被 start() 和重试逻辑复用。"""
        try:
            cmd = [self.rtt_logger_path]
            if self.jlink_serial:
                cmd.extend(['-selectemubysn', self.jlink_serial])

            logger.info(f"JLink RTT Logger 命令: {' '.join(cmd)}")

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            time.sleep(1)

            interactive_input = "\n".join([
                self.target_device,
                self.interface,
                str(self.speed),
                "",
                str(self.rtt_channel),
                self._log_file,
            ]) + "\n"

            logger.info(f"JLink {self.name} 发送交互输入: device={self.target_device}, if={self.interface}, speed={self.speed}, ch={self.rtt_channel}")
            self.process.stdin.write(interactive_input)
            self.process.stdin.flush()
            return True
        except FileNotFoundError:
            logger.error(f"JLinkRTTLogger.exe 未找到，请检查JLink是否安装")
            return False
        except Exception as e:
            logger.error(f"JLink {self.name} 启动进程失败: {e}")
            return False

    def start(self):
        """启动JLink RTT日志采集"""
        try:
            log_dir = os.path.join(tempfile.gettempdir(), 'jlink_rtt_logs')
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            safe_name = self.name.encode('ascii', 'replace').decode('ascii').replace('?', 'x')
            self._log_file = os.path.join(log_dir, f"rtt_{safe_name}_{self.jlink_serial}_{timestamp}.log")

            if not self._start_process():
                self.is_running = False
                return False

            self.is_running = True
            self._retry_count = 0

            self.file_thread = threading.Thread(target=self._read_file_loop, daemon=True)
            self.file_thread.start()

            self.thread = threading.Thread(target=self._read_stdout_loop, daemon=True)
            self.thread.start()

            logger.info(f"JLink {self.name} 采集已启动 (SN: {self.jlink_serial or '默认'}, 芯片: {self.target_device}, 接口: {self.interface}, 速率: {self.speed}kHz, 日志文件: {self._log_file})")
            return True

        except Exception as e:
            logger.error(f"JLink {self.name} 启动失败: {e}")
            self.is_running = False
            return False

    def _read_file_loop(self):
        """后台线程持续读取RTT日志文件内容"""
        # 等待日志文件创建
        wait_count = 0
        while self.is_running and not os.path.exists(self._log_file) and wait_count < 30:
            time.sleep(0.5)
            wait_count += 1

        while self.is_running:
            try:
                if os.path.exists(self._log_file):
                    with open(self._log_file, 'r', encoding='utf-8', errors='replace') as f:
                        f.seek(self._last_pos)
                        content = f.read()
                        if content:
                            now = datetime.now()
                            ts = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}.{now.microsecond // 1000:03d}] "
                            with self._lock:
                                self.buffer.append(ts + content)
                                # 限制缓冲区大小
                                total = sum(len(s) for s in self.buffer)
                                while total > 500000:  # 最多500KB
                                    self.buffer.pop(0)
                                    total = sum(len(s) for s in self.buffer)
                            self._last_pos = f.tell()
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"JLink {self.name} 读取日志文件异常: {e}")
                time.sleep(1)

    def _read_stdout_loop(self):
        """读取JLinkRTTLogger的stdout输出（防止管道阻塞）。
        遇到连接错误时自动重试（最多 MAX_RETRIES 次），而非直接终止。"""
        # 可恢复的错误模式：连接失败、目标无响应等
        RECOVERABLE_ERRORS = [
            'Could not connect to target',
            'Failed to',
            'Connection refused',
            'Target not found',
            'No device found',
        ]
        while self.is_running:
            if not self.process or self.process.poll() is not None:
                # 进程已退出
                if self.process:
                    logger.warning(f"JLink {self.name} RTT Logger 进程已退出 (code={self.process.returncode})")
                self.is_running = self._retry_or_fail()
                break
            try:
                line = self.process.stdout.readline()
                if line:
                    line_stripped = line.strip()
                    if line_stripped:
                        logger.info(f"JLink {self.name} stdout: {line_stripped}")
                    # 判断是否为可恢复错误（连接失败等）
                    is_recoverable = any(err in line for err in RECOVERABLE_ERRORS)
                    if is_recoverable:
                        logger.warning(f"JLink {self.name} 连接错误(第{self._retry_count + 1}次): {line_stripped}")
                        self.is_running = self._retry_or_fail()
                        break
                    # 不可恢复错误（如 JLinkRTTLogger 自身崩溃）才直接终止
                    if 'Shutting down' in line:
                        logger.warning(f"JLink {self.name} JLinkRTTLogger 关闭: {line_stripped}")
                        self.is_running = self._retry_or_fail()
                        break
                else:
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f"JLink {self.name} stdout读取异常: {e}")
                self.is_running = self._retry_or_fail()
                break

    def _retry_or_fail(self):
        """清理旧进程并在允许时重试连接。返回 True 表示已重试（继续运行），False 表示放弃。"""
        # 清理旧进程
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=2)
                except Exception:
                    pass
            self.process = None

        if self._retry_count >= self._MAX_RETRIES:
            logger.error(f"JLink {self.name} 已达最大重试次数({self._MAX_RETRIES})，停止采集")
            return False

        self._retry_count += 1
        logger.info(f"JLink {self.name} {self._RETRY_DELAY}秒后重试连接(第{self._retry_count}/{self._MAX_RETRIES}次)...")

        # 可中断的等待
        for _ in range(self._RETRY_DELAY):
            if not self.is_running:
                return False
            time.sleep(1)

        if not self.is_running:
            return False

        # 重启进程（复用已有的日志文件和 _last_pos）
        if not self._start_process():
            logger.error(f"JLink {self.name} 重试启动进程失败")
            return False

        logger.info(f"JLink {self.name} 重试已启动(第{self._retry_count}/{self._MAX_RETRIES}次)")
        # 重新启动 stdout 监控线程
        self.thread = threading.Thread(target=self._read_stdout_loop, daemon=True)
        self.thread.start()
        return True

    def drain(self):
        """主动做一次最终读取，将RTT日志文件中尚未被_read_file_loop读到的数据拉入buffer。
        返回本次新读取的字符数。用于保存日志前确保数据完整。"""
        if not self._log_file or not os.path.exists(self._log_file):
            return 0
        try:
            with open(self._log_file, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(self._last_pos)
                content = f.read()
                if content:
                    now = datetime.now()
                    ts = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}.{now.microsecond // 1000:03d}] "
                    with self._lock:
                        self.buffer.append(ts + content)
                        total = sum(len(s) for s in self.buffer)
                        while total > 500000:
                            self.buffer.pop(0)
                            total = sum(len(s) for s in self.buffer)
                    self._last_pos = f.tell()
                    return len(content)
        except Exception as e:
            logger.error(f"JLink {self.name} drain读取异常: {e}")
        return 0

    def stop(self):
        """停止采集：先终止JLink进程，再等待线程退出"""
        self.is_running = False
        # 先终止JLink进程，使 _read_stdout_loop 中的 readline 立即返回EOF退出
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=2)
                except Exception:
                    pass
        if self.file_thread:
            self.file_thread.join(timeout=3)
        if self.thread:
            self.thread.join(timeout=3)
        logger.info(f"JLink {self.name} 采集已停止")

    def get_logs(self):
        """获取当前缓冲区的日志文本"""
        with self._lock:
            return ''.join(self.buffer)

    @staticmethod
    def _parse_chunk_time(chunk):
        """解析 chunk 开头的时间戳 [YYYY-MM-DD HH:MM:SS.fff]，失败返回 None"""
        try:
            end = chunk.find(']')
            if chunk.startswith('[') and end > 0:
                ts_str = chunk[1:end]
                return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
        except Exception:
            pass
        return None

    def get_logs_since(self, start_time, pre_seconds=10):
        """获取时间戳 >= (start_time - pre_seconds) 的日志文本。
        用于循环/单次 OTA 只截取该轮期间的日志，往前多留 pre_seconds 秒上下文"""
        if not start_time:
            return self.get_logs()
        threshold = start_time - timedelta(seconds=pre_seconds)
        with self._lock:
            kept = []
            for chunk in self.buffer:
                ct = self._parse_chunk_time(chunk)
                if ct is None or ct >= threshold:
                    kept.append(chunk)
            return ''.join(kept)

    def save_to_file(self, folder_path):
        """将缓冲区日志保存到文件"""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"jlink_{self.name}_{self.device_sn}_{timestamp}.log"
        filepath = os.path.join(folder_path, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            with self._lock:
                f.write(''.join(self.buffer))
        logger.info(f"JLink {self.name} 日志已保存: {filepath}")
        return filepath

    def save_to_file_since(self, folder_path, start_time, pre_seconds=10):
        """只保存时间戳 >= (start_time - pre_seconds) 的日志到文件"""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"jlink_{self.name}_{self.device_sn}_{timestamp}.log"
        filepath = os.path.join(folder_path, filename)
        content = self.get_logs_since(start_time, pre_seconds)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"JLink {self.name} 日志已保存(时间窗口 {start_time}): {filepath}")
        return filepath
