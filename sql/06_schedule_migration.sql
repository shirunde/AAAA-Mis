-- =====================================================
-- 课程时间地点冲突检测系统 - 数据库迁移脚本
-- 创建教室、时间段、开课时间表等新表
-- =====================================================

USE mis_system;

-- =====================================================
-- 1. 创建 classrooms 教室表
-- =====================================================
CREATE TABLE IF NOT EXISTS classrooms (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(20)     NOT NULL,           -- 'yf101', 'sy301'
    name        VARCHAR(50)     NOT NULL,           -- '逸夫楼101', '实验楼301'
    building    VARCHAR(50)     NOT NULL,           -- '逸夫楼', '实验楼'
    room_number VARCHAR(20)     NOT NULL,           -- '101', '301'
    capacity    INT             NULL,               -- 容纳人数(可选)
    is_active   TINYINT(1)      NOT NULL DEFAULT 1,
    UNIQUE KEY uk_code (code),
    INDEX idx_building (building)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- 2. 创建 time_slots 时间段表
-- =====================================================
CREATE TABLE IF NOT EXISTS time_slots (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    day_of_week TINYINT         NOT NULL,           -- 1=周一, 7=周日
    period_num  TINYINT         NOT NULL,           -- 1,2,3,4,5
    start_time  TIME            NOT NULL,           -- '08:00:00'
    end_time    TIME            NOT NULL,           -- '10:00:00'
    label       VARCHAR(20)     NOT NULL,           -- '第1节'
    UNIQUE KEY uk_slot (day_of_week, period_num),
    INDEX idx_day (day_of_week)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- 3. 创建 offering_schedules 开课时间表(关联表)
-- =====================================================
CREATE TABLE IF NOT EXISTS offering_schedules (
    id                  INT             AUTO_INCREMENT PRIMARY KEY,
    course_offering_id  INT             NOT NULL,
    time_slot_id        INT             NOT NULL,
    classroom_id        INT             NOT NULL,
    UNIQUE KEY uk_unique (course_offering_id, time_slot_id, classroom_id),
    INDEX idx_offering (course_offering_id),
    INDEX idx_timeslot (time_slot_id),
    INDEX idx_classroom (classroom_id),
    CONSTRAINT fk_os_offering FOREIGN KEY (course_offering_id)
        REFERENCES course_offerings(id) ON DELETE CASCADE,
    CONSTRAINT fk_os_timeslot FOREIGN KEY (time_slot_id)
        REFERENCES time_slots(id) ON DELETE RESTRICT,
    CONSTRAINT fk_os_classroom FOREIGN KEY (classroom_id)
        REFERENCES classrooms(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- 4. 插入时间段种子数据(周一至周五,每天5个时段)
-- =====================================================
INSERT INTO time_slots (day_of_week, period_num, start_time, end_time, label) VALUES
-- 周一
(1, 1, '08:00:00', '10:00:00', '第1节'),
(1, 2, '10:00:00', '12:00:00', '第2节'),
(1, 3, '14:00:00', '16:00:00', '第3节'),
(1, 4, '16:00:00', '18:00:00', '第4节'),
(1, 5, '19:00:00', '21:00:00', '第5节'),
-- 周二
(2, 1, '08:00:00', '10:00:00', '第1节'),
(2, 2, '10:00:00', '12:00:00', '第2节'),
(2, 3, '14:00:00', '16:00:00', '第3节'),
(2, 4, '16:00:00', '18:00:00', '第4节'),
(2, 5, '19:00:00', '21:00:00', '第5节'),
-- 周三
(3, 1, '08:00:00', '10:00:00', '第1节'),
(3, 2, '10:00:00', '12:00:00', '第2节'),
(3, 3, '14:00:00', '16:00:00', '第3节'),
(3, 4, '16:00:00', '18:00:00', '第4节'),
(3, 5, '19:00:00', '21:00:00', '第5节'),
-- 周四
(4, 1, '08:00:00', '10:00:00', '第1节'),
(4, 2, '10:00:00', '12:00:00', '第2节'),
(4, 3, '14:00:00', '16:00:00', '第3节'),
(4, 4, '16:00:00', '18:00:00', '第4节'),
(4, 5, '19:00:00', '21:00:00', '第5节'),
-- 周五
(5, 1, '08:00:00', '10:00:00', '第1节'),
(5, 2, '10:00:00', '12:00:00', '第2节'),
(5, 3, '14:00:00', '16:00:00', '第3节'),
(5, 4, '16:00:00', '18:00:00', '第4节'),
(5, 5, '19:00:00', '21:00:00', '第5节');

-- =====================================================
-- 5. 插入示例教室数据(部分示例,可根据需要扩展)
-- =====================================================
INSERT INTO classrooms (code, name, building, room_number, capacity) VALUES
-- 逸夫楼 (yf101-yf110 示例)
('yf101', '逸夫楼101', '逸夫楼', '101', 60),
('yf102', '逸夫楼102', '逸夫楼', '102', 60),
('yf103', '逸夫楼103', '逸夫楼', '103', 80),
('yf201', '逸夫楼201', '逸夫楼', '201', 60),
('yf202', '逸夫楼202', '逸夫楼', '202', 60),
('yf301', '逸夫楼301', '逸夫楼', '301', 100),
('yf302', '逸夫楼302', '逸夫楼', '302', 100),
('yf401', '逸夫楼401', '逸夫楼', '401', 80),
('yf501', '逸夫楼501', '逸夫楼', '501', 60),
('yf601', '逸夫楼601', '逸夫楼', '601', 60),
-- 实验楼 (sy101-sy110 示例)
('sy101', '实验楼101', '实验楼', '101', 40),
('sy102', '实验楼102', '实验楼', '102', 40),
('sy103', '实验楼103', '实验楼', '103', 50),
('sy201', '实验楼201', '实验楼', '201', 40),
('sy202', '实验楼202', '实验楼', '202', 40),
('sy301', '实验楼301', '实验楼', '301', 60),
('sy302', '实验楼302', '实验楼', '302', 60),
('sy401', '实验楼401', '实验楼', '401', 50),
('sy501', '实验楼501', '实验楼', '501', 40),
('sy601', '实验楼601', '实验楼', '601', 40);

-- =====================================================
-- 6. 修改 course_offerings 表,添加遗留字段
-- =====================================================
ALTER TABLE course_offerings
ADD COLUMN legacy_schedule VARCHAR(200) NULL COMMENT '遗留字段,不再使用',
ADD COLUMN legacy_classroom VARCHAR(100) NULL COMMENT '遗留字段,不再使用';

-- 迁移现有数据到遗留字段
UPDATE course_offerings
SET legacy_schedule = schedule,
    legacy_classroom = classroom;

-- 清空原字段(后续版本可删除)
UPDATE course_offerings SET schedule = NULL, classroom = NULL;

-- =====================================================
-- 完成提示
-- =====================================================
SELECT '数据库迁移完成!' AS message;
SELECT COUNT(*) AS time_slots_count FROM time_slots;
SELECT COUNT(*) AS classrooms_count FROM classrooms;
