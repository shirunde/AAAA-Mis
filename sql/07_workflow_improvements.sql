-- =====================================================
-- 开课/审核/选课流程改进
-- 执行: mysql -u root -p mis_system < sql/07_workflow_improvements.sql
-- =====================================================

USE mis_system;

-- 1. 扩展开课状态：支持停开
ALTER TABLE course_offerings
    MODIFY COLUMN status ENUM('pending', 'approved', 'rejected', 'published', 'cancelled')
    NOT NULL DEFAULT 'pending';

-- 2. 站内通知表
CREATE TABLE IF NOT EXISTS notifications (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    user_id     INT             NOT NULL,
    title       VARCHAR(100)    NOT NULL,
    content     TEXT            NOT NULL,
    ntype       VARCHAR(30)     NOT NULL DEFAULT 'info',
    ref_type    VARCHAR(30)     NULL,
    ref_id      INT             NULL,
    is_read     TINYINT(1)      NOT NULL DEFAULT 0,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_notify_user (user_id, is_read),
    CONSTRAINT fk_notify_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. 学生课表视图（基于 offering_schedules）
CREATE OR REPLACE VIEW v_student_schedule AS
SELECT
    e.student_id,
    s.student_no,
    s.name AS student_name,
    co.id AS offering_id,
    co.semester_id,
    c.code AS course_code,
    c.name AS course_name,
    c.credit,
    c.course_type,
    c.description AS course_description,
    t.name AS teacher_name,
    sem.name AS semester_name,
    e.status AS enroll_status,
    e.enrolled_at,
    GROUP_CONCAT(
        DISTINCT CONCAT(
            CASE ts.day_of_week
                WHEN 1 THEN '周一' WHEN 2 THEN '周二' WHEN 3 THEN '周三'
                WHEN 4 THEN '周四' WHEN 5 THEN '周五' WHEN 6 THEN '周六'
                WHEN 7 THEN '周日' ELSE '未知'
            END,
            ' ', ts.label, '(', TIME_FORMAT(ts.start_time, '%H:%i'), '-', TIME_FORMAT(ts.end_time, '%H:%i'), ')',
            '@', cl.name
        )
        ORDER BY ts.day_of_week, ts.period_num
        SEPARATOR '; '
    ) AS schedule,
    GROUP_CONCAT(DISTINCT cl.name ORDER BY cl.name SEPARATOR ', ') AS classroom
FROM enrollments e
JOIN students s ON e.student_id = s.id
JOIN course_offerings co ON e.course_offering_id = co.id
JOIN courses c ON co.course_id = c.id
JOIN teachers t ON co.teacher_id = t.id
JOIN semesters sem ON co.semester_id = sem.id
LEFT JOIN offering_schedules os ON os.course_offering_id = co.id
LEFT JOIN time_slots ts ON os.time_slot_id = ts.id
LEFT JOIN classrooms cl ON os.classroom_id = cl.id
WHERE e.status = 'enrolled'
GROUP BY e.student_id, s.student_no, s.name, co.id, co.semester_id,
         c.code, c.name, c.credit, c.course_type, c.description,
         t.name, sem.name, e.status, e.enrolled_at;

-- 4. 更新存储过程
DROP PROCEDURE IF EXISTS sp_enroll_course;
DROP PROCEDURE IF EXISTS sp_approve_course_offering;
DROP PROCEDURE IF EXISTS sp_publish_course_offering;
DROP PROCEDURE IF EXISTS sp_unpublish_course_offering;
DROP PROCEDURE IF EXISTS sp_cancel_course_offering;

DELIMITER //

CREATE PROCEDURE sp_enroll_course(
    IN p_student_id INT,
    IN p_offering_id INT,
    OUT p_result INT,
    OUT p_message VARCHAR(200)
)
main_block: BEGIN
    DECLARE v_semester_id INT;
    DECLARE v_max_students INT;
    DECLARE v_current_count INT;
    DECLARE v_existing_id INT;
    DECLARE v_conflict_course VARCHAR(100);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_result = 99;
        SET p_message = '系统错误，选课失败';
    END;

    START TRANSACTION;

    SELECT semester_id, max_students
      INTO v_semester_id, v_max_students
      FROM course_offerings
     WHERE id = p_offering_id AND status = 'published'
       FOR UPDATE;

    IF v_semester_id IS NULL THEN
        SET p_result = 5;
        SET p_message = '该课程未发布或已停开，无法选课';
        ROLLBACK;
        LEAVE main_block;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM course_selection_periods
         WHERE semester_id = v_semester_id
           AND period_type = 'selection'
           AND is_active = 1
           AND NOW() BETWEEN start_time AND end_time
    ) THEN
        SET p_result = 1;
        SET p_message = '当前不在选课窗口期内';
        ROLLBACK;
        LEAVE main_block;
    END IF;

    IF EXISTS (
        SELECT 1 FROM enrollments
         WHERE student_id = p_student_id
           AND course_offering_id = p_offering_id
           AND status = 'enrolled'
    ) THEN
        SET p_result = 4;
        SET p_message = '已选过该课程，无需重复选课';
        ROLLBACK;
        LEAVE main_block;
    END IF;

    SELECT c.name INTO v_conflict_course
      FROM enrollments e
      JOIN course_offerings co ON e.course_offering_id = co.id
      JOIN courses c ON co.course_id = c.id
      JOIN offering_schedules os_new ON os_new.course_offering_id = p_offering_id
      JOIN offering_schedules os_exist ON os_exist.course_offering_id = co.id
     WHERE e.student_id = p_student_id
       AND e.status = 'enrolled'
       AND co.semester_id = v_semester_id
       AND os_new.time_slot_id = os_exist.time_slot_id
     LIMIT 1;

    IF v_conflict_course IS NOT NULL THEN
        SET p_result = 2;
        SET p_message = CONCAT('时间冲突：与已选课程「', v_conflict_course, '」上课时间重叠');
        ROLLBACK;
        LEAVE main_block;
    END IF;

    SELECT COUNT(*) INTO v_current_count
      FROM enrollments
     WHERE course_offering_id = p_offering_id
       AND status = 'enrolled';

    IF v_current_count >= v_max_students THEN
        SET p_result = 3;
        SET p_message = '该课程选课人数已满';
        ROLLBACK;
        LEAVE main_block;
    END IF;

    SELECT id INTO v_existing_id
      FROM enrollments
     WHERE student_id = p_student_id
       AND course_offering_id = p_offering_id
       AND status = 'dropped'
     LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
        UPDATE enrollments
           SET status = 'enrolled', enrolled_at = NOW(), dropped_at = NULL
         WHERE id = v_existing_id;
        IF NOT EXISTS (SELECT 1 FROM grades WHERE enrollment_id = v_existing_id) THEN
            INSERT INTO grades (enrollment_id, status) VALUES (v_existing_id, 'draft');
        END IF;
    ELSE
        INSERT INTO enrollments (student_id, course_offering_id, status, enrolled_at)
        VALUES (p_student_id, p_offering_id, 'enrolled', NOW());
    END IF;

    COMMIT;
    SET p_result = 0;
    SET p_message = '选课成功';
