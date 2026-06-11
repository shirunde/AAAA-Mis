"""管理员模块路由"""
import random

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app.decorators import role_required
from app.db import query, execute, insert, paginate, call_proc, get_conn, call_proc_rows
from app.helpers import log_action, get_offering_schedule, notify_teacher, notify_user

admin_bp = Blueprint('admin', __name__)


@admin_bp.before_request
@login_required
@role_required('admin')
def check_admin():
    pass


def _fetch_academic_alerts(semester_id=None, student_id=None):
    """调用 sp_list_academic_alerts 获取预警学生列表"""
    try:
        return call_proc_rows('sp_list_academic_alerts', (semester_id, student_id))
    except Exception:
        return []


def _count_academic_alerts(semester_id=None):
    alerts = _fetch_academic_alerts(semester_id)
    return len(alerts)


def _alert_summary(alerts):
    summary = {'high': 0, 'medium': 0, 'low': 0}
    for row in alerts:
        level = row.get('risk_level')
        if level in summary:
            summary[level] += 1
    return summary


@admin_bp.route('/')
def dashboard():
    stats = {
        'student_count': query('SELECT COUNT(*) AS c FROM students', one=True)['c'],
        'teacher_count': query('SELECT COUNT(*) AS c FROM teachers', one=True)['c'],
        'course_count': query('SELECT COUNT(*) AS c FROM courses', one=True)['c'],
        'offering_count': query("SELECT COUNT(*) AS c FROM course_offerings WHERE status!='rejected'", one=True)['c'],
        'pending_count': query("SELECT COUNT(*) AS c FROM course_offerings WHERE status='pending'", one=True)['c'],
        'enrollment_count': query("SELECT COUNT(*) AS c FROM enrollments WHERE status='enrolled'", one=True)['c'],
        'published_grade_count': query("SELECT COUNT(*) AS c FROM grades WHERE status='published'", one=True)['c'],
        'academic_alert_count': _count_academic_alerts(),
    }
    recent_logs = query(
        "SELECT sl.*, u.username FROM system_logs sl LEFT JOIN users u ON sl.user_id=u.id ORDER BY sl.id DESC LIMIT 10"
    )
    return render_template('admin/dashboard.html', stats=stats, logs=recent_logs)


# ---- 学期管理 ----
@admin_bp.route('/semesters')
def semesters():
    data = query('SELECT * FROM semesters ORDER BY id DESC')
    return render_template('admin/semesters.html', semesters=data)


@admin_bp.route('/semesters/add', methods=['POST'])
def semesters_add():
    name = request.form['name']
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    is_current = 1 if request.form.get('is_current') else 0
    if is_current:
        execute('UPDATE semesters SET is_current=0')
    execute('INSERT INTO semesters (name,start_date,end_date,is_current) VALUES (%s,%s,%s,%s)',
            (name, start_date, end_date, is_current))
    flash('学期添加成功', 'success')
    log_action('semester_add', 'semester', None, f'添加学期: {name}')
    return redirect(url_for('admin.semesters'))


@admin_bp.route('/semesters/<int:sid>/edit', methods=['POST'])
def semesters_edit(sid):
    is_current = 1 if request.form.get('is_current') else 0
    if is_current:
        execute('UPDATE semesters SET is_current=0')
    execute('UPDATE semesters SET name=%s,start_date=%s,end_date=%s,is_current=%s WHERE id=%s',
            (request.form['name'], request.form['start_date'], request.form['end_date'], is_current, sid))
    flash('学期更新成功', 'success')
    log_action('semester_edit', 'semester', sid, f'更新学期: {request.form["name"]}')
    return redirect(url_for('admin.semesters'))


@admin_bp.route('/semesters/<int:sid>/delete', methods=['POST'])
def semesters_delete(sid):
    execute('DELETE FROM semesters WHERE id=%s', (sid,))
    flash('学期已删除', 'info')
    log_action('semester_delete', 'semester', sid, f'删除学期ID={sid}')
    return redirect(url_for('admin.semesters'))


# ---- 专业管理 ----
@admin_bp.route('/majors')
def majors():
    data = query('SELECT * FROM majors ORDER BY id')
    return render_template('admin/majors.html', majors=data)


@admin_bp.route('/majors/add', methods=['POST'])
def majors_add():
    execute('INSERT INTO majors (name,code,description) VALUES (%s,%s,%s)',
            (request.form['name'], request.form['code'], request.form.get('description', '')))
    flash('专业添加成功', 'success')
    log_action('major_add', 'major', None, f'添加专业: {request.form["name"]}')
    return redirect(url_for('admin.majors'))


