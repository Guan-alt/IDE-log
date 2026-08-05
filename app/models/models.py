from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(db.Model):
    """用户模型"""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'is_admin': self.is_admin,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class Device(db.Model):
    """设备模型"""
    __tablename__ = 'devices'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    sn = db.Column(db.String(100), unique=True, nullable=False)  # 设备SN号
    name = db.Column(db.String(100))  # 设备名称
    current_version = db.Column(db.String(50))  # 当前固件版本
    status = db.Column(db.String(20), default='idle')  # 状态: idle/upgrading/success/failed
    env_id = db.Column(db.Integer, db.ForeignKey('ota_environments.id'), nullable=True)  # 关联OTA环境
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'sn': self.sn,
            'name': self.name,
            'current_version': self.current_version,
            'status': self.status,
            'env_id': self.env_id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class OtaRecord(db.Model):
    """OTA测试记录模型"""
    __tablename__ = 'ota_records'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('test_tasks.id'), nullable=True)  # 关联测试任务
    device_sn = db.Column(db.String(100), nullable=False)  # 设备SN
    source_version = db.Column(db.String(50))  # 来源版本
    target_version = db.Column(db.String(50))  # 目标版本
    result = db.Column(db.String(50))  # 结果: OTA升级成功/OTA升级超时/OTA请求失败/获取版本失败
    duration = db.Column(db.Float, default=0)  # 耗时（秒）
    upgrade_percent = db.Column(db.Float, default=0)  # 升级进度
    download_percent = db.Column(db.Float, default=0)  # 下载进度
    start_time = db.Column(db.DateTime)  # 开始时间
    end_time = db.Column(db.DateTime)  # 结束时间
    fail_reason = db.Column(db.Text)  # 失败原因
    log_paths = db.Column(db.Text)  # 日志文件路径（JSON数组格式，存储串口和JLink日志路径）
    ai_analysis = db.Column(db.Text)  # AI分析报告

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'device_sn': self.device_sn,
            'source_version': self.source_version,
            'target_version': self.target_version,
            'result': self.result,
            'duration': self.duration,
            'upgrade_percent': self.upgrade_percent,
            'download_percent': self.download_percent,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else None,
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else None,
            'fail_reason': self.fail_reason,
            'log_paths': self.log_paths,
            'ai_analysis': self.ai_analysis
        }


class TestTask(db.Model):
    """测试任务模型 - 用户手动创建，OTA记录归属到任务以分组统计"""
    __tablename__ = 'test_tasks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name = db.Column(db.String(200), nullable=False)  # 任务名称
    description = db.Column(db.Text)  # 任务描述
    status = db.Column(db.String(20), default='进行中')  # 进行中 / 已完成
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)  # 结束时间

    def to_dict(self):
        from sqlalchemy import func
        record_count = db.session.query(func.count(OtaRecord.id)).filter(
            OtaRecord.task_id == self.id
        ).scalar() or 0
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'record_count': record_count,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'ended_at': self.ended_at.strftime('%Y-%m-%d %H:%M:%S') if self.ended_at else None
        }


class LogConfig(db.Model):
    """日志采集配置模型 - 支持串口和JLink两种类型"""
    __tablename__ = 'log_configs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    log_type = db.Column(db.String(20), nullable=False, default='serial')  # 类型: serial/jlink
    name = db.Column(db.String(100))  # 名称/备注，如"门锁主控"
    device_sn = db.Column(db.String(100))  # 关联设备SN
    enabled = db.Column(db.Boolean, default=False)  # 是否启用
    # 串口专用字段
    port = db.Column(db.String(20))  # 串口号，如 COM3（log_type=serial时使用）
    baudrate = db.Column(db.Integer, default=115200)  # 波特率
    # JLink专用字段
    jlink_path = db.Column(db.String(200))  # JLink.exe路径（为空则使用系统PATH）
    jlink_serial = db.Column(db.String(50))  # JLink序列号（自动扫描）
    rtt_channel = db.Column(db.Integer, default=0)  # RTT通道号
    target_device = db.Column(db.String(50))  # 目标芯片型号，如 NRF52840_xxAA
    interface = db.Column(db.String(10), default='SWD')  # 调试接口: SWD/JTAG
    speed = db.Column(db.Integer, default=4000)  # 调试速率: kHz
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'log_type': self.log_type,
            'name': self.name,
            'device_sn': self.device_sn,
            'enabled': self.enabled,
            'port': self.port,
            'baudrate': self.baudrate,
            'jlink_path': self.jlink_path,
            'jlink_serial': self.jlink_serial,
            'rtt_channel': self.rtt_channel,
            'target_device': self.target_device,
            'interface': self.interface,
            'speed': self.speed,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class Setting(db.Model):
    """系统配置模型"""
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ota_url = db.Column(db.String(200), default='https://test-lkadmin-lockin-management.lockin.com')
    token = db.Column(db.String(200), default='b75ddf6b4ef81b005484ca00c382c76c')
    ota_url_online = db.Column(db.String(200), default='')
    token_online = db.Column(db.String(200), default='')
    ota_timeout = db.Column(db.Integer, default=3600)
    ai_api_key = db.Column(db.String(200))  # AI API Key
    ai_model = db.Column(db.String(50), default='doubao')  # AI 模型
    ai_base_url = db.Column(db.String(200), default='https://ark.cn-beijing.volces.com/api/v3')  # AI API地址
    serial_default_baudrate = db.Column(db.Integer, default=115200)
    
    def to_dict(self):
        return {
            'id': self.id,
            'ota_url': self.ota_url,
            'token': self.token,
            'ota_url_online': self.ota_url_online,
            'token_online': self.token_online,
            'ota_timeout': self.ota_timeout,
            'ai_api_key': self.ai_api_key,
            'ai_model': self.ai_model,
            'ai_base_url': self.ai_base_url,
            'serial_default_baudrate': self.serial_default_baudrate
        }


class OtaEnvironment(db.Model):
    """OTA升级环境 - 用户自行管理多个OTA服务器环境"""
    __tablename__ = 'ota_environments'
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='uq_user_env_name'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)  # 环境名称，如"线下"/"线上"/"预发布"
    ota_url = db.Column(db.String(200), nullable=False)
    token = db.Column(db.String(200), nullable=False, default='')
    region = db.Column(db.String(10), default='cn')  # 区域: cn=国内 os=国外（查询设备版本方式不同）
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'ota_url': self.ota_url,
            'token': self.token,
            'region': self.region or 'cn',
            'sort_order': self.sort_order,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
