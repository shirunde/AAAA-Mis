"""Flask 应用初始化 & 蓝图注册"""
from flask import Flask
from flask_login import LoginManager, UserMixin
from flask_wtf.csrf import CSRFProtect
from config import Config

csrf = CSRFProtect()


class User(UserMixin):
    """Flask-Login compatible user wrapper"""
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def get_id(self):
        return str(self._data['id'])

    @property
    def is_active(self):
        return bool(self._data.get('is_active', 1))

    def __getitem__(self, key):
        return self._data[key]


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    csrf.init_app(app)

    # Init database pool
    from app.db import init_pool, close_conn
    init_pool(app)
    app.teardown_appcontext(close_conn)

    # Init Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录后再访问该页面'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from app.db import query
        data = query('SELECT * FROM users WHERE id = %s', (user_id,), one=True)
        return User(data) if data else None

    # Register blueprints
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.teacher.routes import teacher_bp
    app.register_blueprint(teacher_bp, url_prefix='/teacher')

    from app.student.routes import student_bp
    app.register_blueprint(student_bp, url_prefix='/student')

    # Register template helper functions
    from app import helpers
    @app.template_global()
    def get_offering_schedule(offering_id):
        return helpers.get_offering_schedule(offering_id)

    # Home route
    @app.route('/')
    def index():
        from flask import redirect, url_for
        from flask_login import current_user
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        role = current_user.get('role')
        return redirect(url_for(f'{role}.dashboard'))

    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        # Temporarily show detailed error for debugging
        import traceback
        print("=" * 80)
        print("SERVER ERROR DETAILS:")
        traceback.print_exc()
        print("=" * 80)
        return render_template('500.html'), 500

    return app