@admin_bp.route('/majors/<int:mid>/edit', methods=['POST'])
def majors_edit(mid):
    execute('UPDATE majors SET name=%s,code=%s,description=%s WHERE id=%s',
            (request.form['name'], request.form['code'], request.form.get('description', ''), mid))
    flash('专业更新成功', 'success')
    log_action('major_edit', 'major', mid, f'更新专业: {request.form["name"]}')
    return redirect(url_for('admin.majors'))


@admin_bp.route('/majors/<int:mid>/delete', methods=['POST'])
def majors_delete(mid):
    execute('DELETE FROM majors WHERE id=%s', (mid,))
    flash('专业已删除', 'info')
    log_action('major_delete', 'major', mid, f'删除专业ID={mid}')
    return redirect(url_for('admin.majors'))


# ---- 班级管理 ----
@admin_bp.route('/classes')
def classes():
    data = query("""SELECT c.*, m.name AS major_name FROM classes c
                    LEFT JOIN majors m ON c.major_id=m.id ORDER BY c.id""")
    majors = query('SELECT * FROM majors ORDER BY id')
    return render_template('admin/classes.html', classes=data, majors=majors)


@admin_bp.route('/classes/add', methods=['POST'])
def classes_add():
    execute('INSERT INTO classes (name,major_id,grade) VALUES (%s,%s,%s)',
            (request.form['name'], request.form['major_id'], request.form['grade']))
    flash('班级添加成功', 'success')
    log_action('class_add', 'class', None, f'添加班级: {request.form["name"]}')
    return redirect(url_for('admin.classes'))


@admin_bp.route('/classes/<int:cid>/edit', methods=['POST'])
def classes_edit(cid):
    execute('UPDATE classes SET name=%s,major_id=%s,grade=%s WHERE id=%s',
            (request.form['name'], request.form['major_id'], request.form['grade'], cid))
    flash('班级更新成功', 'success')
    log_action('class_edit', 'class', cid, f'更新班级: {request.form["name"]}')
    return redirect(url_for('admin.classes'))


@admin_bp.route('/classes/<int:cid>/delete', methods=['POST'])
def classes_delete(cid):
    execute('DELETE FROM classes WHERE id=%s', (cid,))
    flash('班级已删除', 'info')
    log_action('class_delete', 'class', cid, f'删除班级ID={cid}')
    return redirect(url_for('admin.classes'))


# ---- 课程管理 ----
@admin_bp.route('/courses')
def courses_manage():
    data = query('SELECT * FROM courses ORDER BY id')
    return render_template('admin/courses.html', courses=data)