END main_block //


CREATE PROCEDURE sp_approve_course_offering(
    IN p_offering_id INT,
    IN p_admin_id INT,
    IN p_action ENUM('approved', 'rejected'),
    IN p_comment TEXT,
    OUT p_result INT,
    OUT p_message VARCHAR(200)
)
main_block: BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_conflict_course VARCHAR(100);
    DECLARE v_conflict_classroom VARCHAR(50);

    SELECT status INTO v_status
      FROM course_offerings
     WHERE id = p_offering_id;

    IF v_status IS NULL THEN
        SET p_result = 1;
        SET p_message = '开课记录不存在';
        LEAVE main_block;
    ELSEIF v_status != 'pending' THEN
        SET p_result = 2;
        SET p_message = '该申请已审核过，不可重复审核';
        LEAVE main_block;
    ELSEIF p_action = 'rejected' AND (p_comment IS NULL OR TRIM(p_comment) = '') THEN
        SET p_result = 5;
        SET p_message = '驳回时必须填写审核意见';
        LEAVE main_block;
    ELSE
        IF p_action = 'approved' THEN
            SELECT c.name INTO v_conflict_course
              FROM course_offerings co_existing
              JOIN offering_schedules os_new ON os_new.course_offering_id = p_offering_id
              JOIN offering_schedules os_exist ON os_exist.course_offering_id = co_existing.id
              JOIN courses c ON co_existing.course_id = c.id
             WHERE co_existing.teacher_id = (SELECT teacher_id FROM course_offerings WHERE id = p_offering_id)
               AND co_existing.semester_id = (SELECT semester_id FROM course_offerings WHERE id = p_offering_id)
               AND co_existing.status IN ('pending', 'approved', 'published')
               AND co_existing.id != p_offering_id
               AND os_new.time_slot_id = os_exist.time_slot_id
             LIMIT 1;

            IF v_conflict_course IS NOT NULL THEN
                SET p_result = 3;
                SET p_message = CONCAT('教师时间冲突：与「', v_conflict_course, '」上课时间重叠');
                LEAVE main_block;
            END IF;

            SELECT CONCAT(c.name, '@', cl.name) INTO v_conflict_classroom
              FROM course_offerings co_existing
              JOIN offering_schedules os_new ON os_new.course_offering_id = p_offering_id
              JOIN offering_schedules os_exist ON os_exist.course_offering_id = co_existing.id
              JOIN classrooms cl ON os_exist.classroom_id = cl.id
              JOIN courses c ON co_existing.course_id = c.id
             WHERE co_existing.semester_id = (SELECT semester_id FROM course_offerings WHERE id = p_offering_id)
               AND co_existing.status IN ('pending', 'approved', 'published')
               AND co_existing.id != p_offering_id
               AND os_new.classroom_id = os_exist.classroom_id
               AND os_new.time_slot_id = os_exist.time_slot_id
             LIMIT 1;

            IF v_conflict_classroom IS NOT NULL THEN
                SET p_result = 4;
                SET p_message = CONCAT('教室时间冲突：', v_conflict_classroom, ' 已被占用');
                LEAVE main_block;
            END IF;
        END IF;

        UPDATE course_offerings
           SET status = p_action,
               review_comment = p_comment,
               reviewed_at = NOW()
         WHERE id = p_offering_id;

        INSERT INTO system_logs (user_id, action, target_type, target_id, detail)
        VALUES (p_admin_id,
                CONCAT('course_offering_', p_action),
                'course_offering',
                p_offering_id,
                CONCAT('审核意见: ', IFNULL(p_comment, '')));

        SET p_result = 0;
        SET p_message = CONCAT('开课申请已', CASE p_action WHEN 'approved' THEN '通过' ELSE '驳回' END);
    END IF;
