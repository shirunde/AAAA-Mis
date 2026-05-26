"""学生模块路由"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.decorators import role_required
from app.db import query, execute

student_bp = Blueprint('student', __name__)


@student_bp.before_request
@login_required
@role_required('student')
def check_student():
    pass


def get_student_id():
    s = query('SELECT id FROM students WHERE user_id = %s', (current_user['id'],), one=True)
    return s['id'] if s else None


@student_bp.route('/')
def dashboard():
    sid = get_student_id()
    enrolled_count = query(
        "SELECT COUNT(*) AS c FROM enrollments WHERE student_id=%s AND status='enrolled'",
        (sid,), one=True
    )['c']
    # GPA
    gpa_info = query(
        """SELECT ROUND(COALESCE(SUM(g.gpa_point * c.credit), 0) / NULLIF(SUM(c.credit), 0), 2) AS gpa,
                  SUM(c.credit) AS total_credits
           FROM grades g
           JOIN enrollments e ON g.enrollment_id = e.id
           JOIN course_offerings co ON e.course_offering_id = co.id
           JOIN courses c ON co.course_id = c.id
           WHERE e.student_id=%s AND e.status='enrolled'
             AND g.status IN ('approved','published') AND g.gpa_point IS NOT NULL""",
        (sid,), one=True
    )
    return render_template('student/dashboard.html',
                           enrolled_count=enrolled_count,
                           gpa=gpa_info['gpa'] or 0,
                           total_credits=gpa_info['total_credits'] or 0)


# ---- 课程查询 ----
@student_bp.route('/courses')
def courses():
    search = request.args.get('search', '')
    course_type = request.args.get('type', '')
    current_semester = query('SELECT id FROM semesters WHERE is_current=1', one=True)

    sql = """SELECT co.*, c.name AS course_name, c.code AS course_code, c.credit, c.hours,
                    c.course_type, c.description, t.name AS teacher_name, t.title,
                    sem.name AS semester_name,
                    (SELECT COUNT(*) FROM enrollments e WHERE e.course_offering_id=co.id AND e.status='enrolled') AS enrolled_count
             FROM course_offerings co
             JOIN courses c ON co.course_id = c.id
             JOIN teachers t ON co.teacher_id = t.id
             JOIN semesters sem ON co.semester_id = sem.id
             WHERE co.status = 'published'"""
    args = []

    if current_semester:
        sql += ' AND co.semester_id = %s'
        args.append(current_semester['id'])

    if search:
        sql += ' AND (c.name LIKE %s OR c.code LIKE %s OR t.name LIKE %s)'
        args.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if course_type:
        sql += ' AND c.course_type = %s'
        args.append(course_type)

    sql += ' ORDER BY co.id DESC'

    data = query(sql, tuple(args))
    return render_template('student/courses.html', offerings=data, search=search, type=course_type)


# ---- 选课 ----
@student_bp.route('/enroll/<int:oid>', methods=['POST'])
def enroll(oid):
    sid = get_student_id()

    # 检查是否在选课窗口
    offering = query(
        """SELECT co.semester_id FROM course_offerings co WHERE co.id=%s AND co.status='published'""",
        (oid,), one=True
    )
    if not offering:
        flash('该课程不可选', 'danger')
        return redirect(url_for('student.courses'))

    in_period = query(
        """SELECT COUNT(*) AS c FROM course_selection_periods
           WHERE semester_id=%s AND period_type='selection' AND is_active=1
             AND NOW() BETWEEN start_time AND end_time""",
        (offering['semester_id'],), one=True
    )
    if in_period['c'] == 0:
        flash('当前不在选课窗口期内', 'warning')
        return redirect(url_for('student.courses'))

    # 检查已选
    already = query(
        "SELECT id FROM enrollments WHERE student_id=%s AND course_offering_id=%s AND status='enrolled'",
        (sid, oid), one=True
    )
    if already:
        flash('已选过该课程', 'warning')
        return redirect(url_for('student.courses'))

    # 检查时间冲突
    conflict = query(
        """SELECT c.name FROM enrollments e
           JOIN course_offerings co ON e.course_offering_id = co.id
           JOIN course_offerings co2 ON co2.id = %s
           JOIN courses c ON co.course_id = c.id
           WHERE e.student_id=%s AND e.status='enrolled'
             AND co.semester_id = co2.semester_id
             AND co.schedule = co2.schedule
             AND co2.schedule IS NOT NULL AND co2.schedule != ''""",
        (oid, sid)
    )
    if conflict:
        flash(f'上课时间冲突：已选课程 {conflict[0]["name"]}', 'danger')
        return redirect(url_for('student.courses'))

    # 检查容量
    count = query(
        "SELECT COUNT(*) AS c FROM enrollments WHERE course_offering_id=%s AND status='enrolled'",
        (oid,), one=True
    )
    max_s = query('SELECT max_students FROM course_offerings WHERE id=%s', (oid,), one=True)
    if count['c'] >= max_s['max_students']:
        flash('该课程选课人数已满', 'warning')
        return redirect(url_for('student.courses'))

    # 执行选课
    try:
        execute(
            'INSERT INTO enrollments (student_id, course_offering_id, status) VALUES (%s,%s,%s)',
            (sid, oid, 'enrolled')
        )
        # 触发器会自动在 grades 表中插入草稿记录
        flash('选课成功！', 'success')
    except Exception as e:
        flash(f'选课失败：{str(e)}', 'danger')

    return redirect(url_for('student.courses'))


# ---- 退课 ----
@student_bp.route('/drop/<int:oid>', methods=['POST'])
def drop(oid):
    sid = get_student_id()

    enrollment = query(
        "SELECT id FROM enrollments WHERE student_id=%s AND course_offering_id=%s AND status='enrolled'",
        (sid, oid), one=True
    )
    if not enrollment:
        flash('未选该课程', 'warning')
        return redirect(url_for('student.schedule'))

    # 检查退课窗口
    offering = query('SELECT semester_id FROM course_offerings WHERE id=%s', (oid,), one=True)
    in_period = query(
        """SELECT COUNT(*) AS c FROM course_selection_periods
           WHERE semester_id=%s AND period_type='drop' AND is_active=1
             AND NOW() BETWEEN start_time AND end_time""",
        (offering['semester_id'],), one=True
    )
    if in_period['c'] == 0:
        flash('当前不在退课窗口期内', 'warning')
        return redirect(url_for('student.schedule'))

    # 检查是否已有成绩
    grade = query(
        "SELECT status FROM grades WHERE enrollment_id=%s", (enrollment['id'],), one=True
    )
    if grade and grade['status'] != 'draft':
        flash('该课程已有成绩记录，无法退课', 'danger')
        return redirect(url_for('student.schedule'))

    try:
        execute(
            "UPDATE enrollments SET status='dropped', dropped_at=NOW() WHERE id=%s AND status='enrolled'",
            (enrollment['id'],)
        )
        execute("DELETE FROM grades WHERE enrollment_id=%s AND status='draft'", (enrollment['id'],))
        flash('退课成功', 'success')
    except Exception as e:
        flash(f'退课失败：{str(e)}', 'danger')

    return redirect(url_for('student.schedule'))


# ---- 我的课表 ----
@student_bp.route('/schedule')
def schedule():
    sid = get_student_id()
    data = query(
        """SELECT e.id AS enrollment_id, co.id AS offering_id,
                  c.name AS course_name, c.code AS course_code, c.credit,
                  t.name AS teacher_name, co.schedule, co.classroom,
                  sem.name AS semester_name, e.enrolled_at
           FROM enrollments e
           JOIN course_offerings co ON e.course_offering_id = co.id
           JOIN courses c ON co.course_id = c.id
           JOIN teachers t ON co.teacher_id = t.id
           JOIN semesters sem ON co.semester_id = sem.id
           WHERE e.student_id = %s AND e.status = 'enrolled'
           ORDER BY co.schedule""",
        (sid,)
    )
    return render_template('student/schedule.html', schedule=data)


# ---- 成绩查询 ----
@student_bp.route('/grades')
def grades():
    sid = get_student_id()
    data = query(
        """SELECT c.name AS course_name, c.code AS course_code, c.credit, c.course_type,
                  g.regular_grade, g.exam_grade, g.total_grade, g.gpa_point,
                  g.status AS grade_status, sem.name AS semester_name,
                  t.name AS teacher_name
           FROM grades g
           JOIN enrollments e ON g.enrollment_id = e.id
           JOIN course_offerings co ON e.course_offering_id = co.id
           JOIN courses c ON co.course_id = c.id
           JOIN semesters sem ON co.semester_id = sem.id
           LEFT JOIN teachers t ON co.teacher_id = t.id
           WHERE e.student_id = %s AND e.status = 'enrolled'
           ORDER BY sem.id, c.code""",
        (sid,)
    )

    # 计算GPA
    gpa_info = query(
        """SELECT ROUND(COALESCE(SUM(g.gpa_point * c.credit), 0) / NULLIF(SUM(c.credit), 0), 2) AS gpa,
                  SUM(c.credit) AS total_credits,
                  COUNT(CASE WHEN g.status IN ('approved','published') THEN 1 END) AS graded_count,
                  COUNT(*) AS total_count
           FROM grades g
           JOIN enrollments e ON g.enrollment_id = e.id
           JOIN course_offerings co ON e.course_offering_id = co.id
           JOIN courses c ON co.course_id = c.id
           WHERE e.student_id=%s AND e.status='enrolled'""",
        (sid,), one=True
    )

    return render_template('student/grades.html', grades=data,
                           gpa=gpa_info['gpa'] or 0,
                           total_credits=gpa_info['total_credits'] or 0,
                           graded_count=gpa_info['graded_count'] or 0,
                           total_count=gpa_info['total_count'] or 0)
