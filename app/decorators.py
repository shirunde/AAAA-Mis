"""装饰器：登录验证 & 角色验证"""
from functools import wraps
from flask import abort
from flask_login import current_user


def login_required(f):
    """要求登录"""
    from flask_login import login_required as flask_login_required
    return flask_login_required(f)


def role_required(role):
    """要求指定角色"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                return redirect(url_for('auth.login'))
            if current_user.get('role') != role:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
