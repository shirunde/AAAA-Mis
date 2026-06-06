"""学生模块路由"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.decorators import role_required
from app.db import query, execute, paginate, call_proc, call_proc_rows
from app.helpers import parse_schedule_slots, get_active_selection_periods

student_bp = Blueprint('student', __name__)


@student_bp.before_request
@login_required
@role_required('student')
def check_student():
    pass


def get_student_id():
    s = query('SELECT id FROM students WHERE user_id=%s', (current_user['id'],), one=True)
    return s['id'] if s else None


def _calc_overall_gpa(sid):
    """累计 GPA（仅已发布成绩）"""
    info = query("""SELECT ROUND(COALESCE(SUM(g.gpa_point*c.credit),0)/NULLIF(SUM(c.credit),0),2) AS gpa,
        SUM(c.credit) AS total_credits FROM grades g
        JOIN enrollments e ON g.enrollment_id=e.id
        JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        WHERE e.student_id=%s AND e.status='enrolled'
        AND g.status='published' AND g.gpa_point IS NOT NULL""", (sid,), one=True)
    return info['gpa'] or 0, info['total_credits'] or 0


@student_bp.route('/')
def dashboard():
    sid = get_student_id()
    enrolled_count = query(
        "SELECT COUNT(*) AS c FROM enrollments WHERE student_id=%s AND status='enrolled'",
        (sid,), one=True
    )['c']
    gpa, total_credits = _calc_overall_gpa(sid)

    recent_grades = query("""SELECT c.name AS course_name, g.total_grade, g.gpa_point, g.status AS grade_status
        FROM grades g JOIN enrollments e ON g.enrollment_id=e.id
        JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        WHERE e.student_id=%s AND e.status='enrolled' AND g.status='published'
        AND g.total_grade IS NOT NULL
        ORDER BY g.published_at DESC, g.updated_at DESC LIMIT 5""", (sid,))

    academic_alert = None
    if sid:
        try:
            rows = call_proc_rows('sp_list_academic_alerts', (None, sid))
            academic_alert = rows[0] if rows else None
        except Exception:
            academic_alert = None

    selection_periods = get_active_selection_periods()
    return render_template('student/dashboard.html',
                           enrolled_count=enrolled_count,
                           gpa=gpa,
                           total_credits=total_credits,
                           recent_grades=recent_grades,
                           academic_alert=academic_alert,
                           selection_periods=selection_periods)


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

    enrolled_ids = set()
    conflict_offering_ids = set()
    selection_periods = get_active_selection_periods()
    if sid:
        rows = query('SELECT course_offering_id FROM enrollments WHERE student_id=%s AND status=%s',
                     (sid, 'enrolled'))
        enrolled_ids = {r['course_offering_id'] for r in rows}
        # 用 parse_schedule_slots 做智能冲突检测（"周一1-2节"与"周一第1-2节"视为冲突）
        enrolled_schedules = query("""SELECT co.id, co.schedule FROM enrollments e
                             JOIN course_offerings co ON e.course_offering_id = co.id
                             WHERE e.student_id = %s AND e.status = 'enrolled'
                               AND co.schedule IS NOT NULL AND co.schedule != ''""", (sid,))
        enrolled_slots = set()
        for es in enrolled_schedules:
            enrolled_slots |= parse_schedule_slots(es['schedule'])
        # 对当前页开课做冲突检测
        for o in data.get('items', []):
            if o['id'] not in enrolled_ids and o.get('schedule'):
                o_slots = parse_schedule_slots(o['schedule'])
                if o_slots & enrolled_slots:
                    conflict_offering_ids.add(o['id'])

    return render_template('student/courses.html', **data, search=search, type=course_type,
                           enrolled_ids=enrolled_ids, conflict_offering_ids=conflict_offering_ids,
                           selection_periods=selection_periods)


@student_bp.route('/course/<int:oid>/detail')
def course_detail(oid):
    detail = query("""SELECT co.*, c.name AS course_name, c.code AS course_code, c.credit, c.hours,
        c.course_type, c.description, t.name AS teacher_name, t.title,
        sem.name AS semester_name,
        (SELECT COUNT(*) FROM enrollments e WHERE e.course_offering_id=co.id AND e.status='enrolled') AS enrolled_count
        FROM course_offerings co
        JOIN courses c ON co.course_id=c.id
        JOIN teachers t ON co.teacher_id=t.id
        JOIN semesters sem ON co.semester_id=sem.id
        WHERE co.id=%s AND co.status='published'""", (oid,), one=True)
    if not detail:
        return jsonify({'error': 'not found'}), 404
    return jsonify(detail)


@student_bp.route('/enroll/<int:oid>', methods=['POST'])
def enroll(oid):
    sid = get_student_id()
    try:
        out = call_proc('sp_enroll_course', (sid, oid, 0, ''), [2, 3])
        result_code = out['p2']
        result_msg = out['p3']
        msgs = {0: 'success', 1: 'warning', 2: 'danger', 3: 'warning', 4: 'warning', 5: 'danger'}
        flash(result_msg, msgs.get(result_code, 'danger'))
    except Exception as e:
        flash(f'选课失败：{str(e)}', 'danger')
    return redirect(url_for('student.courses'))


@student_bp.route('/drop/<int:oid>', methods=['POST'])
def drop(oid):
    sid = get_student_id()
    try:
        out = call_proc('sp_drop_course', (sid, oid, 0, ''), [2, 3])
        result_code = out['p2']
        result_msg = out['p3']
        msgs = {0: 'success', 1: 'warning', 2: 'warning', 3: 'danger'}
        flash(result_msg, msgs.get(result_code, 'danger'))
    except Exception as e:
        flash(f'退课失败：{str(e)}', 'danger')
    return redirect(url_for('student.schedule'))


@student_bp.route('/schedule')
def schedule():
    sid = get_student_id()
    data = query("""SELECT offering_id, course_name, course_code, credit, teacher_name,
        schedule, classroom, semester_name, enrolled_at
        FROM v_student_schedule WHERE student_id=%s ORDER BY schedule""", (sid,))
    return render_template('student/schedule.html', schedule=data)


@student_bp.route('/grades')
def grades():
    sid = get_student_id()
    data = query("""SELECT c.name AS course_name, c.code AS course_code, c.credit, c.course_type,
        g.regular_grade, g.exam_grade, g.total_grade, g.gpa_point,
        g.status AS grade_status, sem.name AS semester_name, t.name AS teacher_name
        FROM enrollments e
        JOIN course_offerings co ON e.course_offering_id=co.id
        JOIN courses c ON co.course_id=c.id
        JOIN semesters sem ON co.semester_id=sem.id
        LEFT JOIN teachers t ON co.teacher_id=t.id
        LEFT JOIN grades g ON g.enrollment_id=e.id
        WHERE e.student_id=%s AND e.status='enrolled'
        ORDER BY sem.id, c.code""", (sid,))

    gpa, total_credits = _calc_overall_gpa(sid)
    counts = query("""SELECT
        COUNT(CASE WHEN g.status='published' THEN 1 END) AS graded_count,
        COUNT(*) AS total_count
        FROM enrollments e
        LEFT JOIN grades g ON g.enrollment_id=e.id
        WHERE e.student_id=%s AND e.status='enrolled'""", (sid,), one=True)

    return render_template('student/grades.html', grades=data,
                           gpa=gpa,
                           total_credits=total_credits,
                           graded_count=counts['graded_count'] or 0,
                           total_count=counts['total_count'] or 0)


@student_bp.route('/transcript')
def transcript():
    sid = get_student_id()
    student = query("""SELECT s.*, u.username, m.name AS major_name, cl.name AS class_name
        FROM students s JOIN users u ON s.user_id=u.id
        LEFT JOIN majors m ON s.major_id=m.id
        LEFT JOIN classes cl ON s.class_id=cl.id
        WHERE s.id=%s""", (sid,), one=True)

    grades = query("""SELECT course_code, course_name, credit, course_type,
        regular_grade, exam_grade, total_grade, gpa_point, grade_status, semester_name
        FROM v_student_transcript
        WHERE student_id=%s AND grade_status='published'
        ORDER BY semester_name, course_code""", (sid,))

    gpa, total_credits = _calc_overall_gpa(sid)
    return render_template('student/transcript.html', student=student, grades=grades,
                           gpa=gpa, total_credits=total_credits, now=datetime.now())
