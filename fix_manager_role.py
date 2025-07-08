import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()
# 把用户名为 '你的管理员用户名' 的账号角色改为 'manager'
cursor.execute("UPDATE user SET role='manager' WHERE username='你的管理员用户名'")
conn.commit()
conn.close()
print("修正完成！")