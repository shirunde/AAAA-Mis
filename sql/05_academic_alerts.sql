-- =====================================================
-- 学业预警 / GPA 下滑预测
-- 依赖: 01_schema.sql, 03_procedures.sql, 04_views.sql
-- =====================================================

USE mis_system;

-- -----------------------------------------
-- 1. v_student_cumulative_gpa - 累计学业指标
-- -----------------------------------------
CREATE OR REPLACE VIEW v_student_cumulative_gpa AS
SELECT
    s.id AS student_id,
    s.student_no,
    s.name AS student_name,
    m.name AS major_name,
    cl.name AS class_name,
    ROUND(
        COALESCE(SUM(g.gpa_point * c.credit), 0)
        / NULLIF(SUM(c.credit), 0),
        2
    ) AS cumulative_gpa,
    COALESCE(SUM(c.credit), 0) AS earned_credits,
    SUM(CASE WHEN g.total_grade < 60 THEN 1 ELSE 0 END) AS published_fail_count,
    COUNT(g.id) AS published_course_count
FROM students s
LEFT JOIN majors m ON s.major_id = m.id
LEFT JOIN classes cl ON s.class_id = cl.id
LEFT JOIN enrollments e ON e.student_id = s.id AND e.status = 'enrolled'
LEFT JOIN grades g ON g.enrollment_id = e.id
    AND g.status = 'published'
    AND g.gpa_point IS NOT NULL
LEFT JOIN course_offerings co ON e.course_offering_id = co.id
LEFT JOIN courses c ON co.course_id = c.id
WHERE s.status = 'active'
GROUP BY s.id, s.student_no, s.name, m.name, cl.name;


-- -----------------------------------------
-- 2. v_student_gpa_by_semester - 学期 GPA
-- -----------------------------------------
CREATE OR REPLACE VIEW v_student_gpa_by_semester AS
SELECT
    e.student_id,
    co.semester_id,
    sem.name AS semester_name,
    sem.start_date,
    ROUND(
        SUM(g.gpa_point * c.credit) / NULLIF(SUM(c.credit), 0),
        2
    ) AS semester_gpa,
    SUM(c.credit) AS semester_credits,
    SUM(CASE WHEN g.total_grade < 60 THEN 1 ELSE 0 END) AS fail_count
FROM enrollments e
JOIN course_offerings co ON e.course_offering_id = co.id
JOIN semesters sem ON co.semester_id = sem.id
JOIN courses c ON co.course_id = c.id
JOIN grades g ON g.enrollment_id = e.id
WHERE e.status = 'enrolled'
  AND g.status = 'published'
  AND g.gpa_point IS NOT NULL
GROUP BY e.student_id, co.semester_id, sem.name, sem.start_date;


DELIMITER //

