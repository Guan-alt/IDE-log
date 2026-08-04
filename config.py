# OTA监控平台配置文件
import os


class Config:
    """默认配置"""

    # OTA接口配置（test环境）
    OTA_URL = "https://test-lkadmin-lockin-management.lockin.com"  # test环境
    OTA_TOKEN = "b75ddf6b4ef81b005484ca00c382c76c"
    OTA_TIMEOUT = 3600  # 秒

    # 数据库配置 - 使用绝对路径指向 instance 目录
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'ota_monitor.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # AI分析配置
    AI_API_KEY = ""  # 留空，运行时配置
    AI_MODEL = "doubao"
    AI_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

    # 串口配置
    SERIAL_DEFAULT_BAUDRATE = 115200

    # Flask密钥
    SECRET_KEY = "ota-monitor-secret-key"
