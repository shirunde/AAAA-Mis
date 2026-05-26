-- =====================================================
-- 校园教务选课与成绩管理系统 - 测试种子数据
-- =====================================================

USE mis_system;

-- 管理员账户 (密码: admin123)
INSERT INTO users (username, password_hash, role, is_active) VALUES
('admin', 'scrypt:32768:8:1$iC2wUoMkfX8dVKzA$e9e63cfb3b2d1bdf6d8d6a5f7d4b3a0c74f9c8e7d6b5a4c3d2e1f7d8e9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f', 'admin', 1);

-- 学期数据
INSERT INTO semesters (name, start_date, end_date, is_current) VALUES
('2025-2026-1', '2025-09-01', '2026-01-15', 1),
('2025-2026-2', '2026-02-20', '2026-07-10', 0);

-- 专业数据
INSERT INTO majors (name, code, description) VALUES
('计算机科学与技术', 'CS', '培养计算机软硬件系统设计与开发能力'),
('软件工程', 'SE', '培养大型软件系统分析与设计能力'),
('数据科学与大数据技术', 'DS', '培养大数据分析与处理能力'),
('人工智能', 'AI', '培养人工智能算法与系统开发能力');

-- 班级数据
INSERT INTO classes (name, major_id, grade) VALUES
('计科2301', 1, 2023),
('计科2302', 1, 2023),
('软工2301', 2, 2023),
('软工2302', 2, 2023),
('数据2301', 3, 2023),
('人工2301', 4, 2023);

-- 课程数据
INSERT INTO courses (code, name, credit, hours, course_type, description) VALUES
('CS101', '数据结构与算法', 4.0, 64, 'required', '线性表、树、图等数据结构及查找排序算法'),
('CS102', '操作系统原理', 3.5, 56, 'required', '进程管理、内存管理、文件系统等操作系统核心概念'),
('CS103', '计算机网络', 3.0, 48, 'required', 'TCP/IP协议栈、网络层、传输层及应用层协议'),
('CS201', '数据库系统概论', 3.5, 56, 'required', '关系模型、SQL语言、数据库设计与规范化'),
('CS202', 'Web前端开发', 2.5, 40, 'elective', 'HTML、CSS、JavaScript及主流前端框架'),
('CS203', 'Python数据分析', 2.0, 32, 'elective', '使用Python进行数据清洗、分析与可视化'),
('CS301', '人工智能导论', 3.0, 48, 'optional', '机器学习、深度学习基础理论与应用'),
('CS302', '软件工程导论', 2.5, 40, 'optional', '软件开发流程、需求分析、设计与测试方法');

-- 选课时间段
INSERT INTO course_selection_periods (semester_id, name, start_time, end_time, period_type, is_active) VALUES
(1, '2025秋季-初选阶段', '2025-09-05 08:00:00', '2025-09-15 23:59:59', 'selection', 1),
(1, '2025秋季-退课阶段', '2025-09-05 08:00:00', '2025-09-22 23:59:59', 'drop', 1),
(1, '2025秋季-补退选', '2025-09-20 08:00:00', '2025-09-30 23:59:59', 'selection', 1),
(1, '2025秋季-补退选(退课)', '2025-09-20 08:00:00', '2025-09-30 23:59:59', 'drop', 1);
