# 校园教务选课与成绩管理系统

数据库实训项目 - MIS系统设计与实现

## 技术栈

- **后端**: Python Flask 3.x
- **数据库**: MySQL 8.x (原生SQL + 存储过程 + 触发器 + 视图)
- **前端**: Bootstrap 5 + Jinja2 + Chart.js
- **驱动**: PyMySQL + DBUtils 连接池

## 快速启动

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 初始化数据库
按顺序执行 SQL 脚本：
```bash
mysql -u root -p < sql/01_schema.sql
mysql -u root -p < sql/03_procedures.sql
mysql -u root -p < sql/04_views.sql
mysql -u root -p < sql/02_seed.sql
```

### 3. 修改配置
复制 `.env.example` 为 `.env` 并修改数据库连接参数；或直接编辑 `config.py`。

### 4. 启动应用
```bash
python app.py
```
访问 http://localhost:5000

## 测试账户

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |
| 学生 | 自行注册 | - |
| 教师 | 自行注册 | - |

## 项目结构

```
mis/
├── app.py                    # 应用入口
├── config.py                 # 配置文件
├── requirements.txt          # Python依赖
├── sql/                      # SQL脚本
│   ├── 01_schema.sql         # 建表(12张表)
│   ├── 02_seed.sql           # 种子数据
│   ├── 03_procedures.sql     # 存储过程&触发器
│   └── 04_views.sql          # 视图定义
├── app/                      # 应用模块
│   ├── db.py                 # 数据库连接池
│   ├── decorators.py         # 权限装饰器
│   ├── auth/                 # 认证模块
│   ├── admin/                # 管理员模块
│   ├── teacher/              # 教师模块
│   ├── student/              # 学生模块
│   └── templates/            # 页面模板
├── static/                   # 静态资源
└── README.md
```

## 数据库设计

- 12张核心表，完整的3NF设计
- 5个存储过程（选课、退课、成绩计算、GPA计算、审核）
- 3个触发器（选课自动创建成绩、成绩更新自动计算、状态变更日志）
- 4个视图（课表、成绩单、选课统计、教师工作量）

## 核心业务流

```
管理员录入基础信息 → 教师申请开课 → 管理员审核发布
    → 配置选课时间窗口 → 学生选课/退课
    → 教师录入成绩 → 管理员审核发布 → 学生查看成绩
```
