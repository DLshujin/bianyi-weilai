import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()
try:
    cursor.execute('ALTER TABLE course ADD COLUMN price REAL')
    print("成功为 course 表添加 price 字段。")
except Exception as e:
    print("执行出错：", e)
conn.commit()
conn.close() 