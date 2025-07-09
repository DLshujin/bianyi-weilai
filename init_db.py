import sqlite3

# 连接数据库（如果不存在则会自动创建）
conn = sqlite3.connect('school.db')
cursor = conn.cursor()

# 创建学生表
cursor.execute('''
CREATE TABLE IF NOT EXISTS student (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT,
    teacher TEXT
)
''')

# 创建课程表
cursor.execute('''
CREATE TABLE IF NOT EXISTS course (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    total_hours INTEGER
)
''')

# 创建课消记录表，增加topic和teacher字段
cursor.execute('''
CREATE TABLE IF NOT EXISTS record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    hours_consumed INTEGER NOT NULL,
    date TEXT NOT NULL,
    note TEXT,
    topic TEXT,
    teacher TEXT,
    FOREIGN KEY(student_id) REFERENCES student(id),
    FOREIGN KEY(course_id) REFERENCES course(id)
)
''')

# 创建学生-课程关联表
cursor.execute('''
CREATE TABLE IF NOT EXISTS student_course (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    total_hours INTEGER NOT NULL,
    price REAL NOT NULL,
    FOREIGN KEY(student_id) REFERENCES student(id),
    FOREIGN KEY(course_id) REFERENCES course(id)
)
''')

# 创建用户表
cursor.execute('''
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user'
)
''')

# 创建操作日志表
cursor.execute('''
CREATE TABLE IF NOT EXISTS record_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER,
    operation_type TEXT NOT NULL, -- add/edit/delete
    operator TEXT NOT NULL,
    operation_time TEXT NOT NULL,
    before_content TEXT,
    after_content TEXT,
    FOREIGN KEY(record_id) REFERENCES record(id)
)
''')

# 创建排课表，支持一次为多个学生排同一节课，student_ids为逗号分隔字符串
cursor.execute('''
CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    student_ids TEXT NOT NULL, -- 逗号分隔的学生ID
    teacher TEXT,
    date TEXT NOT NULL,
    time TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT '未消课',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY(course_id) REFERENCES course(id)
)
''')

# 插入默认管理员账号（如不存在）
cursor.execute('SELECT * FROM user WHERE username = ?', ('admin',))
if not cursor.fetchone():
    cursor.execute('INSERT INTO user (username, password, role) VALUES (?, ?, ?)', ('admin', '123456', 'admin'))

conn.commit()
conn.close()

print('数据库初始化完成！')