@admin_bp.route('/courses/add', methods=['POST'])
def courses_add():
    execute("""INSERT INTO courses (code,name,credit,hours,course_type,description)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (request.form['code'], request.form['name'], request.form['credit'],
             request.form['hours'], request.form['course_type'], request.form.get('description', '')))
    flash('课程添加成功', 'success')
    log_action('course_add', 'course', None, f'添加课程: {request.form["name"]}')
    return redirect(url_for('admin.courses_manage'))


@admin_bp.route('/courses/<int:cid>/edit', methods=['POST'])
def courses_edit(cid):
    execute("""UPDATE courses SET code=%s,name=%s,credit=%s,hours=%s,course_type=%s,description=%s
               WHERE id=%s""",
            (request.form['code'], request.form['name'], request.form['credit'],
             request.form['hours'], request.form['course_type'], request.form.get('description', ''), cid))
    flash('课程更新成功', 'success')
    log_action('course_edit', 'course', cid, f'更新课程: {request.form["name"]}')
    return redirect(url_for('admin.courses_manage'))


@admin_bp.route('/courses/<int:cid>/delete', methods=['POST'])
def courses_delete(cid):
    execute('DELETE FROM courses WHERE id=%s', (cid,))
    flash('课程已删除', 'info')
    log_action('course_delete', 'course', cid, f'删除课程ID={cid}')
    return redirect(url_for('admin.courses_manage'))


# ---- 学生管理 (分页+搜索+编辑) ----
_STUDENT_SQL = """SELECT s.*, u.username, u.is_active, m.name AS major_name, cl.name AS class_name
    FROM students s JOIN users u ON s.user_id=u.id
    LEFT JOIN majors m ON s.major_id=m.id
    LEFT JOIN classes cl ON s.class_id=cl.id"""


@admin_bp.route('/students')
def students():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    where = ''
    args = []
    if search:
        where = ' WHERE s.name LIKE %s OR s.student_no LIKE %s OR u.username LIKE %s'
        args = [f'%{search}%', f'%{search}%', f'%{search}%']

    data = paginate(_STUDENT_SQL + where + ' ORDER BY s.id', tuple(args), page=page)
    majors = query('SELECT * FROM majors ORDER BY id')
    classes = query('SELECT * FROM classes ORDER BY id')
    return render_template('admin/students.html', **data, search=search, majors=majors, all_classes=classes)


@admin_bp.route('/students/<int:sid>/toggle', methods=['POST'])
def students_toggle(sid):
    s = query('SELECT user_id FROM students WHERE id=%s', (sid,), one=True)
    if s:
        u = query('SELECT is_active FROM users WHERE id=%s', (s['user_id'],), one=True)
        execute('UPDATE users SET is_active=%s WHERE id=%s', (0 if u['is_active'] else 1, s['user_id']))
        flash('用户状态已切换', 'success')
        log_action('student_toggle', 'student', sid, '切换学生账号状态')
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/<int:sid>/edit', methods=['POST'])
def students_edit(sid):
    execute('UPDATE students SET major_id=%s, class_id=%s, phone=%s, email=%s, status=%s WHERE id=%s',
            (request.form['major_id'], request.form['class_id'],
             request.form.get('phone', ''), request.form.get('email', ''),
             request.form.get('status', 'active'), sid))
    flash('学生信息更新成功', 'success')
    log_action('student_edit', 'student', sid, f'更新学生ID={sid}')
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/add', methods=['POST'])
def students_add():
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM users WHERE username=%s', (request.form['username'],))
            if cur.fetchone():
                flash('用户名已存在', 'danger')
                return redirect(url_for('admin.students'))

            password_hash = generate_password_hash(request.form['password'])
            cur.execute('INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)',
                        (request.form['username'], password_hash, 'student'))
            user_id = cur.lastrowid

            student_no = f"{request.form.get('enrollment_year', 2023)}{random.randint(100000, 999999)}"
            cur.execute("""INSERT INTO students (user_id, student_no, name, gender, major_id, class_id,
                           enrollment_year, phone, email)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (user_id, student_no, request.form['name'], request.form['gender'],
                         request.form['major_id'], request.form['class_id'],
                         request.form.get('enrollment_year', 2023),
                         request.form.get('phone', ''), request.form.get('email', '')))
            conn.commit()
        flash('学生添加成功', 'success')
        log_action('student_add', 'student', None, f'添加学生: {request.form["name"]}')
    except Exception as e:
        flash(f'添加失败：{str(e)}', 'danger')
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/<int:sid>/reset-password', methods=['POST'])
def students_reset_password(sid):
    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('密码至少6位', 'danger')
        return redirect(url_for('admin.students'))
    s = query('SELECT user_id FROM students WHERE id=%s', (sid,), one=True)
    if s:
        execute('UPDATE users SET password_hash=%s WHERE id=%s',
                (generate_password_hash(new_password), s['user_id']))
        flash('密码已重置', 'success')
        log_action('student_reset_password', 'student', sid, '重置学生密码')
    else:
        flash('学生不存在', 'danger')
    return redirect(url_for('admin.students'))


# ---- 教师管理 (分页+搜索) ----
@admin_bp.route('/teachers')
def teachers():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    base = """SELECT t.*, u.username, u.is_active FROM teachers t JOIN users u ON t.user_id=u.id"""
    where = ''
    args = []
    if search:
        where = ' WHERE t.name LIKE %s OR t.teacher_no LIKE %s OR u.username LIKE %s'
        args = [f'%{search}%', f'%{search}%', f'%{search}%']

    data = paginate(base + where + ' ORDER BY t.id', tuple(args), page=page)
    return render_template('admin/teachers.html', **data, search=search)


@admin_bp.route('/teachers/<int:tid>/toggle', methods=['POST'])
def teachers_toggle(tid):
    t = query('SELECT user_id FROM teachers WHERE id=%s', (tid,), one=True)
    if t:
        u = query('SELECT is_active FROM users WHERE id=%s', (t['user_id'],), one=True)
        execute('UPDATE users SET is_active=%s WHERE id=%s', (0 if u['is_active'] else 1, t['user_id']))
        flash('用户状态已切换', 'success')
        log_action('teacher_toggle', 'teacher', tid, '切换教师账号状态')
    return redirect(url_for('admin.teachers'))


