import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()

# 清空所有数据，但保留表结构
cursor.execute('DELETE FROM record')
cursor.execute('DELETE FROM student_course')
cursor.execute('DELETE FROM student')
cursor.execute('DELETE FROM course')
cursor.execute('DELETE FROM user')
cursor.execute('DELETE FROM record_log')
cursor.execute('DELETE FROM schedule')

# 重置所有自增ID（sqlite_sequence）
cursor.execute('DELETE FROM sqlite_sequence')

# 重新插入admin账号，密码为888888
cursor.execute("INSERT INTO user (username, password, role) VALUES (?, ?, ?)", ('admin', '888888', 'admin'))

conn.commit()
conn.close()
print("所有业务数据及自增ID已全部初始化，admin账号已重置为888888！")