"""学生模块路由"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.decorators import role_required
from app.db import query, execute, paginate

student_bp = Blueprint('student', __name__)


@student_bp.before_request
@login_required
@role_required('student')
def check_student():
    pass


def get_student_id():
    s = query('SELECT id FROM students WHERE user_id=%s', (current_user['id'],), one=True)
    return s['id'] if s else None


@student_bp.route('/')
def dashboard():
    sid = get_student_id()
    enrolled_count = query(
        "SELECT COUNT(*) AS c FROM enrollments WHERE student_id=%s AND status='enrolled'",
        (sid,), one=True
    )['c']
    gpa_info = query("""SELECT ROUND(COALESCE(SUM(g.gpa_point*c.credit),0)/NULLIF(SUM(c.credit),0),2) AS gpa,
        SUM(c.credit) AS total_credits FROM grades g
        JOIN enrollments e ON g.enrollment_id=e.id
        JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        WHERE e.student_id=%s AND e.status='enrolled'
        AND g.status IN ('approved','published') AND g.gpa_point IS NOT NULL""", (sid,), one=True)

    # Recent grades
    recent_grades = query("""SELECT c.name AS course_name, g.total_grade, g.gpa_point, g.status AS grade_status
        FROM grades g JOIN enrollments e ON g.enrollment_id=e.id
        JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        WHERE e.student_id=%s AND e.status='enrolled' AND g.total_grade IS NOT NULL
        ORDER BY g.updated_at DESC LIMIT 5""", (sid,))

    return render_template('student/dashboard.html',
                           enrolled_count=enrolled_count,
                           gpa=gpa_info['gpa'] or 0,
                           total_credits=gpa_info['total_credits'] or 0,
                           recent_grades=recent_grades)


# ---- 课程查询 (分页) ----
_COURSE_SQL = """SELECT co.*, c.name AS course_name, c.code AS course_code, c.credit, c.hours,
    c.course_type, c.description, t.name AS teacher_name, t.title,
    sem.name AS semester_name,
    (SELECT COUNT(*) FROM enrollments e WHERE e.course_offering_id=co.id AND e.status='enrolled') AS enrolled_count
    FROM course_offerings co
    JOIN courses c ON co.course_id=c.id
    JOIN teachers t ON co.teacher_id=t.id
    JOIN semesters sem ON co.semester_id=sem.id
    WHERE co.status='published'"""


@student_bp.route('/courses')
def courses():
    sid = get_student_id()
    search = request.args.get('search', '').strip()
    course_type = request.args.get('type', '').strip()
    page = request.args.get('page', 1, type=int)

    current_semester = query('SELECT id FROM semesters WHERE is_current=1', one=True)

    where_extra = ''
    args = []
    if current_semester:
        where_extra += ' AND co.semester_id=%s'
        args.append(current_semester['id'])
    if search:
        where_extra += ' AND (c.name LIKE %s OR c.code LIKE %s OR t.name LIKE %s)'
        args.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if course_type:
        where_extra += ' AND c.course_type=%s'
        args.append(course_type)

    data = paginate(_COURSE_SQL + where_extra + ' ORDER BY co.id DESC', tuple(args), page=page)

    # Mark already enrolled
    enrolled_ids = set()
    if sid:
        rows = query('SELECT course_offering_id FROM enrollments WHERE student_id=%s AND status=%s',
                     (sid, 'enrolled'))
        enrolled_ids = {r['course_offering_id'] for r in rows}

    return render_template('student/courses.html', **data, search=search, type=course_type,
                           enrolled_ids=enrolled_ids)


@student_bp.route('/course/<int:oid>/detail')
def course_detail(oid):
    """AJAX: course detail for modal"""
    detail = query("""SELECT co.*, c.name AS course_name, c.code AS course_code, c.credit, c.hours,
        c.course_type, c.description, t.name AS teacher_name, t.title,
        sem.name AS semester_name,
        (SELECT COUNT(*) FROM enrollments e WHERE e.course_offering_id=co.id AND e.status='enrolled') AS enrolled_count
        FROM course_offerings co
        JOIN courses c ON co.course_id=c.id
        JOIN teachers t ON co.teacher_id=t.id
        JOIN semesters sem ON co.semester_id=sem.id
        WHERE co.id=%s""", (oid,), one=True)
    if not detail:
        return jsonify({'error': 'not found'}), 404
    return jsonify(detail)


# ---- 选课 ----
@student_bp.route('/enroll/<int:oid>', methods=['POST'])
def enroll(oid):
    sid = get_student_id()
    offering = query("""SELECT co.semester_id, co.schedule FROM course_offerings co
                        WHERE co.id=%s AND co.status='published'""", (oid,), one=True)
    if not offering:
        flash('该课程不可选', 'danger')
        return redirect(url_for('student.courses'))

    in_period = query("""SELECT COUNT(*) AS c FROM course_selection_periods
        WHERE semester_id=%s AND period_type='selection' AND is_active=1
        AND NOW() BETWEEN start_time AND end_time""", (offering['semester_id'],), one=True)
    if in_period['c'] == 0:
        flash('当前不在选课窗口期内', 'warning')
        return redirect(url_for('student.courses'))

    already = query("SELECT id FROM enrollments WHERE student_id=%s AND course_offering_id=%s AND status='enrolled'",
                    (sid, oid), one=True)
    if already:
        flash('已选过该课程', 'warning')
        return redirect(url_for('student.courses'))

    # Check time conflict
    if offering.get('schedule') and offering['schedule'].strip():
        conflict = query("""SELECT c.name FROM enrollments e
            JOIN course_offerings co ON e.course_offering_id=co.id
            JOIN course_offerings co2 ON co2.id=%s
            JOIN courses c ON co.course_id=c.id
            WHERE e.student_id=%s AND e.status='enrolled'
            AND co.semester_id=co2.semester_id
            AND co.schedule=co2.schedule""", (oid, sid))
        if conflict:
            flash(f'上课时间冲突：已选课程「{conflict[0]["name"]}」时间相同', 'danger')
            return redirect(url_for('student.courses'))

    count = query("SELECT COUNT(*) AS c FROM enrollments WHERE course_offering_id=%s AND status='enrolled'", (oid,), one=True)
    max_s = query('SELECT max_students FROM course_offerings WHERE id=%s', (oid,), one=True)
    if count['c'] >= max_s['max_students']:
        flash('该课程选课人数已满', 'warning')
        return redirect(url_for('student.courses'))

    try:
        execute('INSERT INTO enrollments (student_id, course_offering_id, status) VALUES (%s,%s,%s)',
                (sid, oid, 'enrolled'))
        flash('选课成功！', 'success')
    except Exception as e:
        flash(f'选课失败：{str(e)}', 'danger')
    return redirect(url_for('student.courses'))


# ---- 退课 ----
@student_bp.route('/drop/<int:oid>', methods=['POST'])
def drop(oid):
    sid = get_student_id()
    enrollment = query("SELECT id FROM enrollments WHERE student_id=%s AND course_offering_id=%s AND status='enrolled'",
                       (sid, oid), one=True)
    if not enrollment:
        flash('未选该课程', 'warning')
        return redirect(url_for('student.schedule'))

    offering = query('SELECT semester_id FROM course_offerings WHERE id=%s', (oid,), one=True)
    in_period = query("""SELECT COUNT(*) AS c FROM course_selection_periods
        WHERE semester_id=%s AND period_type='drop' AND is_active=1
        AND NOW() BETWEEN start_time AND end_time""", (offering['semester_id'],), one=True)
    if in_period['c'] == 0:
        flash('当前不在退课窗口期内', 'warning')
        return redirect(url_for('student.schedule'))

    grade = query("SELECT status FROM grades WHERE enrollment_id=%s", (enrollment['id'],), one=True)
    if grade and grade['status'] != 'draft':
        flash('该课程已有成绩记录，无法退课', 'danger')
        return redirect(url_for('student.schedule'))

    try:
        execute("UPDATE enrollments SET status='dropped', dropped_at=NOW() WHERE id=%s", (enrollment['id'],))
        execute("DELETE FROM grades WHERE enrollment_id=%s AND status='draft'", (enrollment['id'],))
        flash('退课成功', 'success')
    except Exception as e:
        flash(f'退课失败：{str(e)}', 'danger')
    return redirect(url_for('student.schedule'))


# ---- 课表 ----
@student_bp.route('/schedule')
def schedule():
    sid = get_student_id()
    data = query("""SELECT e.id AS enrollment_id, co.id AS offering_id,
        c.name AS course_name, c.code AS course_code, c.credit,
        t.name AS teacher_name, co.schedule, co.classroom,
        sem.name AS semester_name, e.enrolled_at
        FROM enrollments e JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        JOIN teachers t ON co.teacher_id=t.id
        JOIN semesters sem ON co.semester_id=sem.id
        WHERE e.student_id=%s AND e.status='enrolled'
        ORDER BY co.schedule""", (sid,))
    return render_template('student/schedule.html', schedule=data)


# ---- 成绩查询 ----
@student_bp.route('/grades')
def grades():
    sid = get_student_id()
    data = query("""SELECT c.name AS course_name, c.code AS course_code, c.credit, c.course_type,
        g.regular_grade, g.exam_grade, g.total_grade, g.gpa_point,
        g.status AS grade_status, sem.name AS semester_name, t.name AS teacher_name
        FROM grades g JOIN enrollments e ON g.enrollment_id=e.id
        JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        JOIN semesters sem ON co.semester_id=sem.id
        LEFT JOIN teachers t ON co.teacher_id=t.id
        WHERE e.student_id=%s AND e.status='enrolled'
        ORDER BY sem.id, c.code""", (sid,))

    gpa_info = query("""SELECT ROUND(COALESCE(SUM(g.gpa_point*c.credit),0)/NULLIF(SUM(c.credit),0),2) AS gpa,
        SUM(c.credit) AS total_credits,
        COUNT(CASE WHEN g.status IN ('approved','published') THEN 1 END) AS graded_count,
        COUNT(*) AS total_count
        FROM grades g JOIN enrollments e ON g.enrollment_id=e.id
        JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        WHERE e.student_id=%s AND e.status='enrolled'""", (sid,), one=True)

    return render_template('student/grades.html', grades=data,
                           gpa=gpa_info['gpa'] or 0,
                           total_credits=gpa_info['total_credits'] or 0,
                           graded_count=gpa_info['graded_count'] or 0,
                           total_count=gpa_info['total_count'] or 0)


# ---- 成绩单打印版 ----
@student_bp.route('/transcript')
def transcript():
    sid = get_student_id()
    student = query("""SELECT s.*, u.username, m.name AS major_name, cl.name AS class_name
        FROM students s JOIN users u ON s.user_id=u.id
        LEFT JOIN majors m ON s.major_id=m.id
        LEFT JOIN classes cl ON s.class_id=cl.id
        WHERE s.id=%s""", (sid,), one=True)

    grades = query("""SELECT c.name AS course_name, c.code AS course_code, c.credit,
        c.course_type, g.regular_grade, g.exam_grade, g.total_grade, g.gpa_point,
        g.status AS grade_status, sem.name AS semester_name
        FROM grades g JOIN enrollments e ON g.enrollment_id=e.id
        JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        JOIN semesters sem ON co.semester_id=sem.id
        WHERE e.student_id=%s AND e.status='enrolled'
        ORDER BY sem.id, c.code""", (sid,))

    gpa = 0
    total_weighted, total_cred = 0, 0
    for g in grades:
        if g['gpa_point'] is not None and g['grade_status'] in ('approved', 'published'):
            total_weighted += g['gpa_point'] * g['credit']
            total_cred += g['credit']
    if total_cred > 0:
        gpa = round(total_weighted / total_cred, 2)

    return render_template('student/transcript.html', student=student, grades=grades,
                           gpa=gpa, total_credits=total_cred)
