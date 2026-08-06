import serial
import serial.tools.list_ports
import threading
import time
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SerialLogger:
    """单个串口日志采集器"""
    
    def __init__(self, port, baudrate, name, device_sn):
        self.port = port
        self.baudrate = baudrate
        self.name = name or port
        self.device_sn = device_sn or ''
        self.serial_conn = None
        self.thread = None
        self.is_running = False
        self.buffer = []  # 日志缓冲区
        self._lock = threading.Lock()
    
    def start(self):
        """打开串口并启动后台读取线程"""
        try:
            self.serial_conn = serial.Serial(
                self.port,
                self.baudrate,
                timeout=1
            )
            self.is_running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            logger.info(f"串口 {self.name} ({self.port}) 采集已启动")
            return True
        except Exception as e:
            logger.error(f"串口 {self.name} ({self.port}) 打开失败: {e}")
            self.is_running = False
            return False
    
    def _read_loop(self):
        """后台线程持续读取串口数据"""
        while self.is_running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    text = data.decode('utf-8', errors='replace')
                    now = datetime.now()
                    ts = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}.{now.microsecond // 1000:03d}] "
                    with self._lock:
                        self.buffer.append(ts + text)
                else:
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"串口 {self.name} ({self.port}) 读取异常: {e}")
                self.is_running = False
                break
    
    def stop(self):
        """停止采集"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        logger.info(f"串口 {self.name} ({self.port}) 采集已停止")
    
    def get_logs(self):
        """获取当前缓冲区的日志文本"""
        with self._lock:
            return ''.join(self.buffer)
    
    def save_to_file(self, folder_path):
        """将缓冲区日志保存到文件"""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"serial_{self.name}_{self.device_sn}_{timestamp}.log"
        filepath = os.path.join(folder_path, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            with self._lock:
                f.write(''.join(self.buffer))
        logger.info(f"串口 {self.name} 日志已保存: {filepath}")
        return filepath


class SerialManager:
    """多串口日志采集管理器"""
    
    def __init__(self):
        self.loggers = {}  # key: config_id, value: SerialLogger
    
    def add_logger(self, config_id, port, baudrate, name, device_sn):
        """添加一个串口采集器"""
        if config_id in self.loggers:
            logger.warning(f"串口配置 {config_id} 已存在，先移除旧的")
            self.remove_logger(config_id)
        self.loggers[config_id] = SerialLogger(port, baudrate, name, device_sn)
        logger.info(f"已添加串口采集器: {name} ({port})")
    
    def remove_logger(self, config_id):
        """移除并停止一个串口采集器"""
        if config_id in self.loggers:
            self.loggers[config_id].stop()
            del self.loggers[config_id]
            logger.info(f"已移除串口采集器: {config_id}")
    
    def start_all(self):
        """启动所有已添加的采集器"""
        results = []
        for config_id, serial_logger in self.loggers.items():
            success = serial_logger.start()
            results.append({'config_id': config_id, 'port': serial_logger.port, 'name': serial_logger.name, 'success': success})
        return results
    
    def stop_all(self):
        """停止所有采集器"""
        for config_id, serial_logger in self.loggers.items():
            serial_logger.stop()
        logger.info("所有串口采集已停止")
    
    def start_one(self, config_id):
        """启动单个采集器"""
        if config_id in self.loggers:
            return self.loggers[config_id].start()
        return False
    
    def stop_one(self, config_id):
        """停止单个采集器"""
        if config_id in self.loggers:
            self.loggers[config_id].stop()
            return True
        return False
    
    def get_logs(self, config_id):
        """获取指定串口的实时日志"""
        if config_id in self.loggers:
            return self.loggers[config_id].get_logs()
        return ""
    
    def save_all_logs(self, folder_path):
        """保存所有采集器的日志到文件"""
        filepaths = []
        for config_id, serial_logger in self.loggers.items():
            if serial_logger.is_running or serial_logger.get_logs():
                filepath = serial_logger.save_to_file(folder_path)
                filepaths.append(filepath)
        return filepaths
    
    def get_status(self):
        """获取所有串口的运行状态"""
        return {
            config_id: {
                'port': sl.port,
                'name': sl.name,
                'device_sn': sl.device_sn,
                'is_running': sl.is_running
            }
            for config_id, sl in self.loggers.items()
        }


# 全局单例
serial_manager = SerialManager()
