import subprocess
import threading
import time
import os
from datetime import datetime
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

    def start(self):
        """启动JLink RTT日志采集"""
        try:
            # 创建临时日志输出文件路径（使用ASCII名称避免编码问题）
            log_dir = os.path.join(tempfile.gettempdir(), 'jlink_rtt_logs')
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            safe_name = self.name.encode('ascii', 'replace').decode('ascii').replace('?', 'x')
            self._log_file = os.path.join(log_dir, f"rtt_{safe_name}_{self.jlink_serial}_{timestamp}.log")

            # JLinkRTTLogger.exe 是交互式工具，即使提供了命令行参数仍需通过stdin输入
            # 只通过命令行提供 -selectemubysn（选择JLink），其余通过stdin交互输入
            cmd = [self.rtt_logger_path]
            if self.jlink_serial:
                cmd.extend(['-selectemubysn', self.jlink_serial])

            logger.info(f"JLink RTT Logger 命令: {' '.join(cmd)}")

            # 启动 JLinkRTTLogger 进程
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # 等待进程启动并准备好接收输入
            time.sleep(1)

            # 通过stdin提供交互式参数（顺序：设备名、接口、速率、RTT地址、RTT通道、输出文件）
            interactive_input = "\n".join([
                self.target_device,        # 1. 设备名 e.g. NRF52840_xxAA
                self.interface,            # 2. 接口 e.g. SWD
                str(self.speed),           # 3. 速率 e.g. 4000
                "",                        # 4. RTT控制块地址（空=自动检测）
                str(self.rtt_channel),     # 5. RTT通道索引 e.g. 0
                self._log_file,            # 6. 输出文件路径
            ]) + "\n"

            logger.info(f"JLink {self.name} 发送交互输入: device={self.target_device}, if={self.interface}, speed={self.speed}, ch={self.rtt_channel}")
            self.process.stdin.write(interactive_input)
            self.process.stdin.flush()

            self.is_running = True

            # 启动文件读取线程（持续读取日志文件内容）
            self.file_thread = threading.Thread(target=self._read_file_loop, daemon=True)
            self.file_thread.start()

            # 启动进程监控线程（读取stdout防止管道阻塞）
            self.thread = threading.Thread(target=self._read_stdout_loop, daemon=True)
            self.thread.start()

            logger.info(f"JLink {self.name} 采集已启动 (SN: {self.jlink_serial or '默认'}, 芯片: {self.target_device}, 接口: {self.interface}, 速率: {self.speed}kHz, 日志文件: {self._log_file})")
            return True

        except FileNotFoundError:
            logger.error(f"JLinkRTTLogger.exe 未找到，请检查JLink是否安装")
            self.is_running = False
            return False
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
        """读取JLinkRTTLogger的stdout输出（防止管道阻塞）"""
        while self.is_running and self.process:
            try:
                line = self.process.stdout.readline()
                if line:
                    line_stripped = line.strip()
                    if line_stripped:
                        logger.info(f"JLink {self.name} stdout: {line_stripped}")
                    # 检测错误退出
                    if 'ERROR' in line or 'Failed' in line or 'Shutting down' in line:
                        logger.warning(f"JLink {self.name} 检测到错误: {line_stripped}")
                        self.is_running = False
                        break
                else:
                    if self.process.poll() is not None:
                        logger.warning(f"JLink {self.name} RTT Logger 进程已退出 (code={self.process.returncode})")
                        self.is_running = False
                        break
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f"JLink {self.name} stdout读取异常: {e}")
                self.is_running = False
                break

    def stop(self):
        """停止采集"""
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        if self.file_thread:
            self.file_thread.join(timeout=2)
        if self.thread:
            self.thread.join(timeout=2)
        logger.info(f"JLink {self.name} 采集已停止")

    def get_logs(self):
        """获取当前缓冲区的日志文本"""
        with self._lock:
            return ''.join(self.buffer)

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
