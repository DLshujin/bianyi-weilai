import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()

# 1. 备份原表数据
cursor.execute('PRAGMA foreign_keys=off;')
cursor.execute('''CREATE TABLE IF NOT EXISTS schedule_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER,
    student_ids TEXT,
    teacher TEXT,
    start_date TEXT,
    end_date TEXT,
    time TEXT,
    note TEXT,
    status TEXT
)''')
cursor.execute('''INSERT INTO schedule_new (id, course_id, student_ids, teacher, start_date, end_date, time, note, status)
                 SELECT id, course_id, student_ids, teacher, start_date, end_date, time, note, status FROM schedule''')

# 2. 删除原表
cursor.execute('DROP TABLE schedule')

# 3. 重命名新表
cursor.execute('ALTER TABLE schedule_new RENAME TO schedule')
cursor.execute('PRAGMA foreign_keys=on;')
conn.commit()
conn.close()
print('schedule表已重建，date字段已彻底移除！')