END main_block //


CREATE PROCEDURE sp_publish_course_offering(
    IN p_offering_id INT,
    IN p_admin_id INT,
    OUT p_result INT,
    OUT p_message VARCHAR(200)
)
main_block: BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_semester_id INT;

    SELECT status, semester_id INTO v_status, v_semester_id
      FROM course_offerings WHERE id = p_offering_id;

    IF v_status IS NULL THEN
        SET p_result = 1;
        SET p_message = '开课记录不存在';
    ELSEIF v_status != 'approved' THEN
        SET p_result = 2;
        SET p_message = '只有已通过审核的课程才能发布';
    ELSEIF NOT EXISTS (
        SELECT 1 FROM offering_schedules WHERE course_offering_id = p_offering_id
    ) THEN
        SET p_result = 3;
        SET p_message = '未安排上课时间地点，无法发布';
    ELSE
        UPDATE course_offerings SET status = 'published' WHERE id = p_offering_id;

        INSERT INTO system_logs (user_id, action, target_type, target_id, detail)
        VALUES (p_admin_id, 'course_offering_published', 'course_offering', p_offering_id, '课程已发布供学生选课');

        SET p_result = 0;
        SET p_message = '课程已发布，学生可在选课窗口内选课';
    END IF;
END main_block //


CREATE PROCEDURE sp_unpublish_course_offering(
    IN p_offering_id INT,
    IN p_admin_id INT,
    IN p_reason TEXT,
    OUT p_result INT,
    OUT p_message VARCHAR(200)
)
main_block: BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_enrolled_count INT;

    SELECT status INTO v_status FROM course_offerings WHERE id = p_offering_id;

    IF v_status IS NULL THEN
        SET p_result = 1;
        SET p_message = '开课记录不存在';
    ELSEIF v_status != 'published' THEN
        SET p_result = 2;
        SET p_message = '只有已发布的课程才能撤销发布';
    ELSE
        SELECT COUNT(*) INTO v_enrolled_count
          FROM enrollments
         WHERE course_offering_id = p_offering_id AND status = 'enrolled';

        IF v_enrolled_count > 0 THEN
            SET p_result = 3;
            SET p_message = CONCAT('已有 ', v_enrolled_count, ' 名学生选课，请使用「停开课程」而非撤销发布');
        ELSE
            UPDATE course_offerings
               SET status = 'approved',
                   review_comment = CONCAT(IFNULL(review_comment, ''), '\n[撤销发布] ', IFNULL(p_reason, ''))
             WHERE id = p_offering_id;

            INSERT INTO system_logs (user_id, action, target_type, target_id, detail)
            VALUES (p_admin_id, 'course_offering_unpublished', 'course_offering', p_offering_id,
                    CONCAT('撤销发布: ', IFNULL(p_reason, '')));

            SET p_result = 0;
            SET p_message = '已撤销发布，课程恢复为「已通过」状态';
        END IF;
    END IF;
