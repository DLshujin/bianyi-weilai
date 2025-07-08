import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()
try:
    cursor.execute('ALTER TABLE record ADD COLUMN operator TEXT;')
    print("成功为 record 表添加 operator 字段。")
except Exception as e:
    print("执行出错：", e)
conn.commit()
conn.close()