"""教师模块路由"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from app.decorators import role_required
from app.db import query, execute

teacher_bp = Blueprint('teacher', __name__)


@teacher_bp.before_request
@login_required
@role_required('teacher')
def check_teacher():
    pass


def get_teacher_id():
    t = query('SELECT id FROM teachers WHERE user_id = %s', (current_user['id'],), one=True)
    return t['id'] if t else None


def require_offering_owner(oid):
    tid = get_teacher_id()
    if not tid:
        abort(403)
    row = query(
        'SELECT id FROM course_offerings WHERE id=%s AND teacher_id=%s',
        (oid, tid), one=True
    )
    if not row:
        abort(403)
    return oid


def require_enrollment_owner(eid):
    tid = get_teacher_id()
    if not tid:
        abort(403)
    row = query(
        """SELECT e.id FROM enrollments e
           JOIN course_offerings co ON e.course_offering_id = co.id
           WHERE e.id = %s AND co.teacher_id = %s""",
        (eid, tid), one=True
    )
    if not row:
        abort(403)
    return eid


@teacher_bp.route('/')
def dashboard():
    tid = get_teacher_id()
    my_offerings = query(
        """SELECT co.*, c.name AS course_name, c.code AS course_code,
                  sem.name AS semester_name,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.course_offering_id=co.id AND e.status='enrolled') AS enrolled_count
           FROM course_offerings co
           JOIN courses c ON co.course_id = c.id
           JOIN semesters sem ON co.semester_id = sem.id
           WHERE co.teacher_id = %s
           ORDER BY co.created_at DESC""",
        (tid,)
    )
    return render_template('teacher/dashboard.html', offerings=my_offerings)


@teacher_bp.route('/apply-offering', methods=['GET', 'POST'])
def apply_offering():
    tid = get_teacher_id()
    if request.method == 'POST':
        execute(
            """INSERT INTO course_offerings (course_id, teacher_id, semester_id, max_students, classroom, schedule, apply_reason)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (request.form['course_id'], tid, request.form['semester_id'],
             request.form['max_students'], request.form.get('classroom', ''),
             request.form.get('schedule', ''), request.form.get('apply_reason', ''))
        )
        flash('开课申请已提交，请等待管理员审核', 'success')
        return redirect(url_for('teacher.my_offerings'))

    courses = query('SELECT * FROM courses ORDER BY id')
    semesters = query('SELECT * FROM semesters ORDER BY id DESC')
    return render_template('teacher/apply_offering.html', courses=courses, semesters=semesters)


@teacher_bp.route('/my-offerings')
def my_offerings():
    tid = get_teacher_id()
    data = query(
        """SELECT co.*, c.name AS course_name, c.code AS course_code,
                  sem.name AS semester_name,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.course_offering_id=co.id AND e.status='enrolled') AS enrolled_count
           FROM course_offerings co
           JOIN courses c ON co.course_id = c.id
           JOIN semesters sem ON co.semester_id = sem.id
           WHERE co.teacher_id = %s
           ORDER BY co.created_at DESC""",
        (tid,)
    )
    return render_template('teacher/my_offerings.html', offerings=data)


@teacher_bp.route('/offering/<int:oid>/students')
def offering_students(oid):
    require_offering_owner(oid)
    data = query(
        """SELECT e.id AS enrollment_id, s.student_no, s.name, s.gender,
                  m.name AS major_name, c.name AS class_name, e.enrolled_at,
                  g.regular_grade, g.exam_grade, g.total_grade, g.status AS grade_status
           FROM enrollments e
           JOIN students s ON e.student_id = s.id
           LEFT JOIN majors m ON s.major_id = m.id
           LEFT JOIN classes c ON s.class_id = c.id
           LEFT JOIN grades g ON g.enrollment_id = e.id
           WHERE e.course_offering_id = %s AND e.status = 'enrolled'
           ORDER BY s.student_no""",
        (oid,)
    )
    offering = query(
        """SELECT co.*, c.name AS course_name, sem.name AS semester_name
           FROM course_offerings co JOIN courses c ON co.course_id=c.id
           JOIN semesters sem ON co.semester_id=sem.id WHERE co.id=%s""",
        (oid,), one=True
    )
    return render_template('teacher/offering_students.html', students=data, offering=offering)


