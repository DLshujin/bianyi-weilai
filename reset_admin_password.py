import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()
cursor.execute("UPDATE user SET password = '123456' WHERE username = 'admin'")
conn.commit()
conn.close()
print("admin密码已重置为123456")