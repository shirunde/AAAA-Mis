"""认证模块路由：登录/注册/个人信息"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import query, execute, insert
from app.auth.forms import LoginForm, RegisterForm
from app import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm(request.form)
    if request.method == 'POST' and form.validate():
        user = query(
            'SELECT * FROM users WHERE username = %s AND is_active = 1',
            (form.username.data,), one=True
        )
        if user and check_password_hash(user['password_hash'], form.password.data):
            login_user(User(user), remember=True)
            execute(
                'UPDATE users SET last_login = NOW() WHERE id = %s',
                (user['id'],)
            )
            flash('登录成功！', 'success')
            role = user['role']
            return redirect(url_for(f'{role}.dashboard'))
        else:
            flash('用户名或密码错误', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        # Check if username exists
        existing = query(
            'SELECT id FROM users WHERE username = %s',
            (form.username.data,), one=True
        )
        if existing:
            flash('用户名已存在', 'danger')
            return render_template('auth/register.html', form=form)

        try:
            # Create user
            user_id = insert(
                """INSERT INTO users (username, password_hash, role)
                   VALUES (%s, %s, %s)""",
                (form.username.data,
                 generate_password_hash(form.password.data),
                 form.role.data)
            )

            role_name = form.role.data
            if role_name == 'student':
                # Generate student_no
                import random
                student_no = f"2023{random.randint(100000, 999999)}"
                insert(
                    """INSERT INTO students (user_id, student_no, name, gender, major_id, class_id, enrollment_year, phone, email)
                       VALUES (%s, %s, %s, %s, 1, 1, 2023, %s, %s)""",
                    (user_id, student_no, form.name.data, form.gender.data,
                     form.phone.data, form.email.data)
                )
            else:
                import random
                teacher_no = f"T{random.randint(10000, 99999)}"
                insert(
                    """INSERT INTO teachers (user_id, teacher_no, name, gender, phone, email)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (user_id, teacher_no, form.name.data, form.gender.data,
                     form.phone.data, form.email.data)
                )

            flash('注册成功，请登录', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'注册失败：{str(e)}', 'danger')

    return render_template('auth/register.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user
    role = user.get('role')
    profile_data = None

    if role == 'student':
        profile_data = query(
            """SELECT s.*, m.name AS major_name, c.name AS class_name
               FROM students s
               LEFT JOIN majors m ON s.major_id = m.id
               LEFT JOIN classes c ON s.class_id = c.id
               WHERE s.user_id = %s""",
            (user['id'],), one=True
        )
    elif role == 'teacher':
        profile_data = query(
            'SELECT * FROM teachers WHERE user_id = %s',
            (user['id'],), one=True
        )

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        if new_password:
            if len(new_password) < 6:
                flash('密码长度至少6位', 'danger')
            else:
                execute(
                    'UPDATE users SET password_hash = %s WHERE id = %s',
                    (generate_password_hash(new_password), user['id'])
                )
                flash('密码修改成功', 'success')

        # Update phone/email
        phone = request.form.get('phone', '')
        email = request.form.get('email', '')
        table = 'students' if role == 'student' else 'teachers'
        execute(
            f'UPDATE {table} SET phone = %s, email = %s WHERE user_id = %s',
            (phone, email, user['id'])
        )
        flash('个人信息更新成功', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', profile=profile_data)
