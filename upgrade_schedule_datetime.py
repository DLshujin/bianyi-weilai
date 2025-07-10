import sqlite3
from datetime import datetime

conn = sqlite3.connect('school.db')
cursor = conn.cursor()

# 1. 添加新字段（如果不存在）
try:
    cursor.execute('ALTER TABLE schedule ADD COLUMN start_datetime TEXT')
except Exception as e:
    print('start_datetime 字段可能已存在:', e)
try:
    cursor.execute('ALTER TABLE schedule ADD COLUMN end_datetime TEXT')
except Exception as e:
    print('end_datetime 字段可能已存在:', e)

# 2. 迁移原有数据（合并日期和时间）
def merge_date_time(date_str, time_str):
    if not date_str:
        return ''
    if not time_str:
        return date_str.strip() + ' 00:00'
    return date_str.strip() + ' ' + time_str.strip()

cursor.execute('SELECT id, start_date, end_date, time FROM schedule')
for row in cursor.fetchall():
    sid, start_date, end_date, time_val = row
    start_dt = merge_date_time(start_date, time_val)
    end_dt = merge_date_time(end_date, time_val)
    cursor.execute('UPDATE schedule SET start_datetime=?, end_datetime=? WHERE id=?', (start_dt, end_dt, sid))

conn.commit()

# 3. 可选：删除旧字段（sqlite不支持直接drop column，需手动迁移表结构）
print('数据库升级完成！schedule表已支持start_datetime和end_datetime字段，原数据已迁移。')
conn.close() 