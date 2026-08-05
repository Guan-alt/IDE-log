import os
import sys
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import inspect

db = SQLAlchemy()


def _is_frozen():
    """是否运行在 PyInstaller 打包环境中"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


# 内置 OTA 环境：全新部署自动写入（用户后续可自行增删改）
# (名称, OTA地址, Token, 区域: cn=国内 os=国外)
BUILTIN_ENVIRONMENTS = [
    ('国内测试', 'https://test-lkadmin-lockin-management.lockin.com', 'b75ddf6b4ef81b005484ca00c382c76c', 'cn'),
    ('国内线上', 'https://lkadmin-lockin-management.lockin.com', '64e34390c66a370177b30f2441cb8cdc', 'cn'),
    ('北美开发', 'https://dev-lkuadmin-management-platform.lockin.com', 'ad41cce042be131a75a2c9afbd723537', 'os'),
    ('北美测试', 'https://test-lkuadmin-management-platform.lockin.com', '6402ab947ccd25de841e9eeebdc534b6', 'os'),
]


def create_app():
    # 打包模式下：模板/静态资源从 _MEIPASS 加载（PyInstaller 临时解压目录）
    if _is_frozen():
        base = sys._MEIPASS
        app = Flask(
            __name__,
            template_folder=os.path.join(base, 'app', 'templates'),
            static_folder=os.path.join(base, 'app', 'static'),
        )
    else:
        app = Flask(__name__)
    app.config.from_object('config.Config')
    app.secret_key = 'ota-monitor-secret-key-2026'

    # 初始化CORS
    CORS(app, supports_credentials=True)

    # 初始化数据库
    db.init_app(app)

    with app.app_context():
        from app.models.models import Device, OtaRecord, LogConfig, Setting, User, TestTask, OtaEnvironment
        db.create_all()

        # 数据库迁移：为已存在的 ota_records 表补充 task_id 列
        inspector = inspect(db.engine)
        if 'ota_records' in inspector.get_table_names():
            existing_cols = {c['name'] for c in inspector.get_columns('ota_records')}
            if 'task_id' not in existing_cols:
                with db.engine.begin() as conn:
                    conn.exec_driver_sql(
                        'ALTER TABLE ota_records ADD COLUMN task_id INTEGER REFERENCES test_tasks(id)'
                    )
                print('Migration: ota_records.task_id column added')

        # 数据库迁移：为已存在的 devices 表补充 env_id 列
        if 'devices' in inspector.get_table_names():
            existing_cols = {c['name'] for c in inspector.get_columns('devices')}
            if 'env_id' not in existing_cols:
                with db.engine.begin() as conn:
                    conn.exec_driver_sql(
                        'ALTER TABLE devices ADD COLUMN env_id INTEGER REFERENCES ota_environments(id)'
                    )
                print('Migration: devices.env_id column added')

        # 数据库迁移：为已存在的 ota_environments 表补充 region 列
        if 'ota_environments' in inspector.get_table_names():
            existing_cols = {c['name'] for c in inspector.get_columns('ota_environments')}
            if 'region' not in existing_cols:
                with db.engine.begin() as conn:
                    conn.exec_driver_sql(
                        "ALTER TABLE ota_environments ADD COLUMN region VARCHAR(10) DEFAULT 'cn'"
                    )
                print('Migration: ota_environments.region column added')

        # 初始化默认admin用户
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', display_name='Administrator', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            # 将无user_id的现有数据关联到admin
            admin_id = admin.id
            for d in Device.query.filter_by(user_id=None).all():
                d.user_id = admin_id
            for r in OtaRecord.query.filter_by(user_id=None).all():
                r.user_id = admin_id
            for lc in LogConfig.query.filter_by(user_id=None).all():
                lc.user_id = admin_id
            for s in Setting.query.filter_by(user_id=None).all():
                s.user_id = admin_id
            db.session.commit()
            print(f'Default admin user created (id={admin_id}), existing data migrated')

        # 如果没有设置记录，创建默认设置
        if not Setting.query.first():
            from config import Config
            setting = Setting(
                ota_url=Config.OTA_URL,
                token=Config.OTA_TOKEN,
                ota_timeout=Config.OTA_TIMEOUT,
                ai_api_key=Config.AI_API_KEY,
                ai_model=Config.AI_MODEL,
                ai_base_url=Config.AI_BASE_URL,
                serial_default_baudrate=Config.SERIAL_DEFAULT_BAUDRATE
            )
            db.session.add(setting)
            db.session.commit()

        # 内置 OTA 环境：默认用户（admin）没有任何环境时播种内置的 4 个环境
        # 用户已有环境则不动，后续可自行增删改
        admin_user_seed = User.query.filter_by(username='admin').first()
        if admin_user_seed:
            if OtaEnvironment.query.filter_by(user_id=admin_user_seed.id).count() == 0:
                for name, url, token, region in BUILTIN_ENVIRONMENTS:
                    db.session.add(OtaEnvironment(
                        user_id=admin_user_seed.id, name=name, ota_url=url,
                        token=token, region=region, sort_order=0
                    ))
                db.session.commit()
                print('Migration: builtin OTA environments seeded for admin')

        # 全局单用户迁移：将历史多用户数据统一归并到默认用户（admin）
        # 已移除用户登录功能，所有查询均按默认用户过滤，历史归属其他用户的数据须归并，否则不可见
        admin_user = User.query.filter_by(username='admin').first()
        if admin_user:
            admin_id = admin_user.id
            total = 0

            # 设备 / 记录 / 任务 / 日志配置：直接改归属（均无唯一约束冲突）
            for d in Device.query.filter(db.or_(Device.user_id.is_(None), Device.user_id != admin_id)).all():
                d.user_id = admin_id
                total += 1
            for r in OtaRecord.query.filter(db.or_(OtaRecord.user_id.is_(None), OtaRecord.user_id != admin_id)).all():
                r.user_id = admin_id
                total += 1
            for t in TestTask.query.filter(db.or_(TestTask.user_id.is_(None), TestTask.user_id != admin_id)).all():
                t.user_id = admin_id
                total += 1
            for lc in LogConfig.query.filter(db.or_(LogConfig.user_id.is_(None), LogConfig.user_id != admin_id)).all():
                lc.user_id = admin_id
                total += 1

            # 设置：admin 已有设置则废弃其他用户设置；否则归并第一条
            other_settings = Setting.query.filter(
                db.or_(Setting.user_id.is_(None), Setting.user_id != admin_id)
            ).all()
            if Setting.query.filter_by(user_id=admin_id).first():
                for s in other_settings:
                    db.session.delete(s)
                    total += 1
            else:
                for s in other_settings[:1]:
                    s.user_id = admin_id
                    total += 1
                for s in other_settings[1:]:
                    db.session.delete(s)
                    total += 1

            # OTA环境：(user_id, name) 唯一，重名保留 admin 的，其余迁移
            existing_env_names = {e.name for e in OtaEnvironment.query.filter_by(user_id=admin_id).all()}
            for e in OtaEnvironment.query.filter(
                db.or_(OtaEnvironment.user_id.is_(None), OtaEnvironment.user_id != admin_id)
            ).all():
                if e.name in existing_env_names:
                    db.session.delete(e)
                else:
                    e.user_id = admin_id
                    existing_env_names.add(e.name)
                total += 1

            db.session.commit()
            if total:
                print(f'Migration: merged {total} records to default user (admin id={admin_id})')

    # 注册API蓝图
    from app.api.devices import devices_bp
    from app.api.ota import ota_bp
    from app.api.records import records_bp
    from app.api.stats import stats_bp
    from app.api.settings import settings_bp
    from app.api.serial import serial_bp
    from app.api.ai_routes import ai_bp
    from app.api.auth import auth_bp
    from app.api.tasks import tasks_bp
    from app.api.ota_envs import ota_envs_bp

    app.register_blueprint(devices_bp)
    app.register_blueprint(ota_bp)
    app.register_blueprint(records_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(serial_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(ota_envs_bp)

    # 注册页面路由
    @app.route('/')
    def index():
        return render_template('devices.html')

    @app.route('/devices')
    def devices_page():
        return render_template('devices.html')

    @app.route('/monitor')
    def monitor_page():
        return render_template('monitor.html')

    @app.route('/records')
    def records_page():
        return render_template('records.html')

    @app.route('/stats')
    def stats_page():
        return render_template('stats.html')

    @app.route('/settings')
    def settings_page():
        return render_template('settings.html')

    @app.route('/tasks')
    def tasks_page():
        return render_template('tasks.html')

    return app
