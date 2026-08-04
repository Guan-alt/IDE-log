from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import inspect

db = SQLAlchemy()

def create_app():
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

        # 数据迁移：为每个有 Setting 的用户种子 OtaEnvironment（仅当该用户无 OtaEnvironment 时执行）
        existing_users_with_setting = User.query.all()
        for u in existing_users_with_setting:
            if OtaEnvironment.query.filter_by(user_id=u.id).count() > 0:
                continue
            s = Setting.query.filter_by(user_id=u.id).first()
            if not s:
                continue
            if s.ota_url:
                env1 = OtaEnvironment(user_id=u.id, name='线下', ota_url=s.ota_url, token=s.token or '', sort_order=0)
                db.session.add(env1)
            if s.ota_url_online:
                env2 = OtaEnvironment(user_id=u.id, name='线上', ota_url=s.ota_url_online, token=s.token_online or '', sort_order=1)
                db.session.add(env2)
        db.session.commit()
        print('Migration: OtaEnvironment seeded for existing users')

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