END main_block //


CREATE PROCEDURE sp_cancel_course_offering(
    IN p_offering_id INT,
    IN p_admin_id INT,
    IN p_reason TEXT,
    OUT p_result INT,
    OUT p_message VARCHAR(200)
)
main_block: BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_dropped_count INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_result = 99;
        SET p_message = '系统错误，停开失败';
    END;

    SELECT status INTO v_status FROM course_offerings WHERE id = p_offering_id;

    IF v_status IS NULL THEN
        SET p_result = 1;
        SET p_message = '开课记录不存在';
        LEAVE main_block;
    ELSEIF v_status NOT IN ('approved', 'published') THEN
        SET p_result = 2;
        SET p_message = '只能停开已通过或已发布的课程';
    ELSEIF p_reason IS NULL OR TRIM(p_reason) = '' THEN
        SET p_result = 4;
        SET p_message = '停开课程必须填写原因';
        LEAVE main_block;
    END IF;

    START TRANSACTION;

    UPDATE enrollments e
      JOIN grades g ON g.enrollment_id = e.id AND g.status = 'draft'
       SET e.status = 'dropped', e.dropped_at = NOW()
     WHERE e.course_offering_id = p_offering_id AND e.status = 'enrolled';
    SET v_dropped_count = ROW_COUNT();

    DELETE g FROM grades g
      JOIN enrollments e ON g.enrollment_id = e.id
     WHERE e.course_offering_id = p_offering_id AND e.status = 'dropped' AND g.status = 'draft';

    UPDATE course_offerings
       SET status = 'cancelled',
           review_comment = CONCAT(IFNULL(review_comment, ''), '\n[停开] ', p_reason)
     WHERE id = p_offering_id;

    INSERT INTO system_logs (user_id, action, target_type, target_id, detail)
    VALUES (p_admin_id, 'course_offering_cancelled', 'course_offering', p_offering_id,
            CONCAT('停开课程，退选', v_dropped_count, '人。原因: ', p_reason));

    COMMIT;
    SET p_result = 0;
    SET p_message = CONCAT('课程已停开，已自动退选 ', v_dropped_count, ' 名学生');
END main_block //

DELIMITER ;
