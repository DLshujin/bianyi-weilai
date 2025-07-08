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

# 插入默认管理员账号（如不存在）
cursor.execute('SELECT * FROM user WHERE username = ?', ('admin',))
if not cursor.fetchone():
    cursor.execute('INSERT INTO user (username, password, role) VALUES (?, ?, ?)', ('admin', '123456', 'admin'))

conn.commit()
conn.close()

print('数据库初始化完成！')
