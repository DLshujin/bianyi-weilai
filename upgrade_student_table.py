import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()
try:
    cursor.execute('ALTER TABLE student ADD COLUMN email TEXT')
except Exception as e:
    print('email 字段可能已存在:', e)
try:
    cursor.execute('ALTER TABLE student ADD COLUMN remark TEXT')
except Exception as e:
    print('remark 字段可能已存在:', e)
try:
    cursor.execute('ALTER TABLE student ADD COLUMN class_name TEXT')
except Exception as e:
    print('class_name 字段可能已存在:', e)
conn.commit()
conn.close()
print('student表已升级，可支持更多字段。') 