"""执行 sql/07_workflow_improvements.sql"""
import re
import pymysql
from config import Config


def main():
    c = Config()
    conn = pymysql.connect(
        host=c.DB_HOST, port=c.DB_PORT, user=c.DB_USER,
        password=c.DB_PASSWORD, database=c.DB_NAME, charset='utf8mb4',
    )
    cur = conn.cursor()

    with open('sql/07_workflow_improvements.sql', 'r', encoding='utf-8') as f:
        content = f.read()

    # ALTER status enum
    try:
        cur.execute(
            "ALTER TABLE course_offerings MODIFY COLUMN status "
            "ENUM('pending','approved','rejected','published','cancelled') "
            "NOT NULL DEFAULT 'pending'"
        )
        conn.commit()
        print('OK: alter status enum')
    except Exception as e:
        print('alter:', e)

    # notifications table
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(100) NOT NULL,
                content TEXT NOT NULL,
                ntype VARCHAR(30) NOT NULL DEFAULT 'info',
                ref_type VARCHAR(30) NULL,
                ref_id INT NULL,
                is_read TINYINT(1) NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_notify_user (user_id, is_read),
                CONSTRAINT fk_notify_user FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE CASCADE ON UPDATE CASCADE
            ) ENGINE=InnoDB
        """)
        conn.commit()
        print('OK: notifications table')
    except Exception as e:
        print('notifications:', e)

    # view
    view_start = content.find('CREATE OR REPLACE VIEW v_student_schedule AS')
    view_end = content.find('-- 4. 更新存储过程', view_start)
    view_sql = content[view_start:view_end].strip().rstrip(';')
    view_match = view_sql if view_start >= 0 and view_end > view_start else None
    if view_match:
        try:
            cur.execute(view_match)
            conn.commit()
            print('OK: v_student_schedule')
        except Exception as e:
            print('view:', e)

    # procedures
    proc_section = content.split('DELIMITER //')[1].split('DELIMITER ;')[0]
    for proc_name in [
        'sp_enroll_course', 'sp_approve_course_offering',
        'sp_publish_course_offering', 'sp_unpublish_course_offering',
        'sp_cancel_course_offering',
    ]:
        cur.execute(f'DROP PROCEDURE IF EXISTS {proc_name}')
        conn.commit()
        m = re.search(
            rf'CREATE PROCEDURE {proc_name}\([\s\S]+?END main_block //',
            proc_section
        )
        if not m:
            print(f'MISSING: {proc_name}')
            continue
        sql = m.group(0).replace('END main_block //', 'END main_block')
        try:
            cur.execute(sql)
            conn.commit()
            print(f'OK: {proc_name}')
        except Exception as e:
            print(f'{proc_name}:', e)

    conn.close()
    print('Migration complete.')


if __name__ == '__main__':
    main()
