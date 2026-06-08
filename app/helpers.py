"""公共辅助工具"""
import re

from flask import request
from flask_login import current_user
from app.db import get_conn, query


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


def parse_schedule_slots(schedule_str):
    """
    将课表字符串解析为标准化的时间槽集合。
    例: "周一1-2节" -> {('周一','1-2')}
        "周一第1-2节" -> {('周一','1-2')}
        "周一3-4节;周三1-2节" -> {('周一','3-4'), ('周三','1-2')}
    返回 set of (day, period) 元组
    """
    if not schedule_str:
        return set()

    DAY_MAP = {
        '一': '周一', '二': '周二', '三': '周三', '四': '周四', '五': '周五',
        '1': '周一', '2': '周二', '3': '周三', '4': '周四', '5': '周五',
    }

    slots = set()
    # 支持分号/逗号分隔的多段
    parts = re.split(r'[;,，；]', schedule_str)
    for part in parts:
        part = part.strip()
        # 匹配: 周X / 星期X + (第)?N-N(节)?
        m = re.match(
            r'(?:周|星期)([一二三四五1-5])\s*(?:第)?\s*(\d+)\s*[-\-~]\s*(\d+)',
            part
        )
        if m:
            day_key = m.group(1)
            start = int(m.group(2))
            end = int(m.group(3))
            day = DAY_MAP.get(day_key, f'周{day_key}')
            # 归并到标准时段: 1-2, 3-4, 5-6, 7-8
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
             AND end_time >= NOW()
           ORDER BY start_time""",
        (semester_id,)
    )


def get_offering_schedule(offering_id):
    """获取开课的详细时间安排(用于展示)
    Returns: 可读的时间安排字符串,如 "周一 第1节(08:00-10:00),第2节(10:00-12:00)@逸夫楼101; 周三 第3节(14:00-16:00)@实验楼201"
    """
    rows = query("""SELECT ts.day_of_week, ts.period_num, ts.start_time, ts.end_time, ts.label,
                           c.code AS classroom_code, c.name AS classroom_name
                    FROM offering_schedules os
                    JOIN time_slots ts ON os.time_slot_id = ts.id
                    JOIN classrooms c ON os.classroom_id = c.id
                    WHERE os.course_offering_id = %s
                    ORDER BY ts.day_of_week, ts.period_num""", (offering_id,))

    if not rows:
        return '未安排'

    # 按天分组
    days_map = {1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日'}
    grouped = {}
    for row in rows:
        day_label = days_map.get(row['day_of_week'], '未知')
        if day_label not in grouped:
            grouped[day_label] = {'slots': [], 'classroom': row['classroom_name']}
        grouped[day_label]['slots'].append(f"{row['label']}({row['start_time'].strftime('%H:%M') if hasattr(row['start_time'], 'strftime') else str(row['start_time'])[:5]}-{row['end_time'].strftime('%H:%M') if hasattr(row['end_time'], 'strftime') else str(row['end_time'])[:5]})")

    # 生成可读字符串
    parts = []
    for day, info in grouped.items():
        slots_str = ','.join(info['slots'])
        parts.append(f"{day} {slots_str}@{info['classroom']}")

    return '; '.join(parts) if parts else '未安排'


def check_offering_conflicts(offering_id, semester_id, teacher_id, classroom_id, time_slot_ids):
    """检查开课冲突(教师/教室)
    Returns: {'teacher_conflict': bool, 'classroom_conflict': bool, 'conflicts': [...]}
    """
    conflicts = []

    # 检查教师冲突
    teacher_conflict = query("""
        SELECT c.name AS course_name, ts.label, ts.day_of_week
        FROM course_offerings co
        JOIN offering_schedules os ON os.course_offering_id = co.id
        JOIN time_slots ts ON os.time_slot_id = ts.id
        JOIN courses c ON co.course_id = c.id
        WHERE co.teacher_id = %s AND co.semester_id = %s
          AND co.status IN ('approved', 'published')
          AND co.id != %s
          AND os.time_slot_id IN %s
    """, (teacher_id, semester_id, offering_id, tuple(time_slot_ids)))

    if teacher_conflict:
        conflicts.append(f"教师时间冲突: {len(teacher_conflict)}个时间段已有课程")

    # 检查教室冲突
    classroom_conflict = query("""
        SELECT c.name AS course_name, ts.label, cl.name AS classroom_name
        FROM course_offerings co
        JOIN offering_schedules os ON os.course_offering_id = co.id
        JOIN time_slots ts ON os.time_slot_id = ts.id
        JOIN classrooms cl ON os.classroom_id = cl.id
        JOIN courses c ON co.course_id = c.id
        WHERE co.semester_id = %s AND co.status IN ('approved', 'published')
          AND co.id != %s
          AND os.classroom_id = %s
          AND os.time_slot_id IN %s
    """, (semester_id, offering_id, classroom_id, tuple(time_slot_ids)))

    if classroom_conflict:
        conflicts.append(f"教室冲突: {len(classroom_conflict)}个时间段教室已被占用")

    return {
        'teacher_conflict': len(teacher_conflict) > 0,
        'classroom_conflict': len(classroom_conflict) > 0,
        'conflicts': conflicts
    }
