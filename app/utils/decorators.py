from functools import wraps
from flask import jsonify


def login_required(f):
    """登录验证装饰器（已移除登录校验，直接放行）"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


def get_default_user_id():
    """获取默认用户（admin）的ID，兜底返回1"""
    try:
        from app.models.models import User
        user = User.query.filter_by(username='admin').first()
        if user:
            return user.id
    except Exception:
        pass
    return 1


def get_current_user_id():
    """获取当前用户ID（全局单用户模式，固定返回默认用户ID）"""
    return get_default_user_id()


def get_current_user():
    """获取当前用户对象（全局单用户模式，固定返回默认用户）"""
    try:
        from app.models.models import User
        user = User.query.filter_by(username='admin').first()
        if user:
            return user
        return User.query.get(1)
    except Exception:
        return None
