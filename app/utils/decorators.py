from functools import wraps
from flask import session, jsonify


def login_required(f):
    """登录验证装饰器：未登录返回401"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '未登录', 'code': 401}), 401
        return f(*args, **kwargs)
    return decorated_function


def get_current_user_id():
    """获取当前登录用户ID"""
    return session.get('user_id')


def get_current_user():
    """获取当前登录用户对象"""
    from app.models.models import User
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None
