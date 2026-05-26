-- =====================================================
-- 校园教务选课与成绩管理系统 - 存储过程 & 触发器
-- =====================================================

USE mis_system;

DELIMITER //

-- =====================================================
-- 1. sp_enroll_course - 选课存储过程
-- 参数: p_student_id - 学生ID, p_offering_id - 开课ID
-- 包含: 选课窗口检查、时间冲突检测、容量检查、事务控制
-- =====================================================
CREATE PROCEDURE sp_enroll_course(
    IN p_student_id INT,
    IN p_offering_id INT,
    OUT p_result INT,       -- 0=成功, 1=不在选课窗口, 2=时间冲突, 3=已满, 4=已选过
    OUT p_message VARCHAR(200)
)
BEGIN
    DECLARE v_semester_id INT;
    DECLARE v_schedule VARCHAR(200);
    DECLARE v_max_students INT;
    DECLARE v_current_count INT;
    DECLARE v_conflict_count INT;
    DECLARE v_already_enrolled INT DEFAULT 0;
    DECLARE v_in_period INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_result = 99;
        SET p_message = '系统错误，选课失败';
    END;

    START TRANSACTION;

    -- 获取开课信息
    SELECT semester_id, schedule, max_students
      INTO v_semester_id, v_schedule, v_max_students
      FROM course_offerings
     WHERE id = p_offering_id AND status = 'published';

    IF v_semester_id IS NULL THEN
        ROLLBACK;
        SET p_result = 5;
        SET p_message = '该课程未发布，无法选课';
    END IF;

    -- 检查是否在选课窗口期内
    SELECT COUNT(*) INTO v_in_period
      FROM course_selection_periods
     WHERE semester_id = v_semester_id
       AND period_type = 'selection'
       AND is_active = 1
       AND NOW() BETWEEN start_time AND end_time;

    IF v_in_period = 0 THEN
        ROLLBACK;
        SET p_result = 1;
        SET p_message = '当前不在选课窗口期内';
    END IF;

    -- 检查是否已经选过
    SELECT COUNT(*) INTO v_already_enrolled
      FROM enrollments
     WHERE student_id = p_student_id
       AND course_offering_id = p_offering_id
       AND status = 'enrolled';

    IF v_already_enrolled > 0 THEN
        ROLLBACK;
        SET p_result = 4;
        SET p_message = '已选过该课程，无需重复选课';
    END IF;

    -- 检查时间冲突（同一学生已选课程中是否有时间重叠）
    SELECT COUNT(*) INTO v_conflict_count
      FROM enrollments e
      JOIN course_offerings co ON e.course_offering_id = co.id
     WHERE e.student_id = p_student_id
       AND e.status = 'enrolled'
       AND co.semester_id = v_semester_id
       AND co.schedule = v_schedule
       AND v_schedule IS NOT NULL
       AND v_schedule != '';

    IF v_conflict_count > 0 THEN
        ROLLBACK;
        SET p_result = 2;
        SET p_message = CONCAT('上课时间冲突：', v_schedule);
    END IF;

    -- 检查容量
    SELECT COUNT(*) INTO v_current_count
      FROM enrollments
     WHERE course_offering_id = p_offering_id
       AND status = 'enrolled';

    IF v_current_count >= v_max_students THEN
        ROLLBACK;
        SET p_result = 3;
        SET p_message = '该课程选课人数已满';
    END IF;

    -- 执行选课
    INSERT INTO enrollments (student_id, course_offering_id, status, enrolled_at)
    VALUES (p_student_id, p_offering_id, 'enrolled', NOW());

    COMMIT;
    SET p_result = 0;
    SET p_message = '选课成功';
END //


