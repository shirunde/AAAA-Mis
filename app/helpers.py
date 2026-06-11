"""公共辅助工具"""
import re
from datetime import timedelta

from flask import request
from flask_login import current_user
from app.db import get_conn, query, execute, insert


def log_action(action, target_type=None, target_id=None, detail=None):
    """写入系统日志，自动填充 user_id 和 ip_address"""
    user_id = current_user['id'] if current_user.is_authenticated else None
    ip_address = request.remote_addr or ''
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO system_logs (user_id, action, target_type, target_id, detail, ip_address)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, action, target_type, target_id, detail, ip_address)
        )
        conn.commit()


def notify_user(user_id, title, content, ntype='info', ref_type=None, ref_id=None):
    """发送站内通知"""
    if not user_id:
        return
    try:
        insert(
            """INSERT INTO notifications (user_id, title, content, ntype, ref_type, ref_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, title, content, ntype, ref_type, ref_id)
        )
    except Exception:
        pass


def notify_teacher(teacher_id, title, content, ntype='info', ref_type=None, ref_id=None):
    """向教师发送站内通知"""
    row = query('SELECT user_id FROM teachers WHERE id=%s', (teacher_id,), one=True)
    if row:
        notify_user(row['user_id'], title, content, ntype, ref_type, ref_id)


def get_unread_notification_count(user_id):
    """未读通知数量"""
    try:
        row = query(
            'SELECT COUNT(*) AS c FROM notifications WHERE user_id=%s AND is_read=0',
            (user_id,), one=True
        )
        return row['c'] if row else 0
    except Exception:
        return 0


def parse_schedule_slots(schedule_str):
    """
    将课表字符串解析为标准化的时间槽集合。
    例: "周一1-2节" -> {('周一','1-2')}
    """
    if not schedule_str:
        return set()

    DAY_MAP = {
        '一': '周一', '二': '周二', '三': '周三', '四': '周四', '五': '周五',
        '1': '周一', '2': '周二', '3': '周三', '4': '周四', '5': '周五',
    }

    slots = set()
    parts = re.split(r'[;,，；]', schedule_str)
    for part in parts:
        part = part.strip()
        m = re.match(
            r'(?:周|星期)([一二三四五1-5])\s*(?:第)?\s*(\d+)\s*[-\-~]\s*(\d+)',
            part
        )
        if m:
            day_key = m.group(1)
            start = int(m.group(2))
            end = int(m.group(3))
            day = DAY_MAP.get(day_key, f'周{day_key}')
            for period_start in range(start, end + 1, 2):
                period_end = min(period_start + 1, end)
                slots.add((day, f'{period_start}-{period_end}'))
    return slots


def schedules_conflict(schedule_a, schedule_b):
    """判断两段课表是否时间冲突"""
    return bool(parse_schedule_slots(schedule_a) & parse_schedule_slots(schedule_b))


def get_active_selection_periods(semester_id=None):
    """获取当前生效的选课/退课时间段列表"""
    if semester_id is None:
        current = query('SELECT id FROM semesters WHERE is_current=1 LIMIT 1', one=True)
        if not current:
            return []
        semester_id = current['id']
    return query(
        """SELECT * FROM course_selection_periods
           WHERE semester_id=%s AND is_active=1
             AND start_time <= NOW() AND end_time >= NOW()
           ORDER BY start_time""",
        (semester_id,)
    )


def get_upcoming_selection_periods(semester_id=None):
    """获取尚未开始但即将开放的选课窗口"""
    if semester_id is None:
        current = query('SELECT id FROM semesters WHERE is_current=1 LIMIT 1', one=True)
        if not current:
            return []
        semester_id = current['id']
    return query(
        """SELECT * FROM course_selection_periods
           WHERE semester_id=%s AND is_active=1 AND start_time > NOW()
           ORDER BY start_time""",
        (semester_id,)
    )


DAY_NAMES = {1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日'}


def format_time(t):
    """格式化 TIME 字段（PyMySQL 可能返回 timedelta）"""
    if t is None:
        return ''
    if isinstance(t, timedelta):
        total_secs = int(t.total_seconds())
        hours, remainder = divmod(total_secs, 3600)
        minutes = remainder // 60
        return f'{hours:02d}:{minutes:02d}'
    if hasattr(t, 'strftime'):
        return t.strftime('%H:%M')
    s = str(t)
    return s[:5] if len(s) >= 5 else s


_format_time = format_time


def get_offering_schedule_rows(offering_id):
    """获取开课的时间安排明细行"""
    return query("""SELECT ts.day_of_week, ts.period_num, ts.start_time, ts.end_time, ts.label,
                           c.code AS classroom_code, c.name AS classroom_name, c.capacity AS classroom_capacity
                    FROM offering_schedules os
                    JOIN time_slots ts ON os.time_slot_id = ts.id
                    JOIN classrooms c ON os.classroom_id = c.id
                    WHERE os.course_offering_id = %s
                    ORDER BY ts.day_of_week, ts.period_num""", (offering_id,))


def get_offering_schedule(offering_id):
    """获取开课的详细时间安排(可读字符串)"""
    rows = get_offering_schedule_rows(offering_id)
    if not rows:
        return '未安排'

    grouped = {}
    for row in rows:
        day_label = DAY_NAMES.get(row['day_of_week'], '未知')
        if day_label not in grouped:
            grouped[day_label] = {'slots': [], 'classroom': row['classroom_name']}
        grouped[day_label]['slots'].append(
            f"{row['label']}({_format_time(row['start_time'])}-{_format_time(row['end_time'])})"
        )

    parts = []
    for day, info in grouped.items():
        slots_str = ','.join(info['slots'])
        parts.append(f"{day} {slots_str}@{info['classroom']}")

    return '; '.join(parts) if parts else '未安排'


def get_offering_classrooms(offering_id):
    """获取开课使用的教室名称列表"""
    rows = query(
        """SELECT DISTINCT c.name FROM offering_schedules os
           JOIN classrooms c ON os.classroom_id = c.id
           WHERE os.course_offering_id=%s ORDER BY c.name""",
        (offering_id,)
    )
    return ', '.join(r['name'] for r in rows) if rows else ''


def check_classroom_capacity(classroom_id, max_students):
    """检查选课人数上限是否超过教室容量"""
    classroom = query('SELECT name, capacity FROM classrooms WHERE id=%s', (classroom_id,), one=True)
    if not classroom:
        return False, '所选教室不存在'
    if classroom['capacity'] and max_students > classroom['capacity']:
        return False, (
            f'选课人数上限({max_students})超过教室「{classroom["name"]}」容量'
            f'({classroom["capacity"]}人)，请调整人数或更换教室'
        )
    return True, ''


def check_offering_conflicts(offering_id, semester_id, teacher_id, classroom_id, time_slot_ids,
                             include_pending=True):
    """
    检查开课冲突(教师/教室)，返回详细冲突信息
    Returns: {
        teacher_conflict, classroom_conflict, conflicts (list of str),
        teacher_details, classroom_details
    }
    """
    if not time_slot_ids:
        return {
            'teacher_conflict': False, 'classroom_conflict': False,
            'conflicts': [], 'teacher_details': [], 'classroom_details': []
        }

    status_list = ('pending', 'approved', 'published') if include_pending else ('approved', 'published')
    status_placeholders = ','.join(['%s'] * len(status_list))
    slot_tuple = tuple(time_slot_ids)

    teacher_details = query(f"""
        SELECT c.name AS course_name, c.code AS course_code,
               ts.label AS slot_label, ts.day_of_week, ts.period_num,
               CASE ts.day_of_week
                   WHEN 1 THEN '周一' WHEN 2 THEN '周二' WHEN 3 THEN '周三'
                   WHEN 4 THEN '周四' WHEN 5 THEN '周五' WHEN 6 THEN '周六'
                   WHEN 7 THEN '周日' ELSE '未知'
               END AS day_name,
               co.status AS offering_status
        FROM course_offerings co
        JOIN offering_schedules os ON os.course_offering_id = co.id
        JOIN time_slots ts ON os.time_slot_id = ts.id
        JOIN courses c ON co.course_id = c.id
        WHERE co.teacher_id = %s AND co.semester_id = %s
          AND co.status IN ({status_placeholders})
          AND co.id != %s
          AND os.time_slot_id IN %s
        GROUP BY c.name, c.code, ts.label, ts.day_of_week, ts.period_num, co.status
        ORDER BY ts.day_of_week, ts.period_num
    """, (teacher_id, semester_id, *status_list, offering_id, slot_tuple))

    classroom_details = query(f"""
        SELECT c.name AS course_name, c.code AS course_code,
               cl.name AS classroom_name, ts.label AS slot_label,
               ts.day_of_week, ts.period_num,
               CASE ts.day_of_week
                   WHEN 1 THEN '周一' WHEN 2 THEN '周二' WHEN 3 THEN '周三'
                   WHEN 4 THEN '周四' WHEN 5 THEN '周五' WHEN 6 THEN '周六'
                   WHEN 7 THEN '周日' ELSE '未知'
               END AS day_name,
               co.status AS offering_status
        FROM course_offerings co
        JOIN offering_schedules os ON os.course_offering_id = co.id
        JOIN time_slots ts ON os.time_slot_id = ts.id
        JOIN classrooms cl ON os.classroom_id = cl.id
        JOIN courses c ON co.course_id = c.id
        WHERE co.semester_id = %s
          AND co.status IN ({status_placeholders})
          AND co.id != %s
          AND os.classroom_id = %s
          AND os.time_slot_id IN %s
        GROUP BY c.name, c.code, cl.name, ts.label, ts.day_of_week, ts.period_num, co.status
        ORDER BY ts.day_of_week, ts.period_num
    """, (semester_id, *status_list, offering_id, classroom_id, slot_tuple))

    conflicts = []
    status_map = {
        'pending': '待审核', 'approved': '已通过', 'published': '已发布'
    }

    for row in teacher_details:
        st = status_map.get(row['offering_status'], row['offering_status'])
        conflicts.append(
            f"教师时间冲突：{row['day_name']}{row['slot_label']} 已有「{row['course_name']}」({st})"
        )

    for row in classroom_details:
        st = status_map.get(row['offering_status'], row['offering_status'])
        conflicts.append(
            f"教室冲突：{row['classroom_name']} {row['day_name']}{row['slot_label']} "
            f"已被「{row['course_name']}」占用({st})"
        )

    return {
        'teacher_conflict': len(teacher_details) > 0,
        'classroom_conflict': len(classroom_details) > 0,
        'conflicts': conflicts,
        'teacher_details': teacher_details,
        'classroom_details': classroom_details,
    }


def save_offering_schedules(offering_id, time_slot_ids, classroom_id):
    """保存开课时间安排（先删后插）"""
    execute('DELETE FROM offering_schedules WHERE course_offering_id=%s', (offering_id,))
    for slot_id in time_slot_ids:
        execute(
            """INSERT INTO offering_schedules (course_offering_id, time_slot_id, classroom_id)
               VALUES (%s,%s,%s)""",
            (offering_id, slot_id, classroom_id)
        )


def get_student_schedule_grid(student_id, semester_id=None):
    """获取学生课表网格数据"""
    where_semester = ''
    args = [student_id]
    if semester_id:
        where_semester = ' AND co.semester_id = %s'
        args.append(semester_id)

    slots = query(f"""
        SELECT e.course_offering_id AS offering_id, c.name AS course_name, c.code AS course_code,
               c.credit, t.name AS teacher_name, sem.name AS semester_name,
               ts.day_of_week, ts.period_num, ts.label AS slot_label,
               ts.start_time, ts.end_time, cl.name AS classroom_name, e.enrolled_at
        FROM enrollments e
        JOIN course_offerings co ON e.course_offering_id = co.id
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters sem ON co.semester_id = sem.id
        JOIN offering_schedules os ON os.course_offering_id = co.id
        JOIN time_slots ts ON os.time_slot_id = ts.id
        JOIN classrooms cl ON os.classroom_id = cl.id
        WHERE e.student_id = %s AND e.status = 'enrolled' {where_semester}
        ORDER BY ts.day_of_week, ts.period_num, c.name
    """, tuple(args))

    courses = query(f"""
        SELECT co.id AS offering_id, c.name AS course_name, c.code AS course_code, c.credit,
               t.name AS teacher_name, sem.name AS semester_name, e.enrolled_at
        FROM enrollments e
        JOIN course_offerings co ON e.course_offering_id = co.id
        JOIN courses c ON co.course_id = c.id
        JOIN teachers t ON co.teacher_id = t.id
        JOIN semesters sem ON co.semester_id = sem.id
        WHERE e.student_id = %s AND e.status = 'enrolled' {where_semester}
        ORDER BY c.code
    """, tuple(args))

    for course in courses:
        course['schedule'] = get_offering_schedule(course['offering_id'])
        course['classroom'] = get_offering_classrooms(course['offering_id'])

    time_slots = query('SELECT * FROM time_slots ORDER BY day_of_week, period_num')

    return {'grid_slots': slots, 'courses': courses, 'time_slots': time_slots}