@admin_bp.route('/teachers/<int:tid>/edit', methods=['POST'])
def teachers_edit(tid):
    execute('UPDATE teachers SET title=%s, phone=%s, email=%s WHERE id=%s',
            (request.form.get('title', ''), request.form.get('phone', ''),
             request.form.get('email', ''), tid))
    flash('教师信息更新成功', 'success')
    log_action('teacher_edit', 'teacher', tid, f'更新教师ID={tid}')
    return redirect(url_for('admin.teachers'))


@admin_bp.route('/teachers/add', methods=['POST'])
def teachers_add():
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM users WHERE username=%s', (request.form['username'],))
            if cur.fetchone():
                flash('用户名已存在', 'danger')
                return redirect(url_for('admin.teachers'))

            password_hash = generate_password_hash(request.form['password'])
            cur.execute('INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)',
                        (request.form['username'], password_hash, 'teacher'))
            user_id = cur.lastrowid

            teacher_no = f"T{random.randint(10000, 99999)}"
            cur.execute("""INSERT INTO teachers (user_id, teacher_no, name, gender, title, phone, email)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (user_id, teacher_no, request.form['name'], request.form['gender'],
                         request.form.get('title', ''), request.form.get('phone', ''),
                         request.form.get('email', '')))
            conn.commit()
        flash('教师添加成功', 'success')
        log_action('teacher_add', 'teacher', None, f'添加教师: {request.form["name"]}')
    except Exception as e:
        flash(f'添加失败：{str(e)}', 'danger')
    return redirect(url_for('admin.teachers'))


@admin_bp.route('/teachers/<int:tid>/reset-password', methods=['POST'])
def teachers_reset_password(tid):
    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('密码至少6位', 'danger')
        return redirect(url_for('admin.teachers'))
    t = query('SELECT user_id FROM teachers WHERE id=%s', (tid,), one=True)
    if t:
        execute('UPDATE users SET password_hash=%s WHERE id=%s',
                (generate_password_hash(new_password), t['user_id']))
        flash('密码已重置', 'success')
        log_action('teacher_reset_password', 'teacher', tid, '重置教师密码')
    else:
        flash('教师不存在', 'danger')
    return redirect(url_for('admin.teachers'))


# ---- 开课审核 (分页) ----
@admin_bp.route('/offerings')
def offerings():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()

    where = ''
    args = []
    if status_filter in ('pending', 'approved', 'rejected', 'published', 'cancelled'):
        where += ' AND co.status=%s'
        args.append(status_filter)
    if search:
        where += ' AND (c.name LIKE %s OR c.code LIKE %s OR t.name LIKE %s)'
        args.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

    sql = f"""SELECT co.*, c.name AS course_name, c.code AS course_code,
                    t.name AS teacher_name, sem.name AS semester_name
             FROM course_offerings co
             JOIN courses c ON co.course_id=c.id
             JOIN teachers t ON co.teacher_id=t.id
             JOIN semesters sem ON co.semester_id=sem.id
             WHERE 1=1{where}
             ORDER BY co.status ASC, co.created_at DESC"""
    data = paginate(sql, tuple(args), page=page)
    for o in data.get('items', []):
        o['schedule_display'] = get_offering_schedule(o['id'])
        o['enrolled_count'] = query(
            "SELECT COUNT(*) AS c FROM enrollments WHERE course_offering_id=%s AND status='enrolled'",
            (o['id'],), one=True
        )['c']
    return render_template('admin/offerings.html', **data, status_filter=status_filter, search=search)


@admin_bp.route('/offerings/<int:oid>/review', methods=['POST'])
def offerings_review(oid):
    action = request.form['action']
    comment = request.form.get('comment', '').strip()
    if action not in ('approved', 'rejected'):
        flash('无效的审核操作', 'danger')
        return redirect(url_for('admin.offerings'))
    if action == 'rejected' and not comment:
        flash('驳回时必须填写审核意见', 'danger')
        return redirect(url_for('admin.offerings'))

    offering = query(
        """SELECT co.*, c.name AS course_name, t.id AS teacher_id
           FROM course_offerings co JOIN courses c ON co.course_id=c.id
           JOIN teachers t ON co.teacher_id=t.id WHERE co.id=%s""",
        (oid,), one=True
    )

    try:
        out = call_proc('sp_approve_course_offering',
                        (oid, current_user['id'], action, comment, 0, ''), [4, 5])
        if out['p4'] == 0:
            label = '通过' if action == 'approved' else '驳回'
            flash(f'开课申请已{label}', 'success')
            if offering:
                notify_teacher(
                    offering['teacher_id'],
                    f'开课申请已{label}',
                    f'您的「{offering["course_name"]}」开课申请已{label}。'
                    + (f'审核意见：{comment}' if comment else ''),
                    'success' if action == 'approved' else 'warning',
                    'offering', oid
                )
            log_action('offering_review', 'offering', oid, f'{label}: {comment}')
        else:
            flash(out['p5'], 'warning')
    except Exception as e:
        flash(f'审核失败：{str(e)}', 'danger')
    return redirect(url_for('admin.offerings'))


@admin_bp.route('/offerings/<int:oid>/publish', methods=['POST'])
def offerings_publish(oid):
    offering = query(
        """SELECT co.*, c.name AS course_name, t.id AS teacher_id
           FROM course_offerings co JOIN courses c ON co.course_id=c.id
           JOIN teachers t ON co.teacher_id=t.id WHERE co.id=%s""",
        (oid,), one=True
    )
    try:
        out = call_proc('sp_publish_course_offering', (oid, current_user['id'], 0, ''), [2, 3])
        if out['p2'] == 0:
            flash(out['p3'], 'success')
            if offering:
                notify_teacher(
                    offering['teacher_id'], '课程已发布',
                    f'您的「{offering["course_name"]}」已通过审核并发布，学生现可选课。',
                    'success', 'offering', oid
                )
            log_action('offering_publish', 'offering', oid, f'发布开课ID={oid}')
        else:
            flash(out['p3'], 'warning')
    except Exception as e:
        flash(f'发布失败：{str(e)}', 'danger')
    return redirect(url_for('admin.offerings'))


@admin_bp.route('/offerings/<int:oid>/unpublish', methods=['POST'])
def offerings_unpublish(oid):
    reason = request.form.get('reason', '').strip()
    offering = query(
        """SELECT co.*, c.name AS course_name, t.id AS teacher_id
           FROM course_offerings co JOIN courses c ON co.course_id=c.id
           JOIN teachers t ON co.teacher_id=t.id WHERE co.id=%s""",
        (oid,), one=True
    )
    try:
        out = call_proc('sp_unpublish_course_offering',
                        (oid, current_user['id'], reason, 0, ''), [3, 4])
        if out['p3'] == 0:
            flash(out['p4'], 'success')
            if offering:
                notify_teacher(
                    offering['teacher_id'], '课程发布已撤销',
                    f'「{offering["course_name"]}」已撤销发布。' + (f'原因：{reason}' if reason else ''),
                    'warning', 'offering', oid
                )
            log_action('offering_unpublish', 'offering', oid, reason or '撤销发布')
        else:
            flash(out['p4'], 'warning')
    except Exception as e:
        flash(f'撤销发布失败：{str(e)}', 'danger')
    return redirect(url_for('admin.offerings'))


@admin_bp.route('/offerings/<int:oid>/cancel', methods=['POST'])
def offerings_cancel(oid):
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('停开课程必须填写原因', 'danger')
        return redirect(url_for('admin.offerings'))

    offering = query(
        """SELECT co.*, c.name AS course_name, t.id AS teacher_id
           FROM course_offerings co JOIN courses c ON co.course_id=c.id
           JOIN teachers t ON co.teacher_id=t.id WHERE co.id=%s""",
        (oid,), one=True
    )
    try:
        out = call_proc('sp_cancel_course_offering',
                        (oid, current_user['id'], reason, 0, ''), [3, 4])
        if out['p3'] == 0:
            flash(out['p4'], 'success')
            if offering:
                notify_teacher(
                    offering['teacher_id'], '课程已停开',
                    f'「{offering["course_name"]}」已停开。原因：{reason}',
                    'danger', 'offering', oid
                )
                students = query(
                    """SELECT s.user_id FROM enrollments e
                       JOIN students s ON e.student_id=s.id
                       WHERE e.course_offering_id=%s AND e.status='dropped'""",
                    (oid,)
                )
                for s in students:
                    notify_user(
                        s['user_id'], '课程停开通知',
                        f'您选修的「{offering["course_name"]}」已停开，系统已自动退课。原因：{reason}',
                        'warning', 'offering', oid
                    )
            log_action('offering_cancel', 'offering', oid, reason)
        else:
            flash(out['p4'], 'warning')
    except Exception as e:
        flash(f'停开失败：{str(e)}', 'danger')
    return redirect(url_for('admin.offerings'))


# ---- 选课时间配置 ----
@admin_bp.route('/selection-periods')
def selection_periods():
    data = query("""SELECT sp.*, sem.name AS semester_name FROM course_selection_periods sp
                    JOIN semesters sem ON sp.semester_id=sem.id ORDER BY sp.id DESC""")
    semesters = query('SELECT * FROM semesters ORDER BY id DESC')
    return render_template('admin/selection_periods.html', periods=data, semesters=semesters)


@admin_bp.route('/selection-periods/add', methods=['POST'])
def selection_periods_add():
    execute("""INSERT INTO course_selection_periods (semester_id,name,start_time,end_time,period_type)
               VALUES (%s,%s,%s,%s,%s)""",
            (request.form['semester_id'], request.form['name'],
             request.form['start_time'], request.form['end_time'], request.form['period_type']))
    flash('选课时间段添加成功', 'success')
    log_action('selection_period_add', 'selection_period', None, '添加选课时间段')
    return redirect(url_for('admin.selection_periods'))


@admin_bp.route('/selection-periods/<int:pid>/edit', methods=['POST'])
def selection_periods_edit(pid):
    execute("""UPDATE course_selection_periods
               SET semester_id=%s, name=%s, start_time=%s, end_time=%s, period_type=%s
               WHERE id=%s""",
            (request.form['semester_id'], request.form['name'],
             request.form['start_time'], request.form['end_time'],
             request.form['period_type'], pid))
    flash('选课时间段更新成功', 'success')
    log_action('selection_period_edit', 'selection_period', pid, '更新选课时间段')
    return redirect(url_for('admin.selection_periods'))


@admin_bp.route('/selection-periods/<int:pid>/toggle', methods=['POST'])
def selection_periods_toggle(pid):
    p = query('SELECT is_active FROM course_selection_periods WHERE id=%s', (pid,), one=True)
    execute('UPDATE course_selection_periods SET is_active=%s WHERE id=%s', (0 if p['is_active'] else 1, pid))
    flash('时间段状态已切换', 'success')
    log_action('selection_period_toggle', 'selection_period', pid, '切换选课时间段状态')
    return redirect(url_for('admin.selection_periods'))


@admin_bp.route('/selection-periods/<int:pid>/delete', methods=['POST'])
def selection_periods_delete(pid):
    execute('DELETE FROM course_selection_periods WHERE id=%s', (pid,))
    flash('选课时间段已删除', 'info')
    log_action('selection_period_delete', 'selection_period', pid, f'删除选课时间段ID={pid}')
    return redirect(url_for('admin.selection_periods'))


# ---- 成绩审核 (分页) ----
@admin_bp.route('/grades-review')
def grades_review():
    page = request.args.get('page', 1, type=int)
    sql = """SELECT g.*, s.name AS student_name, s.student_no, c.name AS course_name,
                    t.name AS teacher_name, sem.name AS semester_name
             FROM grades g
             JOIN enrollments e ON g.enrollment_id=e.id
             JOIN students s ON e.student_id=s.id
             JOIN course_offerings co ON e.course_offering_id=co.id
             JOIN courses c ON co.course_id=c.id
             JOIN teachers t ON co.teacher_id=t.id
             JOIN semesters sem ON co.semester_id=sem.id
             WHERE g.status IN ('submitted','approved','published')
             ORDER BY g.status ASC, g.updated_at DESC"""
    data = paginate(sql, page=page)
    return render_template('admin/grades_review.html', **data)


@admin_bp.route('/grades/<int:gid>/approve', methods=['POST'])
def grades_approve(gid):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE grades SET status='approved',approved_at=NOW() WHERE id=%s AND status='submitted'", (gid,))
            if cur.rowcount == 0:
                flash('该成绩不存在或已审核', 'warning')
                return redirect(url_for('admin.grades_review'))
            conn.commit()
        log_action('grade_approved', 'grade', gid, '管理员审核通过成绩')
        flash('成绩已审核通过', 'success')
    except Exception as e:
        flash(f'审核失败：{str(e)}', 'danger')
    return redirect(url_for('admin.grades_review'))


@admin_bp.route('/grades/<int:gid>/publish', methods=['POST'])
def grades_publish(gid):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE grades SET status='published',published_at=NOW() WHERE id=%s AND status='approved'", (gid,))
            if cur.rowcount == 0:
                flash('该成绩不存在或未通过审核', 'warning')
                return redirect(url_for('admin.grades_review'))
            conn.commit()
        log_action('grade_published', 'grade', gid, '管理员发布成绩')
        flash('成绩已发布', 'success')
    except Exception as e:
        flash(f'发布失败：{str(e)}', 'danger')
    return redirect(url_for('admin.grades_review'))


@admin_bp.route('/grades/<int:gid>/reject', methods=['POST'])
def grades_reject(gid):
    reason = request.form.get('reject_reason', '').strip()
    if not reason:
        flash('请填写驳回原因', 'danger')
        return redirect(url_for('admin.grades_review'))
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE grades SET status='draft', submitted_at=NULL WHERE id=%s AND status='submitted'",
                (gid,)
            )
            if cur.rowcount == 0:
                flash('该成绩不存在或无法驳回', 'warning')
                return redirect(url_for('admin.grades_review'))
            conn.commit()
        log_action('grade_rejected', 'grade', gid, f'管理员驳回成绩，原因: {reason}')
        flash('成绩已驳回，教师可重新修改', 'success')
    except Exception as e:
        flash(f'驳回失败：{str(e)}', 'danger')
    return redirect(url_for('admin.grades_review'))


@admin_bp.route('/grades/batch-publish', methods=['POST'])
def grades_batch_publish():
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE grades SET status='published',published_at=NOW() WHERE status='approved'")
            count = cur.rowcount
            conn.commit()
        if count > 0:
            log_action('grade_batch_published', 'grade', 0, f'批量发布{count}条成绩')
        flash(f'已批量发布{count}条成绩', 'success')
    except Exception as e:
        flash(f'批量发布失败：{str(e)}', 'danger')
    return redirect(url_for('admin.grades_review'))


# ---- 系统日志查看器 ----
@admin_bp.route('/logs')
def logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '').strip()

    base_sql = """SELECT sl.*, u.username FROM system_logs sl
                  LEFT JOIN users u ON sl.user_id=u.id"""
    count_sql = "SELECT COUNT(*) AS total FROM system_logs sl"

    where = ''
    args = []
    if action_filter:
        where = ' WHERE sl.action LIKE %s'
        args = [f'%{action_filter}%']

    data = paginate(
        base_sql + where + ' ORDER BY sl.id DESC',
        tuple(args) if args else None,
        page=page,
        count_sql=count_sql + where,
        count_args=tuple(args) if args else None,
    )
    return render_template('admin/logs.html', **data, action_filter=action_filter)


# ---- 统计分析 ----
@admin_bp.route('/statistics')
def statistics():
    selection_stats = query("""SELECT course_code AS code, course_name, teacher_name,
        max_students, enrolled_count
        FROM v_course_selection_stats
        WHERE offering_status IN ('approved', 'published')
        ORDER BY enrolled_count DESC""")

    grade_dist = query("""SELECT CASE
        WHEN g.total_grade>=90 THEN '90-100(优秀)'
        WHEN g.total_grade>=80 THEN '80-89(良好)'
        WHEN g.total_grade>=70 THEN '70-79(中等)'
        WHEN g.total_grade>=60 THEN '60-69(及格)'
        ELSE '60以下(不及格)' END AS grade_range, COUNT(*) AS count
        FROM grades g WHERE g.total_grade IS NOT NULL
        GROUP BY grade_range ORDER BY grade_range DESC""")

    teacher_workload = query("""SELECT teacher_name AS name, title,
        SUM(total_offerings) AS offering_count,
        SUM(total_students) AS total_students
        FROM v_teacher_workload
        GROUP BY teacher_id, teacher_name, title
        ORDER BY offering_count DESC""")

    return render_template('admin/statistics.html',
                           selection_stats=selection_stats, grade_dist=grade_dist,
                           teacher_workload=teacher_workload)


# ---- 学业预警 ----
@admin_bp.route('/academic-alerts')
def academic_alerts():
    semester_id = request.args.get('semester_id', type=int)
    risk_filter = request.args.get('risk', '').strip()
    search = request.args.get('search', '').strip()

    semesters = query('SELECT * FROM semesters ORDER BY start_date DESC')
    if semester_id is None:
        current = query('SELECT id FROM semesters WHERE is_current=1 ORDER BY id DESC LIMIT 1', one=True)
        semester_id = current['id'] if current else None

    alerts = _fetch_academic_alerts(semester_id)

    if risk_filter in ('high', 'medium', 'low'):
        alerts = [a for a in alerts if a.get('risk_level') == risk_filter]
    if search:
        key = search.lower()
        alerts = [
            a for a in alerts
            if key in (a.get('student_no') or '').lower()
            or key in (a.get('student_name') or '').lower()
            or key in (a.get('major_name') or '').lower()
            or key in (a.get('class_name') or '').lower()
        ]

    summary = _alert_summary(alerts)

    # 手动分页
    per_page = current_app.config['PER_PAGE']
    total = len(alerts)
    pages = max(1, (total + per_page - 1) // per_page)
    page_num = request.args.get('page', 1, type=int)
    page_num = min(max(1, page_num), pages)
    start = (page_num - 1) * per_page
    end = start + per_page
    paginated_alerts = alerts[start:end]

    selected_semester = query('SELECT * FROM semesters WHERE id=%s', (semester_id,), one=True) if semester_id else None

    return render_template(
        'admin/academic_alerts.html',
        alerts=paginated_alerts,
        summary=summary,
        semesters=semesters,
        semester_id=semester_id,
        selected_semester=selected_semester,
        risk_filter=risk_filter,
        search=search,
        total=total, page=page_num, pages=pages,
    )


# ---- 教室管理 ----
@admin_bp.route('/classrooms')
def classrooms():
    data = query('SELECT * FROM classrooms ORDER BY building, room_number')
    buildings = query('SELECT DISTINCT building FROM classrooms ORDER BY building')
    return render_template('admin/classrooms.html', classrooms=data, buildings=buildings)


@admin_bp.route('/classrooms/add', methods=['POST'])
def classrooms_add():
    code = request.form['code']
    name = request.form['name']
    building = request.form['building']
    room_number = request.form['room_number']
    capacity = request.form.get('capacity', type=int)

    execute("""INSERT INTO classrooms (code, name, building, room_number, capacity)
               VALUES (%s,%s,%s,%s,%s)""",
            (code, name, building, room_number, capacity))
    flash('教室添加成功', 'success')
    log_action('classroom_add', 'classroom', None, f'添加教室: {name}')
    return redirect(url_for('admin.classrooms'))


@admin_bp.route('/classrooms/<int:cid>/edit', methods=['POST'])
def classrooms_edit(cid):
    execute("""UPDATE classrooms SET code=%s,name=%s,building=%s,room_number=%s,capacity=%s
               WHERE id=%s""",
            (request.form['code'], request.form['name'], request.form['building'],
             request.form['room_number'], request.form.get('capacity', type=int), cid))
    flash('教室更新成功', 'success')
    log_action('classroom_edit', 'classroom', cid, f'更新教室: {request.form["name"]}')
    return redirect(url_for('admin.classrooms'))


@admin_bp.route('/classrooms/<int:cid>/toggle', methods=['POST'])
def classrooms_toggle(cid):
    c = query('SELECT is_active FROM classrooms WHERE id=%s', (cid,), one=True)
    execute('UPDATE classrooms SET is_active=%s WHERE id=%s', (0 if c['is_active'] else 1, cid))
    flash('教室状态已切换', 'success')
    log_action('classroom_toggle', 'classroom', cid, '切换教室状态')
    return redirect(url_for('admin.classrooms'))


@admin_bp.route('/classrooms/<int:cid>/delete', methods=['POST'])
def classrooms_delete(cid):
    execute('DELETE FROM classrooms WHERE id=%s', (cid,))
    flash('教室已删除', 'info')
    log_action('classroom_delete', 'classroom', cid, f'删除教室ID={cid}')
    return redirect(url_for('admin.classrooms'))


# ---- 时间段管理 ----
@admin_bp.route('/time-slots')
def time_slots():
    data = query('SELECT * FROM time_slots ORDER BY day_of_week, period_num')
    day_names = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return render_template('admin/time_slots.html', slots=data, day_names=day_names)


@admin_bp.route('/time-slots/<int:sid>/edit', methods=['POST'])
def time_slots_edit(sid):
    execute("""UPDATE time_slots SET start_time=%s,end_time=%s,label=%s
               WHERE id=%s""",
            (request.form['start_time'], request.form['end_time'],
             request.form['label'], sid))
    flash('时间段更新成功', 'success')
    log_action('timeslot_edit', 'timeslot', sid, f'更新时间段ID={sid}')
    return redirect(url_for('admin.time_slots'))