-- =====================================================
-- 2. sp_drop_course - 退课存储过程
-- =====================================================
CREATE PROCEDURE sp_drop_course(
    IN p_student_id INT,
    IN p_offering_id INT,
    OUT p_result INT,       -- 0=成功, 1=不在退课窗口, 2=已退选
    OUT p_message VARCHAR(200)
)
BEGIN
    DECLARE v_enrollment_id INT DEFAULT NULL;
    DECLARE v_semester_id INT;
    DECLARE v_in_period INT DEFAULT 0;
    DECLARE v_grade_status VARCHAR(20);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_result = 99;
        SET p_message = '系统错误，退课失败';
    END;

    START TRANSACTION;

    -- 查找选课记录
    SELECT e.id, co.semester_id
      INTO v_enrollment_id, v_semester_id
      FROM enrollments e
      JOIN course_offerings co ON e.course_offering_id = co.id
     WHERE e.student_id = p_student_id
       AND e.course_offering_id = p_offering_id
       AND e.status = 'enrolled';

    IF v_enrollment_id IS NULL THEN
        ROLLBACK;
        SET p_result = 2;
        SET p_message = '未选该课程或已退选';
    END IF;

    -- 检查是否已有成绩录入
    SELECT status INTO v_grade_status
      FROM grades
     WHERE enrollment_id = v_enrollment_id;

    IF v_grade_status IS NOT NULL AND v_grade_status != 'draft' THEN
        ROLLBACK;
        SET p_result = 3;
        SET p_message = '该课程已有成绩记录，无法退课';
    END IF;

    -- 检查是否在退课窗口期内
    SELECT COUNT(*) INTO v_in_period
      FROM course_selection_periods
     WHERE semester_id = v_semester_id
       AND period_type = 'drop'
       AND is_active = 1
       AND NOW() BETWEEN start_time AND end_time;

    IF v_in_period = 0 THEN
        ROLLBACK;
        SET p_result = 1;
        SET p_message = '当前不在退课窗口期内';
    END IF;

    -- 执行退课
    UPDATE enrollments
       SET status = 'dropped', dropped_at = NOW()
     WHERE id = v_enrollment_id;

    -- 删除对应的草稿成绩记录
    DELETE FROM grades
     WHERE enrollment_id = v_enrollment_id
       AND status = 'draft';

    COMMIT;
    SET p_result = 0;
    SET p_message = '退课成功';
END //


-- =====================================================
-- 3. sp_calculate_total_grade - 计算总评成绩
-- 平时成绩30% + 期末成绩70%
-- =====================================================
CREATE PROCEDURE sp_calculate_total_grade(
    IN p_enrollment_id INT
)
BEGIN
    DECLARE v_regular DECIMAL(5,2);
    DECLARE v_exam DECIMAL(5,2);
    DECLARE v_total DECIMAL(5,2);
    DECLARE v_gpa DECIMAL(3,1);

    SELECT regular_grade, exam_grade
      INTO v_regular, v_exam
      FROM grades
     WHERE enrollment_id = p_enrollment_id;

    IF v_regular IS NOT NULL AND v_exam IS NOT NULL THEN
        SET v_total = ROUND(v_regular * 0.3 + v_exam * 0.7, 2);

        -- 计算绩点 (4.0制)
        IF v_total >= 90 THEN SET v_gpa = 4.0;
        ELSEIF v_total >= 85 THEN SET v_gpa = 3.7;
        ELSEIF v_total >= 82 THEN SET v_gpa = 3.3;
        ELSEIF v_total >= 78 THEN SET v_gpa = 3.0;
        ELSEIF v_total >= 75 THEN SET v_gpa = 2.7;
        ELSEIF v_total >= 72 THEN SET v_gpa = 2.3;
        ELSEIF v_total >= 68 THEN SET v_gpa = 2.0;
        ELSEIF v_total >= 64 THEN SET v_gpa = 1.5;
        ELSEIF v_total >= 60 THEN SET v_gpa = 1.0;
        ELSE SET v_gpa = 0.0;
        END IF;

        UPDATE grades
           SET total_grade = v_total,
               gpa_point = v_gpa
         WHERE enrollment_id = p_enrollment_id;
    END IF;
END //


-- =====================================================
-- 4. sp_calculate_gpa - 计算学期GPA
-- =====================================================
CREATE PROCEDURE sp_calculate_gpa(
    IN p_student_id INT,
    IN p_semester_id INT,
    OUT p_gpa DECIMAL(4,2),
    OUT p_total_credits DECIMAL(5,1),
    OUT p_message VARCHAR(200)
)
BEGIN
    DECLARE v_weighted_sum DECIMAL(10,2) DEFAULT 0;
    DECLARE v_total_credits DECIMAL(5,1) DEFAULT 0;

    SELECT COALESCE(SUM(g.gpa_point * c.credit), 0),
           COALESCE(SUM(c.credit), 0)
      INTO v_weighted_sum, v_total_credits
      FROM grades g
      JOIN enrollments e ON g.enrollment_id = e.id
      JOIN course_offerings co ON e.course_offering_id = co.id
      JOIN courses c ON co.course_id = c.id
     WHERE e.student_id = p_student_id
       AND co.semester_id = p_semester_id
       AND e.status = 'enrolled'
       AND g.status IN ('approved', 'published')
       AND g.gpa_point IS NOT NULL;

    IF v_total_credits > 0 THEN
        SET p_gpa = ROUND(v_weighted_sum / v_total_credits, 2);
    ELSE
        SET p_gpa = 0;
    END IF;

    SET p_total_credits = v_total_credits;
    SET p_message = 'GPA计算完成';
