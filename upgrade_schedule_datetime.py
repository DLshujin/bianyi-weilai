import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()

# 添加新字段（如果不存在）
try:
    cursor.execute('ALTER TABLE schedule ADD COLUMN start_date TEXT')
except Exception as e:
    print('start_date 字段可能已存在:', e)
try:
    cursor.execute('ALTER TABLE schedule ADD COLUMN end_date TEXT')
except Exception as e:
    print('end_date 字段可能已存在:', e)

# 将原date字段数据迁移到新字段（仅为空时迁移）
cursor.execute('UPDATE schedule SET start_date = date WHERE (start_date IS NULL OR start_date = "") AND date IS NOT NULL')
cursor.execute('UPDATE schedule SET end_date = date WHERE (end_date IS NULL OR end_date = "") AND date IS NOT NULL')

conn.commit()
conn.close()
print('数据库升级完成！') 