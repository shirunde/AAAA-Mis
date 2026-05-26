-- =====================================================
-- 校园教务选课与成绩管理系统 - 视图定义
-- =====================================================

USE mis_system;

-- -----------------------------------------
-- 1. v_student_schedule - 学生课表视图
-- -----------------------------------------
CREATE OR REPLACE VIEW v_student_schedule AS
SELECT
    e.student_id,
    s.student_no,
    s.name AS student_name,
    co.id AS offering_id,
    c.code AS course_code,
    c.name AS course_name,
    c.credit,
    c.course_type,
    t.name AS teacher_name,
    co.schedule,
    co.classroom,
    sem.name AS semester_name,
    e.status AS enroll_status,
    e.enrolled_at
FROM enrollments e
JOIN students s ON e.student_id = s.id
JOIN course_offerings co ON e.course_offering_id = co.id
JOIN courses c ON co.course_id = c.id
JOIN teachers t ON co.teacher_id = t.id
JOIN semesters sem ON co.semester_id = sem.id
WHERE e.status = 'enrolled';


-- -----------------------------------------
-- 2. v_student_transcript - 学生成绩单视图
-- -----------------------------------------
CREATE OR REPLACE VIEW v_student_transcript AS
SELECT
    s.id AS student_id,
    s.student_no,
    s.name AS student_name,
    m.name AS major_name,
    cl.name AS class_name,
    c.code AS course_code,
    c.name AS course_name,
    c.credit,
    c.course_type,
    g.regular_grade,
    g.exam_grade,
    g.total_grade,
    g.gpa_point,
    g.status AS grade_status,
    sem.name AS semester_name,
    t.name AS teacher_name
FROM enrollments e
JOIN students s ON e.student_id = s.id
LEFT JOIN majors m ON s.major_id = m.id
LEFT JOIN classes cl ON s.class_id = cl.id
JOIN grades g ON g.enrollment_id = e.id
JOIN course_offerings co ON e.course_offering_id = co.id
JOIN courses c ON co.course_id = c.id
JOIN semesters sem ON co.semester_id = sem.id
LEFT JOIN teachers t ON co.teacher_id = t.id
WHERE e.status = 'enrolled'
  AND g.status != 'draft';


-- -----------------------------------------
-- 3. v_course_selection_stats - 选课统计视图
-- -----------------------------------------
CREATE OR REPLACE VIEW v_course_selection_stats AS
SELECT
    co.id AS offering_id,
    c.code AS course_code,
    c.name AS course_name,
    c.course_type,
    t.name AS teacher_name,
    sem.name AS semester_name,
    co.max_students,
    COUNT(CASE WHEN e.status = 'enrolled' THEN 1 END) AS enrolled_count,
    ROUND(
        COUNT(CASE WHEN e.status = 'enrolled' THEN 1 END) * 100.0 / co.max_students, 1
    ) AS fill_rate,
    co.status AS offering_status
FROM course_offerings co
JOIN courses c ON co.course_id = c.id
JOIN teachers t ON co.teacher_id = t.id
JOIN semesters sem ON co.semester_id = sem.id
LEFT JOIN enrollments e ON co.id = e.course_offering_id
GROUP BY co.id, c.code, c.name, c.course_type, t.name, sem.name, co.max_students, co.status;


-- -----------------------------------------
-- 4. v_teacher_workload - 教师工作量统计视图
-- -----------------------------------------
CREATE OR REPLACE VIEW v_teacher_workload AS
SELECT
    t.id AS teacher_id,
    t.teacher_no,
    t.name AS teacher_name,
    t.title,
    sem.name AS semester_name,
    COUNT(DISTINCT co.id) AS total_offerings,
    COALESCE(SUM(CASE WHEN e.status = 'enrolled' THEN 1 ELSE 0 END), 0) AS total_students,
    COALESCE(SUM(c.credit), 0) AS total_credits
FROM teachers t
LEFT JOIN course_offerings co ON t.id = co.teacher_id
LEFT JOIN courses c ON co.course_id = c.id
LEFT JOIN semesters sem ON co.semester_id = sem.id
LEFT JOIN enrollments e ON co.id = e.course_offering_id
GROUP BY t.id, t.teacher_no, t.name, t.title, sem.id, sem.name;
