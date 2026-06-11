"""教师模块路由"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from app.decorators import role_required
from app.db import query, execute, insert, get_conn
from app.helpers import (
    log_action, check_offering_conflicts, check_classroom_capacity,
    save_offering_schedules, get_offering_schedule,
)

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


def _offering_form_context():
    return {
        'courses': query('SELECT * FROM courses ORDER BY id'),
        'semesters': query('SELECT * FROM semesters ORDER BY id DESC'),
        'time_slots': query('SELECT * FROM time_slots ORDER BY day_of_week, period_num'),
        'classrooms': query('SELECT * FROM classrooms WHERE is_active=1 ORDER BY code'),
    }


@teacher_bp.route('/apply-offering', methods=['GET', 'POST'])
def apply_offering():
    tid = get_teacher_id()
    if request.method == 'POST':
        time_slot_ids = request.form.getlist('time_slots', type=int)
        classroom_id = request.form.get('classroom_id', type=int)
        semester_id = request.form.get('semester_id', type=int)
        max_students = request.form.get('max_students', type=int)

        if not time_slot_ids or not classroom_id:
            flash('请选择上课时间和教室', 'danger')
            return render_template('teacher/apply_offering.html', **_offering_form_context())

        ok, cap_msg = check_classroom_capacity(classroom_id, max_students)
        if not ok:
            flash(cap_msg, 'danger')
            return render_template('teacher/apply_offering.html', **_offering_form_context())

        conflicts = check_offering_conflicts(
            0, semester_id, tid, classroom_id, time_slot_ids, include_pending=True
        )
        if conflicts['conflicts']:
            flash('申请未提交：' + '；'.join(conflicts['conflicts']), 'danger')
            return render_template('teacher/apply_offering.html', **_offering_form_context())

        try:
            offering_id = insert(
                """INSERT INTO course_offerings (course_id, teacher_id, semester_id, max_students, apply_reason)
                   VALUES (%s,%s,%s,%s,%s)""",
                (request.form['course_id'], tid, semester_id,
                 max_students, request.form.get('apply_reason', ''))
            )
            save_offering_schedules(offering_id, time_slot_ids, classroom_id)
        except Exception as e:
            if 'uk_offering' in str(e).lower() or 'duplicate' in str(e).lower():
                flash('您本学期已申请过该课程，请勿重复提交', 'warning')
            else:
                flash(f'提交失败：{str(e)}', 'danger')
            return render_template('teacher/apply_offering.html', **_offering_form_context())

        flash('开课申请已提交，排课信息已预检通过，请等待管理员审核', 'success')
        log_action('offering_apply', 'offering', offering_id, f'申请开课: course_id={request.form["course_id"]}')
        return redirect(url_for('teacher.my_offerings'))

    return render_template('teacher/apply_offering.html', **_offering_form_context())


@teacher_bp.route('/check-conflicts', methods=['POST'])
def check_conflicts_api():
    """申请开课前实时冲突检测"""
    tid = get_teacher_id()
    data = request.get_json(silent=True) or {}
    time_slot_ids = data.get('time_slot_ids', [])
    classroom_id = data.get('classroom_id')
    semester_id = data.get('semester_id')
    offering_id = data.get('offering_id', 0)
    max_students = data.get('max_students')

    if not time_slot_ids or not classroom_id or not semester_id:
        return jsonify({'ok': False, 'message': '请先选择学期、教室和上课时间'})

    try:
        result = check_offering_conflicts(
            offering_id, semester_id, tid, classroom_id, time_slot_ids, include_pending=True
        )
        cap_ok, cap_msg = True, ''
        if max_students:
            cap_ok, cap_msg = check_classroom_capacity(classroom_id, int(max_students))
        return jsonify({
            'ok': not result['conflicts'] and cap_ok,
            'conflicts': result['conflicts'],
            'capacity_warning': cap_msg if not cap_ok else '',
        })
    except Exception as e:
        return jsonify({'ok': True, 'conflicts': [], 'capacity_warning': '', 'check_error': str(e)})


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
    for o in data:
        o['schedule_display'] = get_offering_schedule(o['id'])
        o['classroom_display'] = query(
            """SELECT DISTINCT c.name FROM offering_schedules os
               JOIN classrooms c ON os.classroom_id=c.id WHERE os.course_offering_id=%s""",
            (o['id'],)
        )
        o['classroom_display'] = ', '.join(r['name'] for r in o['classroom_display']) or '-'
        o['selected_slots'] = [
            r['time_slot_id'] for r in query(
                'SELECT time_slot_id FROM offering_schedules WHERE course_offering_id=%s', (o['id'],)
            )
        ]
        o['classroom_id'] = query(
            'SELECT classroom_id FROM offering_schedules WHERE course_offering_id=%s LIMIT 1',
            (o['id'],), one=True
        )
        o['classroom_id'] = o['classroom_id']['classroom_id'] if o['classroom_id'] else None

    ctx = _offering_form_context()
    return render_template('teacher/my_offerings.html', offerings=data, **ctx)


@teacher_bp.route('/offering/<int:oid>/withdraw', methods=['POST'])
def withdraw_offering(oid):
    require_offering_owner(oid)
    o = query('SELECT status FROM course_offerings WHERE id=%s', (oid,), one=True)
    if not o or o['status'] != 'pending':
        flash('只能撤销待审核的申请', 'warning')
        return redirect(url_for('teacher.my_offerings'))
    execute('DELETE FROM course_offerings WHERE id=%s AND status=%s', (oid, 'pending'))
    flash('开课申请已撤销', 'success')
    log_action('offering_withdraw', 'offering', oid, f'撤销开课申请ID={oid}')
    return redirect(url_for('teacher.my_offerings'))


@teacher_bp.route('/offering/<int:oid>/edit', methods=['POST'])
def edit_offering(oid):
    tid = get_teacher_id()
    require_offering_owner(oid)
    o = query('SELECT status FROM course_offerings WHERE id=%s', (oid,), one=True)
    if not o or o['status'] != 'pending':
        flash('只能编辑待审核的申请', 'warning')
        return redirect(url_for('teacher.my_offerings'))

    time_slot_ids = request.form.getlist('time_slots', type=int)
    classroom_id = request.form.get('classroom_id', type=int)
    semester_id = request.form.get('semester_id', type=int)
    max_students = request.form.get('max_students', type=int)

    if not time_slot_ids or not classroom_id:
        flash('请选择上课时间和教室', 'danger')
        return redirect(url_for('teacher.my_offerings'))

    ok, cap_msg = check_classroom_capacity(classroom_id, max_students)
    if not ok:
        flash(cap_msg, 'danger')
        return redirect(url_for('teacher.my_offerings'))

    conflicts = check_offering_conflicts(
        oid, semester_id, tid, classroom_id, time_slot_ids, include_pending=True
    )
    if conflicts['conflicts']:
        flash('修改未保存：' + '；'.join(conflicts['conflicts']), 'danger')
        return redirect(url_for('teacher.my_offerings'))

    execute("""UPDATE course_offerings SET course_id=%s, semester_id=%s, max_students=%s, apply_reason=%s
               WHERE id=%s AND status='pending'""",
            (request.form['course_id'], semester_id, max_students,
             request.form.get('apply_reason', ''), oid))
    save_offering_schedules(oid, time_slot_ids, classroom_id)
    flash('开课申请已更新，排课信息已重新校验', 'success')
    log_action('offering_edit', 'offering', oid, f'修改开课申请ID={oid}')
    return redirect(url_for('teacher.my_offerings'))


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
    log_action('grade_edit', 'grade', eid, f'录入/修改成绩 enrollment={eid}')
    flash('成绩保存成功', 'success')
    return redirect(request.referrer or url_for('teacher.dashboard'))


@teacher_bp.route('/grade/<int:eid>/submit', methods=['POST'])
def grade_submit(eid):
    require_enrollment_owner(eid)
    execute(
        "UPDATE grades SET status='submitted', submitted_at=NOW() WHERE enrollment_id=%s AND status='draft'",
        (eid,)
    )
    log_action('grade_submit', 'grade', eid, f'提交成绩 enrollment={eid}')
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
    log_action('grade_batch_submit', 'grade', oid, f'批量提交成绩 offering={oid}')
    return redirect(url_for('teacher.offering_students', oid=oid))


@teacher_bp.route('/grade/<int:eid>/withdraw', methods=['POST'])
def grade_withdraw(eid):
    require_enrollment_owner(eid)
    locked = query("SELECT status FROM grades WHERE enrollment_id=%s", (eid,), one=True)
    if not locked or locked['status'] != 'submitted':
        flash('只能撤回已提交且未审核的成绩', 'warning')
        return redirect(request.referrer or url_for('teacher.dashboard'))
    execute(
        "UPDATE grades SET status='draft', submitted_at=NULL WHERE enrollment_id=%s AND status='submitted'",
        (eid,)
    )
    log_action('grade_withdraw', 'grade', eid, '教师撤回已提交成绩')
    flash('成绩已撤回至草稿状态', 'success')
    return redirect(request.referrer or url_for('teacher.dashboard'))


@teacher_bp.route('/offering/<int:oid>/batch-grade', methods=['POST'])
def batch_grade_edit(oid):
    require_offering_owner(oid)
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            for key, value in request.form.items():
                parts = key.split('_', 1)
                if len(parts) != 2:
                    continue
                field, eid_str = parts
                if field not in ('regular', 'exam') or not eid_str.isdigit():
                    continue
                eid = int(eid_str)
                val = value.strip()
                num_val = float(val) if val else None
                if num_val is not None and not (0 <= num_val <= 100):
                    conn.rollback()
                    flash('成绩值必须在 0-100 之间', 'danger')
                    return redirect(url_for('teacher.offering_students', oid=oid))

                cur.execute("SELECT status FROM grades WHERE enrollment_id=%s FOR UPDATE", (eid,))
                row = cur.fetchone()
                if row and row['status'] != 'draft':
                    continue

                col_name = 'regular_grade' if field == 'regular' else 'exam_grade'
                cur.execute(
                    f"UPDATE grades SET {col_name}=%s WHERE enrollment_id=%s AND status='draft'",
                    (num_val, eid)
                )
            conn.commit()
        log_action('grade_batch_edit', 'grade', oid, f'批量录入成绩 offering={oid}')
        flash('批量成绩保存成功', 'success')
    except Exception as e:
        flash(f'批量保存失败：{str(e)}', 'danger')
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
