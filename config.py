# OTA监控平台配置文件
import os
import sys


def _get_app_data_dir():
    """获取应用数据目录（用于持久化数据库/日志）

    - 打包模式（PyInstaller）：exe 同级目录下的 data 子目录
    - 开发模式：项目根目录下的 instance 目录（保持原有数据位置）
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        exe_dir = os.path.dirname(sys.executable)
        data_dir = os.path.join(exe_dir, 'data')
    else:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


class Config:
    """默认配置"""

    # OTA接口配置（test环境）
    OTA_URL = "https://test-lkadmin-lockin-management.lockin.com"  # test环境
    OTA_TOKEN = "b75ddf6b4ef81b005484ca00c382c76c"
    OTA_TIMEOUT = 3600  # 秒

    # 数据库配置 - 打包模式放在 exe 同级 data 目录（持久化，不打包数据）
    BASE_DIR = _get_app_data_dir()
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'ota_monitor.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # AI分析配置
    AI_API_KEY = ""  # 留空，运行时配置
    AI_MODEL = "doubao"
    AI_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

    # 串口配置
    SERIAL_DEFAULT_BAUDRATE = 115200

    # Flask密钥
    SECRET_KEY = "ota-monitor-secret-key"
