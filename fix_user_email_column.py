import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()
try:
    cursor.execute('ALTER TABLE user ADD COLUMN email TEXT;')
    print("成功为 user 表添加 email 字段。")
except Exception as e:
    print("执行出错：", e)
conn.commit()
conn.close() 