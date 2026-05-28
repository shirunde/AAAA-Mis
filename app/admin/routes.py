"""管理员模块路由"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.decorators import role_required
from app.db import query, execute, insert, paginate, call_proc

admin_bp = Blueprint('admin', __name__)


@admin_bp.before_request
@login_required
@role_required('admin')
def check_admin():
    pass


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
    return redirect(url_for('admin.semesters'))


@admin_bp.route('/semesters/<int:sid>/edit', methods=['POST'])
def semesters_edit(sid):
    is_current = 1 if request.form.get('is_current') else 0
    if is_current:
        execute('UPDATE semesters SET is_current=0')
    execute('UPDATE semesters SET name=%s,start_date=%s,end_date=%s,is_current=%s WHERE id=%s',
            (request.form['name'], request.form['start_date'], request.form['end_date'], is_current, sid))
    flash('学期更新成功', 'success')
    return redirect(url_for('admin.semesters'))


@admin_bp.route('/semesters/<int:sid>/delete', methods=['POST'])
def semesters_delete(sid):
    execute('DELETE FROM semesters WHERE id=%s', (sid,))
    flash('学期已删除', 'info')
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
    return redirect(url_for('admin.majors'))


@admin_bp.route('/majors/<int:mid>/edit', methods=['POST'])
def majors_edit(mid):
    execute('UPDATE majors SET name=%s,code=%s,description=%s WHERE id=%s',
            (request.form['name'], request.form['code'], request.form.get('description', ''), mid))
    flash('专业更新成功', 'success')
    return redirect(url_for('admin.majors'))


@admin_bp.route('/majors/<int:mid>/delete', methods=['POST'])
def majors_delete(mid):
    execute('DELETE FROM majors WHERE id=%s', (mid,))
    flash('专业已删除', 'info')
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
    return redirect(url_for('admin.classes'))


@admin_bp.route('/classes/<int:cid>/edit', methods=['POST'])
def classes_edit(cid):
    execute('UPDATE classes SET name=%s,major_id=%s,grade=%s WHERE id=%s',
            (request.form['name'], request.form['major_id'], request.form['grade'], cid))
    flash('班级更新成功', 'success')
    return redirect(url_for('admin.classes'))


@admin_bp.route('/classes/<int:cid>/delete', methods=['POST'])
def classes_delete(cid):
    execute('DELETE FROM classes WHERE id=%s', (cid,))
    flash('班级已删除', 'info')
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
    return redirect(url_for('admin.courses_manage'))


@admin_bp.route('/courses/<int:cid>/edit', methods=['POST'])
def courses_edit(cid):
    execute("""UPDATE courses SET code=%s,name=%s,credit=%s,hours=%s,course_type=%s,description=%s
               WHERE id=%s""",
            (request.form['code'], request.form['name'], request.form['credit'],
             request.form['hours'], request.form['course_type'], request.form.get('description', ''), cid))
    flash('课程更新成功', 'success')
    return redirect(url_for('admin.courses_manage'))


@admin_bp.route('/courses/<int:cid>/delete', methods=['POST'])
def courses_delete(cid):
    execute('DELETE FROM courses WHERE id=%s', (cid,))
    flash('课程已删除', 'info')
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
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/<int:sid>/edit', methods=['POST'])
def students_edit(sid):
    execute('UPDATE students SET major_id=%s, class_id=%s, phone=%s, email=%s, status=%s WHERE id=%s',
            (request.form['major_id'], request.form['class_id'],
             request.form.get('phone', ''), request.form.get('email', ''),
             request.form.get('status', 'active'), sid))
    flash('学生信息更新成功', 'success')
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
    return redirect(url_for('admin.teachers'))


@admin_bp.route('/teachers/<int:tid>/edit', methods=['POST'])
def teachers_edit(tid):
    execute('UPDATE teachers SET title=%s, phone=%s, email=%s WHERE id=%s',
            (request.form.get('title', ''), request.form.get('phone', ''),
             request.form.get('email', ''), tid))
    flash('教师信息更新成功', 'success')
    return redirect(url_for('admin.teachers'))


# ---- 开课审核 (分页) ----
@admin_bp.route('/offerings')
def offerings():
    page = request.args.get('page', 1, type=int)
    sql = """SELECT co.*, c.name AS course_name, c.code AS course_code,
                    t.name AS teacher_name, sem.name AS semester_name
             FROM course_offerings co
             JOIN courses c ON co.course_id=c.id
             JOIN teachers t ON co.teacher_id=t.id
             JOIN semesters sem ON co.semester_id=sem.id
             ORDER BY co.status ASC, co.created_at DESC"""
    data = paginate(sql, page=page)
    return render_template('admin/offerings.html', **data)


@admin_bp.route('/offerings/<int:oid>/review', methods=['POST'])
def offerings_review(oid):
    action = request.form['action']
    comment = request.form.get('comment', '')
    if action not in ('approved', 'rejected'):
        flash('无效的审核操作', 'danger')
        return redirect(url_for('admin.offerings'))

    try:
        out = call_proc('sp_approve_course_offering',
                        (oid, current_user['id'], action, comment, 0, ''), [4, 5])
        if out['p4'] == 0:
            flash(f'开课申请已{("通过" if action == "approved" else "驳回")}', 'success')
        else:
            flash(out['p5'], 'warning')
    except Exception as e:
        flash(f'审核失败：{str(e)}', 'danger')
    return redirect(url_for('admin.offerings'))


@admin_bp.route('/offerings/<int:oid>/publish', methods=['POST'])
def offerings_publish(oid):
    execute("UPDATE course_offerings SET status='published' WHERE id=%s AND status='approved'", (oid,))
    flash('课程已发布', 'success')
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
    return redirect(url_for('admin.selection_periods'))


@admin_bp.route('/selection-periods/<int:pid>/toggle', methods=['POST'])
def selection_periods_toggle(pid):
    p = query('SELECT is_active FROM course_selection_periods WHERE id=%s', (pid,), one=True)
    execute('UPDATE course_selection_periods SET is_active=%s WHERE id=%s', (0 if p['is_active'] else 1, pid))
    flash('时间段状态已切换', 'success')
    return redirect(url_for('admin.selection_periods'))


@admin_bp.route('/selection-periods/<int:pid>/delete', methods=['POST'])
def selection_periods_delete(pid):
    execute('DELETE FROM course_selection_periods WHERE id=%s', (pid,))
    flash('选课时间段已删除', 'info')
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
    execute("UPDATE grades SET status='approved',approved_at=NOW() WHERE id=%s AND status='submitted'", (gid,))
    flash('成绩已审核通过', 'success')
    return redirect(url_for('admin.grades_review'))


@admin_bp.route('/grades/<int:gid>/publish', methods=['POST'])
def grades_publish(gid):
    execute("UPDATE grades SET status='published',published_at=NOW() WHERE id=%s AND status='approved'", (gid,))
    flash('成绩已发布', 'success')
    return redirect(url_for('admin.grades_review'))


@admin_bp.route('/grades/batch-publish', methods=['POST'])
def grades_batch_publish():
    execute("UPDATE grades SET status='published',published_at=NOW() WHERE status='approved'")
    flash('已批量发布所有审核通过的成绩', 'success')
    return redirect(url_for('admin.grades_review'))


# ---- 系统日志查看器 ----
@admin_bp.route('/logs')
def logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '').strip()

    where = ''
    args = []
    if action_filter:
        where = ' WHERE sl.action LIKE %s'
        args = [f'%{action_filter}%']

    sql = f"""SELECT sl.*, u.username FROM system_logs sl
              LEFT JOIN users u ON sl.user_id=u.id{where} ORDER BY sl.id DESC"""
    data = paginate(sql, tuple(args), page=page)
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
