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
