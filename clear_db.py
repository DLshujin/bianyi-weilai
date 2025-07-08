import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()

# 清空所有数据，但保留表结构
cursor.execute('DELETE FROM record')
cursor.execute('DELETE FROM student_course')
cursor.execute('DELETE FROM student')
cursor.execute('DELETE FROM course')
cursor.execute('DELETE FROM user WHERE username != "admin"')  # 保留admin账号

conn.commit()
conn.close()
print("数据库数据已清空（保留admin账号）！")