END //


-- =====================================================
-- 5. sp_approve_course_offering - 审核开课申请
-- =====================================================
CREATE PROCEDURE sp_approve_course_offering(
    IN p_offering_id INT,
    IN p_admin_id INT,
    IN p_action ENUM('approved', 'rejected'),
    IN p_comment TEXT,
    OUT p_result INT,
    OUT p_message VARCHAR(200)
)
BEGIN
    DECLARE v_status VARCHAR(20);

    SELECT status INTO v_status
      FROM course_offerings
     WHERE id = p_offering_id;

    IF v_status IS NULL THEN
        SET p_result = 1;
        SET p_message = '开课记录不存在';
    ELSEIF v_status != 'pending' THEN
        SET p_result = 2;
        SET p_message = '该申请已审核过，不可重复审核';
    ELSE
        UPDATE course_offerings
           SET status = p_action,
               review_comment = p_comment,
               reviewed_at = NOW()
         WHERE id = p_offering_id;

        -- 记录日志
        INSERT INTO system_logs (user_id, action, target_type, target_id, detail)
        VALUES (p_admin_id,
                CONCAT('course_offering_', p_action),
                'course_offering',
                p_offering_id,
                CONCAT('审核意见: ', p_comment));

        SET p_result = 0;
        SET p_message = CONCAT('开课申请已', CASE p_action WHEN 'approved' THEN '通过' ELSE '驳回' END);
    END IF;
END //


-- =====================================================
-- 触发器
-- =====================================================

-- trg_after_enrollment: 选课时自动创建成绩记录
CREATE TRIGGER trg_after_enrollment_insert
AFTER INSERT ON enrollments
FOR EACH ROW
BEGIN
    IF NEW.status = 'enrolled' THEN
        INSERT INTO grades (enrollment_id, status)
        VALUES (NEW.id, 'draft');
    END IF;
END //


-- trg_after_grade_update: 成绩更新时自动计算总评
CREATE TRIGGER trg_after_grade_update
BEFORE UPDATE ON grades
FOR EACH ROW
BEGIN
    IF (NEW.regular_grade IS NOT NULL AND NEW.exam_grade IS NOT NULL)
       AND (NEW.regular_grade != OLD.regular_grade OR NEW.exam_grade != OLD.exam_grade) THEN
        SET NEW.total_grade = ROUND(NEW.regular_grade * 0.3 + NEW.exam_grade * 0.7, 2);

        -- GPA绩点计算
        IF NEW.total_grade >= 90 THEN SET NEW.gpa_point = 4.0;
        ELSEIF NEW.total_grade >= 85 THEN SET NEW.gpa_point = 3.7;
        ELSEIF NEW.total_grade >= 82 THEN SET NEW.gpa_point = 3.3;
        ELSEIF NEW.total_grade >= 78 THEN SET NEW.gpa_point = 3.0;
        ELSEIF NEW.total_grade >= 75 THEN SET NEW.gpa_point = 2.7;
        ELSEIF NEW.total_grade >= 72 THEN SET NEW.gpa_point = 2.3;
        ELSEIF NEW.total_grade >= 68 THEN SET NEW.gpa_point = 2.0;
        ELSEIF NEW.total_grade >= 64 THEN SET NEW.gpa_point = 1.5;
        ELSEIF NEW.total_grade >= 60 THEN SET NEW.gpa_point = 1.0;
        ELSE SET NEW.gpa_point = 0.0;
        END IF;
    END IF;
END //


-- trg_course_offering_status: 开课状态变更时记录日志
CREATE TRIGGER trg_course_offering_status_change
AFTER UPDATE ON course_offerings
FOR EACH ROW
BEGIN
    IF NEW.status != OLD.status THEN
        INSERT INTO system_logs (user_id, action, target_type, target_id, detail)
        VALUES (NULL,
                'course_offering_status_changed',
                'course_offering',
                NEW.id,
                CONCAT('状态变更: ', OLD.status, ' -> ', NEW.status));
    END IF;
END //

DELIMITER ;
