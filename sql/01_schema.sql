-- =====================================================
-- 校园教务选课与成绩管理系统 - 建表脚本
-- 12张核心表，含完整的约束、索引、外键关系
-- =====================================================

CREATE DATABASE IF NOT EXISTS mis_system
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE mis_system;

-- =====================================================
-- 1. users 用户账户表
-- =====================================================
CREATE TABLE users (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50)     NOT NULL,
    password_hash VARCHAR(255)  NOT NULL,
    role        ENUM('student', 'teacher', 'admin') NOT NULL,
    is_active   TINYINT(1)      NOT NULL DEFAULT 1,
    last_login  DATETIME        NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NULL ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_username (username),
    INDEX idx_role (role)
) ENGINE=InnoDB;

-- =====================================================
-- 2. majors 专业表
-- =====================================================
CREATE TABLE majors (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100)    NOT NULL,
    code        VARCHAR(20)     NOT NULL,
    description TEXT            NULL,
    UNIQUE KEY uk_code (code)
) ENGINE=InnoDB;

-- =====================================================
-- 3. classes 班级表
-- =====================================================
CREATE TABLE classes (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50)     NOT NULL,
    major_id    INT             NOT NULL,
    grade       YEAR            NOT NULL,
    INDEX idx_major (major_id),
    CONSTRAINT fk_class_major FOREIGN KEY (major_id) REFERENCES majors(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- =====================================================
-- 4. students 学生信息表
-- =====================================================
CREATE TABLE students (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    user_id         INT             NOT NULL,
    student_no      VARCHAR(20)     NOT NULL,
    name            VARCHAR(50)     NOT NULL,
    gender          ENUM('M', 'F')  NOT NULL,
    major_id        INT             NOT NULL,
    class_id        INT             NOT NULL,
    enrollment_year YEAR            NOT NULL,
    phone           VARCHAR(20)     NULL,
    email           VARCHAR(100)    NULL,
    status          ENUM('active', 'graduated', 'suspended') NOT NULL DEFAULT 'active',
    UNIQUE KEY uk_student_no (student_no),
    UNIQUE KEY uk_student_user (user_id),
    INDEX idx_student_major (major_id),
    INDEX idx_student_class (class_id),
    CONSTRAINT fk_student_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_student_major FOREIGN KEY (major_id) REFERENCES majors(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_student_class FOREIGN KEY (class_id) REFERENCES classes(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- =====================================================
-- 5. teachers 教师信息表
-- =====================================================
CREATE TABLE teachers (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    user_id     INT             NOT NULL,
    teacher_no  VARCHAR(20)     NOT NULL,
    name        VARCHAR(50)     NOT NULL,
    gender      ENUM('M', 'F')  NOT NULL,
    title       VARCHAR(50)     NULL,
    phone       VARCHAR(20)     NULL,
    email       VARCHAR(100)    NULL,
    UNIQUE KEY uk_teacher_no (teacher_no),
    UNIQUE KEY uk_teacher_user (user_id),
    CONSTRAINT fk_teacher_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- =====================================================
-- 6. semesters 学期表
-- =====================================================
CREATE TABLE semesters (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50)     NOT NULL,
    start_date  DATE            NOT NULL,
    end_date    DATE            NOT NULL,
    is_current  TINYINT(1)      NOT NULL DEFAULT 0,
    UNIQUE KEY uk_semester_name (name),
    INDEX idx_current (is_current)
) ENGINE=InnoDB;

-- =====================================================
-- 7. courses 课程信息表
-- =====================================================
CREATE TABLE courses (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(20)     NOT NULL,
    name        VARCHAR(100)    NOT NULL,
    credit      DECIMAL(3,1)    NOT NULL,
    hours       INT             NOT NULL,
    course_type ENUM('required', 'elective', 'optional') NOT NULL,
    description TEXT            NULL,
    UNIQUE KEY uk_course_code (code),
    INDEX idx_course_type (course_type),
    CONSTRAINT chk_credit CHECK (credit > 0),
    CONSTRAINT chk_hours CHECK (hours > 0)
) ENGINE=InnoDB;

-- =====================================================
-- 8. course_offerings 开课申请表
-- =====================================================
CREATE TABLE course_offerings (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    course_id       INT             NOT NULL,
    teacher_id      INT             NOT NULL,
    semester_id     INT             NOT NULL,
    max_students    INT             NOT NULL,
    classroom       VARCHAR(100)    NULL,
    schedule        VARCHAR(200)    NULL,
    status          ENUM('pending', 'approved', 'rejected', 'published') NOT NULL DEFAULT 'pending',
    apply_reason    TEXT            NULL,
    review_comment  TEXT            NULL,
    reviewed_at     DATETIME        NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_offering (course_id, teacher_id, semester_id),
    INDEX idx_offering_course (course_id),
    INDEX idx_offering_teacher (teacher_id),
    INDEX idx_offering_semester (semester_id),
    INDEX idx_offering_status (status),
    CONSTRAINT fk_offering_course FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_offering_teacher FOREIGN KEY (teacher_id) REFERENCES teachers(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_offering_semester FOREIGN KEY (semester_id) REFERENCES semesters(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT chk_max_students CHECK (max_students >= 1)
) ENGINE=InnoDB;

-- =====================================================
-- 9. enrollments 选课记录表
-- =====================================================
CREATE TABLE enrollments (
    id                  INT             AUTO_INCREMENT PRIMARY KEY,
    student_id          INT             NOT NULL,
    course_offering_id  INT             NOT NULL,
    status              ENUM('enrolled', 'dropped') NOT NULL DEFAULT 'enrolled',
    enrolled_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dropped_at          DATETIME        NULL,
    UNIQUE KEY uk_enrollment (student_id, course_offering_id),
    INDEX idx_enroll_offering (course_offering_id),
    INDEX idx_enroll_status (status),
    CONSTRAINT fk_enroll_student FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_enroll_offering FOREIGN KEY (course_offering_id) REFERENCES course_offerings(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- =====================================================
-- 10. grades 成绩表
-- =====================================================
CREATE TABLE grades (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    enrollment_id   INT             NOT NULL,
    regular_grade   DECIMAL(5,2)    NULL,
    exam_grade      DECIMAL(5,2)    NULL,
    total_grade     DECIMAL(5,2)    NULL,
    gpa_point       DECIMAL(3,1)    NULL,
    status          ENUM('draft', 'submitted', 'approved', 'published') NOT NULL DEFAULT 'draft',
    submitted_at    DATETIME        NULL,
    approved_at     DATETIME        NULL,
    published_at    DATETIME        NULL,
    updated_at      DATETIME        NULL ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_grade_enrollment (enrollment_id),
    INDEX idx_grade_status (status),
    CONSTRAINT fk_grade_enrollment FOREIGN KEY (enrollment_id) REFERENCES enrollments(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_regular CHECK (regular_grade IS NULL OR (regular_grade >= 0 AND regular_grade <= 100)),
    CONSTRAINT chk_exam CHECK (exam_grade IS NULL OR (exam_grade >= 0 AND exam_grade <= 100)),
    CONSTRAINT chk_total CHECK (total_grade IS NULL OR (total_grade >= 0 AND total_grade <= 100))
) ENGINE=InnoDB;

-- =====================================================
-- 11. course_selection_periods 选课时间段表
-- =====================================================
CREATE TABLE course_selection_periods (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    semester_id INT             NOT NULL,
    name        VARCHAR(100)    NOT NULL,
    start_time  DATETIME        NOT NULL,
    end_time    DATETIME        NOT NULL,
    period_type ENUM('selection', 'drop') NOT NULL,
    is_active   TINYINT(1)      NOT NULL DEFAULT 1,
    INDEX idx_period_semester (semester_id),
    INDEX idx_period_time (start_time, end_time),
    CONSTRAINT fk_period_semester FOREIGN KEY (semester_id) REFERENCES semesters(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- =====================================================
-- 12. system_logs 操作日志表
-- =====================================================
CREATE TABLE system_logs (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    user_id     INT             NULL,
    action      VARCHAR(100)    NOT NULL,
    target_type VARCHAR(50)     NULL,
    target_id   INT             NULL,
    detail      TEXT            NULL,
    ip_address  VARCHAR(45)     NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_log_user (user_id),
    INDEX idx_log_action (action),
    INDEX idx_log_created (created_at),
    CONSTRAINT fk_log_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB;