@teacher_bp.route('/grade/<int:eid>/edit', methods=['POST'])
def grade_edit(eid):
    require_enrollment_owner(eid)
    regular = request.form.get('regular_grade', '').strip()
    exam = request.form.get('exam_grade', '').strip()

    regular_val = float(regular) if regular else None
    exam_val = float(exam) if exam else None
    if regular_val is not None and not (0 <= regular_val <= 100):
        flash('平时成绩须在 0-100 之间', 'danger')
        return redirect(request.referrer or url_for('teacher.dashboard'))
    if exam_val is not None and not (0 <= exam_val <= 100):
        flash('期末成绩须在 0-100 之间', 'danger')
        return redirect(request.referrer or url_for('teacher.dashboard'))

    locked = query(
        "SELECT status FROM grades WHERE enrollment_id=%s",
        (eid,), one=True
    )
    if locked and locked['status'] not in ('draft',):
        flash('成绩已提交，无法修改', 'warning')
        return redirect(request.referrer or url_for('teacher.dashboard'))

    execute(
        """UPDATE grades SET regular_grade=%s, exam_grade=%s WHERE enrollment_id=%s""",
        (regular_val, exam_val, eid)
    )
    flash('成绩保存成功', 'success')
    return redirect(request.referrer or url_for('teacher.dashboard'))


@teacher_bp.route('/grade/<int:eid>/submit', methods=['POST'])
def grade_submit(eid):
    require_enrollment_owner(eid)
    execute(
        "UPDATE grades SET status='submitted', submitted_at=NOW() WHERE enrollment_id=%s AND status='draft'",
        (eid,)
    )
    flash('成绩已提交，等待管理员审核', 'success')
    return redirect(request.referrer or url_for('teacher.dashboard'))


@teacher_bp.route('/offering/<int:oid>/submit-all', methods=['POST'])
def grade_submit_all(oid):
    require_offering_owner(oid)
    execute(
        """UPDATE grades g
           JOIN enrollments e ON g.enrollment_id = e.id
           SET g.status='submitted', g.submitted_at=NOW()
           WHERE e.course_offering_id=%s AND g.status='draft'
             AND g.regular_grade IS NOT NULL AND g.exam_grade IS NOT NULL""",
        (oid,)
    )
    flash('所有已录入成绩的课程已批量提交', 'success')
    return redirect(url_for('teacher.offering_students', oid=oid))


@teacher_bp.route('/grade-stats')
def grade_stats():
    tid = get_teacher_id()
    semester_id = request.args.get('semester_id', '', type=int)

    where = 'AND co.semester_id=%s' if semester_id else ''
    args = [tid, semester_id] if semester_id else [tid]

    offerings = query(
        f"""SELECT co.id, c.name AS course_name, sem.name AS semester_name
           FROM course_offerings co
           JOIN courses c ON co.course_id = c.id
           JOIN semesters sem ON co.semester_id = sem.id
           WHERE co.teacher_id = %s AND co.status IN ('approved','published') {where}
           ORDER BY co.id DESC""",
        tuple(args)
    )
    semesters = query('SELECT * FROM semesters ORDER BY id DESC')
    return render_template('teacher/grade_stats.html', offerings=offerings,
                           semesters=semesters, selected_semester=semester_id)


@teacher_bp.route('/offering/<int:oid>/stats-data')
def offering_stats_data(oid):
    require_offering_owner(oid)
    dist = query(
        """SELECT
             CASE
               WHEN g.total_grade >= 90 THEN '90-100'
               WHEN g.total_grade >= 80 THEN '80-89'
               WHEN g.total_grade >= 70 THEN '70-79'
               WHEN g.total_grade >= 60 THEN '60-69'
               ELSE '<60'
             END AS grade_range,
             COUNT(*) AS count
           FROM grades g
           JOIN enrollments e ON g.enrollment_id = e.id
           WHERE e.course_offering_id = %s AND g.total_grade IS NOT NULL
           GROUP BY grade_range
           ORDER BY grade_range DESC""",
        (oid,)
    )

    stats = query(
        """SELECT
             COUNT(*) AS total,
             ROUND(AVG(g.total_grade), 1) AS avg_grade,
             MAX(g.total_grade) AS max_grade,
             MIN(g.total_grade) AS min_grade,
             ROUND(COUNT(CASE WHEN g.total_grade >= 60 THEN 1 END)*100.0/COUNT(*), 1) AS pass_rate
           FROM grades g
           JOIN enrollments e ON g.enrollment_id = e.id
           WHERE e.course_offering_id = %s AND g.total_grade IS NOT NULL""",
        (oid,), one=True
    )
    return jsonify({'distribution': dist, 'stats': stats})
