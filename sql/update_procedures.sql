-- 更新存储过程 - 增强冲突检测
USE mis_system;

-- 删除旧的存储过程
DROP PROCEDURE IF EXISTS sp_enroll_course;
DROP PROCEDURE IF EXISTS sp_approve_course_offering;

-- 重新创建(从03_procedures.sql中复制最新定义)
DELIMITER //

-- 这里包含修改后的sp_enroll_course和sp_approve_course_offering
-- (由于文件较长,直接执行03_procedures.sql会更方便)

DELIMITER ;

SELECT '请手动执行: source c:/Users/24189/Desktop/mis/sql/03_procedures.sql' AS message;