-- -----------------------------------------
-- 3. sp_list_academic_alerts - 学业预警列表
-- p_semester_id: NULL 表示当前学期
-- p_student_id: NULL 表示全部学生，否则仅查指定学生
-- -----------------------------------------
CREATE PROCEDURE sp_list_academic_alerts(
    IN p_semester_id INT,
    IN p_student_id INT
)
BEGIN
    DECLARE v_semester_id INT;

    IF p_semester_id IS NULL THEN
        SELECT id INTO v_semester_id
          FROM semesters
         WHERE is_current = 1
         ORDER BY id DESC
         LIMIT 1;
    ELSE
        SET v_semester_id = p_semester_id;
    END IF;

    WITH current_semester_stats AS (
        SELECT
            e.student_id,
            COUNT(*) AS current_courses,
            SUM(
                CASE
                    WHEN g.regular_grade IS NOT NULL
                     AND g.exam_grade IS NOT NULL
                     AND ROUND(g.regular_grade * 0.3 + g.exam_grade * 0.7, 2) < 60
                    THEN 1 ELSE 0
                END
            ) AS projected_fail_count,
            ROUND(
                SUM(
                    CASE
                        WHEN g.regular_grade IS NOT NULL AND g.exam_grade IS NOT NULL
                        THEN ROUND(g.regular_grade * 0.3 + g.exam_grade * 0.7, 2) * c.credit
                        ELSE 0
                    END
                ) / NULLIF(
                    SUM(
                        CASE
                            WHEN g.regular_grade IS NOT NULL AND g.exam_grade IS NOT NULL
                            THEN c.credit ELSE 0
                        END
                    ),
                    0
                ),
                2
            ) AS projected_semester_gpa,
            SUM(
                CASE
                    WHEN g.status = 'published' AND g.total_grade < 60 THEN 1 ELSE 0
                END
            ) AS current_published_fail_count
        FROM enrollments e
        JOIN course_offerings co ON e.course_offering_id = co.id
        JOIN courses c ON co.course_id = c.id
        LEFT JOIN grades g ON g.enrollment_id = e.id
        WHERE e.status = 'enrolled'
          AND co.semester_id = v_semester_id
        GROUP BY e.student_id
    ),
    semester_ranked AS (
        SELECT
            sg.student_id,
            sg.semester_id,
            sg.semester_gpa,
            sg.start_date,
            ROW_NUMBER() OVER (
                PARTITION BY sg.student_id
                ORDER BY sg.start_date DESC
            ) AS rn
        FROM v_student_gpa_by_semester sg
    ),
    gpa_trend AS (
        SELECT
            cur.student_id,
            cur.semester_gpa AS current_semester_gpa,
            prev.semester_gpa AS previous_semester_gpa,
            ROUND(prev.semester_gpa - cur.semester_gpa, 2) AS gpa_decline
        FROM semester_ranked cur
        LEFT JOIN semester_ranked prev
          ON cur.student_id = prev.student_id
         AND prev.rn = 2
        WHERE cur.rn = 1
    )
    SELECT
        base.student_id,
        base.student_no,
        base.student_name,
        base.major_name,
        base.class_name,
        base.cumulative_gpa,
        base.earned_credits,
        base.published_fail_count,
        gt.current_semester_gpa,
        gt.previous_semester_gpa,
        gt.gpa_decline,
        css.projected_semester_gpa,
        css.projected_fail_count,
        css.current_published_fail_count,
        css.current_courses,
        CASE
            WHEN base.cumulative_gpa IS NOT NULL
             AND base.earned_credits >= 6
             AND base.cumulative_gpa < 2.0
            THEN 'high'
            WHEN base.published_fail_count >= 2
            THEN 'high'
            WHEN COALESCE(css.current_published_fail_count, 0) >= 2
            THEN 'high'
            WHEN COALESCE(css.projected_fail_count, 0) >= 2
            THEN 'high'
            WHEN base.cumulative_gpa IS NOT NULL
             AND base.earned_credits >= 6
             AND base.cumulative_gpa >= 2.0
             AND base.cumulative_gpa < 2.3
            THEN 'medium'
            WHEN gt.gpa_decline IS NOT NULL AND gt.gpa_decline >= 0.5
            THEN 'medium'
            WHEN css.projected_semester_gpa IS NOT NULL
             AND base.cumulative_gpa IS NOT NULL
             AND css.projected_semester_gpa < base.cumulative_gpa - 0.4
            THEN 'medium'
            WHEN base.published_fail_count = 1
            THEN 'low'
            WHEN COALESCE(css.projected_fail_count, 0) = 1
            THEN 'low'
            WHEN COALESCE(css.current_published_fail_count, 0) = 1
            THEN 'low'
            ELSE 'none'
        END AS risk_level,
        TRIM(BOTH ';' FROM CONCAT_WS(';',
            IF(base.cumulative_gpa IS NOT NULL AND base.earned_credits >= 6 AND base.cumulative_gpa < 2.0,
               '累计GPA低于2.0', NULL),
            IF(base.published_fail_count >= 2,
               CONCAT('累计', base.published_fail_count, '门不及格'), NULL),
            IF(COALESCE(css.current_published_fail_count, 0) >= 2,
               CONCAT('本学期', css.current_published_fail_count, '门已发布成绩不及格'), NULL),
            IF(COALESCE(css.projected_fail_count, 0) >= 2,
               CONCAT('预测本学期', css.projected_fail_count, '门存在挂科风险'), NULL),
            IF(base.cumulative_gpa IS NOT NULL AND base.earned_credits >= 6
               AND base.cumulative_gpa >= 2.0 AND base.cumulative_gpa < 2.3,
               '累计GPA处于预警区(2.0~2.3)', NULL),
            IF(gt.gpa_decline IS NOT NULL AND gt.gpa_decline >= 0.5,
               CONCAT('较上学期GPA下滑', gt.gpa_decline, ''), NULL),
            IF(css.projected_semester_gpa IS NOT NULL AND base.cumulative_gpa IS NOT NULL
               AND css.projected_semester_gpa < base.cumulative_gpa - 0.4,
               CONCAT('预测学期GPA(', css.projected_semester_gpa, ')明显低于累计水平'), NULL),
            IF(base.published_fail_count = 1, '存在单门历史不及格', NULL),
            IF(COALESCE(css.projected_fail_count, 0) = 1, '预测单门课程挂科风险', NULL),
            IF(COALESCE(css.current_published_fail_count, 0) = 1, '本学期单门不及格', NULL)
        )) AS risk_reasons
    FROM v_student_cumulative_gpa base
    LEFT JOIN current_semester_stats css ON css.student_id = base.student_id
    LEFT JOIN gpa_trend gt ON gt.student_id = base.student_id
    WHERE (p_student_id IS NULL OR base.student_id = p_student_id)
    HAVING risk_level != 'none'
    ORDER BY
        FIELD(risk_level, 'high', 'medium', 'low'),
        base.cumulative_gpa ASC,
        base.student_no;
END //

DELIMITER ;
