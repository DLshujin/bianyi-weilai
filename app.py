from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
import pandas as pd
from flask import send_file
import io
from functools import wraps
import os
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

def get_db_connection():
    db_path = os.path.abspath('school.db')
    print('数据库绝对路径:', db_path)
    conn = sqlite3.connect('school.db')
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 仅admin可访问

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('username') != 'admin':
            flash('无权限访问')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_or_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') not in ['admin', 'manager']:
            flash('无权限访问')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM user WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('index'))
        else:
            error = '用户名或密码错误'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- 需要登录的页面 ---
@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    if session.get('role') in ['admin', 'manager']:
        records = conn.execute('''
            SELECT record.id, student.name AS student_name, course.name AS course_name, record.hours_consumed, record.date, record.note, record.topic, record.operator
            FROM record
            JOIN student ON record.student_id = student.id
            JOIN course ON record.course_id = course.id
            ORDER BY record.date DESC
        ''').fetchall()
        balances = conn.execute('''
            SELECT s.name AS student_name, c.name AS course_name, sc.total_hours,
                   IFNULL(SUM(r.hours_consumed), 0) AS consumed_hours,
                   sc.total_hours - IFNULL(SUM(r.hours_consumed), 0) AS remaining_hours
            FROM student_course sc
            JOIN student s ON sc.student_id = s.id
            JOIN course c ON sc.course_id = c.id
            LEFT JOIN record r ON sc.student_id = r.student_id AND sc.course_id = r.course_id
            GROUP BY sc.id
            ORDER BY s.name, c.name
        ''').fetchall()
    else:
        records = conn.execute('''
            SELECT record.id, student.name AS student_name, course.name AS course_name, record.hours_consumed, record.date, record.note, record.topic, record.operator
            FROM record
            JOIN student ON record.student_id = student.id
            JOIN course ON record.course_id = course.id
            WHERE student.name = ?
            ORDER BY record.date DESC
        ''', (session.get('username'),)).fetchall()
        balances = conn.execute('''
            SELECT s.name AS student_name, c.name AS course_name, sc.total_hours,
                   IFNULL(SUM(r.hours_consumed), 0) AS consumed_hours,
                   sc.total_hours - IFNULL(SUM(r.hours_consumed), 0) AS remaining_hours
            FROM student_course sc
            JOIN student s ON sc.student_id = s.id
            JOIN course c ON sc.course_id = c.id
            LEFT JOIN record r ON sc.student_id = r.student_id AND sc.course_id = r.course_id
            WHERE s.name = ?
            GROUP BY sc.id
            ORDER BY s.name, c.name
        ''', (session.get('username'),)).fetchall()
    conn.close()
    return render_template('index.html', records=records, balances=balances)

@app.route('/add', methods=['GET', 'POST'])
@admin_or_manager_required
def add():
    conn = get_db_connection()
    students = conn.execute('SELECT * FROM student').fetchall()
    courses = conn.execute('SELECT * FROM course').fetchall()
    if request.method == 'POST':
        student_ids = request.form.getlist('student_id')
        course_id = request.form['course_id']
        hours_consumed = request.form['hours_consumed']
        date = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
        note = request.form['note']
        topic = request.form['topic']
        teacher = request.form.get('teacher')
        operator = session.get('username')
        cursor = conn.cursor()
        for student_id in student_ids:
            cursor.execute(
                'INSERT INTO record (student_id, course_id, hours_consumed, date, note, topic, teacher, operator) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (student_id, course_id, hours_consumed, date, note, topic, teacher, operator)
            )
            record_id = cursor.lastrowid
            # 写入日志
            cursor.execute(
                'INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)',
                (record_id, 'add', operator, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None, json.dumps({
                    'student_id': student_id, 'course_id': course_id, 'hours_consumed': hours_consumed, 'date': date, 'note': note, 'topic': topic, 'teacher': teacher, 'operator': operator
                }))
            )
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    conn.close()
    return render_template('add.html', students=students, courses=courses)

@app.route('/edit/<int:record_id>', methods=['GET', 'POST'])
@admin_or_manager_required
def edit_record(record_id):
    conn = get_db_connection()
    record = conn.execute('SELECT * FROM record WHERE id = ?', (record_id,)).fetchone()
    students = conn.execute('SELECT * FROM student').fetchall()
    courses = conn.execute('SELECT * FROM course').fetchall()
    if request.method == 'POST':
        student_id = request.form['student_id']
        course_id = request.form['course_id']
        hours_consumed = request.form['hours_consumed']
        date = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
        note = request.form['note']
        topic = request.form['topic']
        teacher = request.form.get('teacher')
        operator = session.get('username')
        before_content = json.dumps(dict(record)) if record else None
        conn.execute('''
            UPDATE record SET student_id=?, course_id=?, hours_consumed=?, date=?, note=?, topic=?, teacher=?, operator=? WHERE id=?''',
            (student_id, course_id, hours_consumed, date, note, topic, teacher, operator, record_id)
        )
        after_content = json.dumps({
            'student_id': student_id, 'course_id': course_id, 'hours_consumed': hours_consumed, 'date': date, 'note': note, 'topic': topic, 'teacher': teacher, 'operator': operator
        })
        conn.execute(
            'INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)',
            (record_id, 'edit', operator, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), before_content, after_content)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    conn.close()
    return render_template('edit.html', record=record, students=students, courses=courses)

@app.route('/delete/<int:record_id>', methods=['POST'])
@admin_or_manager_required
def delete_record(record_id):
    conn = get_db_connection()
    record = conn.execute('SELECT * FROM record WHERE id = ?', (record_id,)).fetchone()
    operator = session.get('username')
    before_content = json.dumps(dict(record)) if record else None
    conn.execute('DELETE FROM record WHERE id = ?', (record_id,))
    conn.execute(
        'INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)',
        (record_id, 'delete', operator, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), before_content, None)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/students')
@admin_or_manager_required
def students():
    conn = get_db_connection()
    students = conn.execute('SELECT * FROM student').fetchall()
    conn.close()
    return render_template('students.html', students=students)

@app.route('/students/add', methods=['GET', 'POST'])
@admin_or_manager_required
def add_student():
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        course_names = request.form.getlist('course_name')
        total_hours_list = request.form.getlist('total_hours')
        price_list = request.form.getlist('price')
        cursor.execute('INSERT INTO student (name, contact) VALUES (?, ?)', (name, contact))
        student_id = cursor.lastrowid
        for idx, course_name in enumerate(course_names):
            if course_name and total_hours_list[idx] and price_list[idx]:
                # 检查课程是否已存在
                cursor.execute('SELECT id FROM course WHERE name = ?', (course_name,))
                course_row = cursor.fetchone()
                if course_row:
                    course_id = course_row['id']
                else:
                    cursor.execute('INSERT INTO course (name, total_hours) VALUES (?, ?)', (course_name, total_hours_list[idx]))
                    course_id = cursor.lastrowid
                cursor.execute('INSERT INTO student_course (student_id, course_id, total_hours, price) VALUES (?, ?, ?, ?)',
                               (student_id, course_id, total_hours_list[idx], price_list[idx]))
        conn.commit()
        conn.close()
        return redirect(url_for('students'))
    return render_template('add_student.html')

@app.route('/students/delete/<int:student_id>', methods=['POST'])
@admin_or_manager_required
def delete_student(student_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM student WHERE id = ?', (student_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('students'))

# 删除课程管理相关路由

@app.route('/export/<table>')
def export_table(table):
    valid_tables = {'student', 'course', 'record'}
    if table not in valid_tables:
        return '无效的表名', 400
    conn = get_db_connection()
    df = pd.read_sql_query(f'SELECT * FROM {table}', conn)
    conn.close()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=table)
    output.seek(0)
    filename = f'{table}.xlsx'
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/import/<table>', methods=['GET', 'POST'])
def import_table(table):
    valid_tables = {'student', 'course', 'record'}
    if table not in valid_tables:
        return '无效的表名', 400
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not getattr(file, "filename", None) or not (file.filename and file.filename.endswith('.xlsx')):
            flash('请上传Excel文件（.xlsx）')
            return redirect(request.url)
        df = pd.read_excel(file)
        conn = get_db_connection()
        cursor = conn.cursor()
        if table == 'student':
            for _, row in df.iterrows():
                cursor.execute('INSERT INTO student (name, contact) VALUES (?, ?)', (row.get('name'), row.get('contact')))
        elif table == 'course':
            for _, row in df.iterrows():
                cursor.execute('INSERT INTO course (name, total_hours) VALUES (?, ?)', (row.get('name'), row.get('total_hours')))
        elif table == 'record':
            for _, row in df.iterrows():
                cursor.execute('INSERT INTO record (student_id, course_id, hours_consumed, date, note) VALUES (?, ?, ?, ?, ?)',
                               (row.get('student_id'), row.get('course_id'), row.get('hours_consumed'), row.get('date'), row.get('note')))
        conn.commit()
        conn.close()
        flash('导入成功！')
        return redirect(url_for(f'{table}s'))
    return render_template('import.html', table=table)

@app.route('/users')
@admin_or_manager_required
def user_list():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM user').fetchall()
    conn.close()
    return render_template('users.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@admin_or_manager_required
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        # 只有admin能添加manager，admin和manager都不能添加admin
        if role == 'admin':
            flash('不能添加admin账号')
            return redirect(url_for('user_list'))
        if session.get('role') != 'admin' and role == 'manager':
            flash('无权限添加该类型用户')
            return redirect(url_for('user_list'))
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO user (username, password, role) VALUES (?, ?, ?)', (username, password, role))
            conn.commit()
            flash('添加成功')
        except Exception as e:
            flash(f'添加失败：{e}')
        conn.close()
        return redirect(url_for('user_list'))
    return render_template('add_user.html')

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_or_manager_required
def edit_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('用户不存在')
        return redirect(url_for('user_list'))
    # 只有admin能编辑admin/manager
    if session.get('role') != 'admin' and user['role'] in ['admin', 'manager']:
        conn.close()
        flash('无权限编辑该类型用户')
        return redirect(url_for('user_list'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        # manager不能将user改为admin/manager
        if session.get('role') != 'admin' and role in ['admin', 'manager']:
            flash('无权限修改为该类型用户')
            return redirect(url_for('user_list'))
        try:
            if password:
                conn.execute('UPDATE user SET username=?, password=?, role=? WHERE id=?', (username, password, role, user_id))
            else:
                conn.execute('UPDATE user SET username=?, role=? WHERE id=?', (username, role, user_id))
            conn.commit()
            flash('修改成功')
        except Exception as e:
            flash('修改失败：用户名已存在')
        conn.close()
        return redirect(url_for('user_list'))
    conn.close()
    return render_template('edit_user.html', user=user)

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_or_manager_required
def delete_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()
    # 只有admin能删除admin/manager
    if session.get('role') != 'admin' and user and user['role'] in ['admin', 'manager']:
        conn.close()
        flash('无权限删除该类型用户')
        return redirect(url_for('user_list'))
    if user_id == 1:
        flash('不能删除admin账号')
        return redirect(url_for('user_list'))
    conn.execute('DELETE FROM user WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('删除成功')
    return redirect(url_for('user_list'))

# 操作日志页面，仅admin可见
@app.route('/operation_logs')
@admin_required
def operation_logs():
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT l.*, u.username as operator_name FROM record_log l LEFT JOIN user u ON l.operator = u.username ORDER BY l.operation_time DESC
    ''').fetchall()
    conn.close()
    return render_template('operation_logs.html', logs=logs)

@app.route('/schedules')
@admin_or_manager_required
def schedule_list():
    conn = get_db_connection()
    schedules = conn.execute('SELECT * FROM schedule ORDER BY date DESC, time DESC').fetchall()
    courses = {c['id']: c['name'] for c in conn.execute('SELECT * FROM course').fetchall()}
    students = {s['id']: s['name'] for s in conn.execute('SELECT * FROM student').fetchall()}
    conn.close()
    return render_template('schedules.html', schedules=schedules, courses=courses, students=students)

@app.route('/schedules/add', methods=['GET', 'POST'])
@admin_or_manager_required
def add_schedule():
    conn = get_db_connection()
    courses = conn.execute('SELECT * FROM course').fetchall()
    students = conn.execute('SELECT * FROM student').fetchall()
    if request.method == 'POST':
        course_id = request.form['course_id']
        student_ids = request.form.getlist('student_ids')
        teacher = request.form.get('teacher')
        date = request.form['date']
        time = request.form['time']
        note = request.form['note']
        # 冲突检测（简单实现：同一学生同一天同一时间有排课则冲突）
        for sid in student_ids:
            conflict = conn.execute('SELECT * FROM schedule WHERE date=? AND time=? AND instr(student_ids, ?) > 0', (date, time, sid)).fetchone()
            if conflict:
                flash(f'学生ID {sid} 在该时间已排课，请检查！')
                conn.close()
                return redirect(request.url)
        student_ids_str = ','.join(student_ids)
        conn.execute('INSERT INTO schedule (course_id, student_ids, teacher, date, time, note) VALUES (?, ?, ?, ?, ?, ?)',
                     (course_id, student_ids_str, teacher, date, time, note))
        conn.commit()
        # add_schedule 日志
        conn.execute('INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)', (None, 'add_schedule', session.get('username'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None, json.dumps({'course_id': course_id, 'student_ids': student_ids_str, 'teacher': teacher, 'date': date, 'time': time, 'note': note})))
        conn.close()
        return redirect(url_for('schedule_list'))
    conn.close()
    return render_template('add_schedule.html', courses=courses, students=students)

@app.route('/schedules/edit/<int:schedule_id>', methods=['GET', 'POST'])
@admin_or_manager_required
def edit_schedule(schedule_id):
    conn = get_db_connection()
    schedule = conn.execute('SELECT * FROM schedule WHERE id=?', (schedule_id,)).fetchone()
    # manager只能编辑自己排的课
    if session.get('role') == 'manager' and schedule and schedule['teacher'] != session.get('username'):
        conn.close()
        flash('只能编辑自己排的课！')
        return redirect(url_for('schedule_list'))
    courses = conn.execute('SELECT * FROM course').fetchall()
    students = conn.execute('SELECT * FROM student').fetchall()
    if request.method == 'POST':
        course_id = request.form['course_id']
        student_ids = request.form.getlist('student_ids')
        teacher = request.form.get('teacher')
        date = request.form['date']
        time = request.form['time']
        note = request.form['note']
        # 冲突检测
        for sid in student_ids:
            conflict = conn.execute('SELECT * FROM schedule WHERE date=? AND time=? AND instr(student_ids, ?) > 0 AND id!=?', (date, time, sid, schedule_id)).fetchone()
            if conflict:
                flash(f'学生ID {sid} 在该时间已排课，请检查！')
                conn.close()
                return redirect(request.url)
        student_ids_str = ','.join(student_ids)
        conn.execute('UPDATE schedule SET course_id=?, student_ids=?, teacher=?, date=?, time=?, note=? WHERE id=?',
                     (course_id, student_ids_str, teacher, date, time, note, schedule_id))
        conn.commit()
        # edit_schedule 日志
        conn.execute('INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)', (None, 'edit_schedule', session.get('username'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), json.dumps(dict(schedule)), json.dumps({'course_id': course_id, 'student_ids': student_ids_str, 'teacher': teacher, 'date': date, 'time': time, 'note': note})))
        conn.close()
        return redirect(url_for('schedule_list'))
    conn.close()
    return render_template('add_schedule.html', schedule=schedule, courses=courses, students=students, edit=True)

@app.route('/schedules/delete/<int:schedule_id>', methods=['POST'])
@admin_or_manager_required
def delete_schedule(schedule_id):
    # 仅admin可删除
    if session.get('role') != 'admin':
        flash('只有管理员可以删除排课！')
        return redirect(url_for('schedule_list'))
    conn = get_db_connection()
    schedule = conn.execute('SELECT * FROM schedule WHERE id=?', (schedule_id,)).fetchone()
    before_content = json.dumps(dict(schedule)) if schedule else None
    conn.execute('DELETE FROM schedule WHERE id=?', (schedule_id,))
    conn.commit()
    # delete_schedule 日志
    conn.execute('INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)', (None, 'delete_schedule', session.get('username'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), before_content, None))
    conn.close()
    flash('排课已删除！')
    return redirect(url_for('schedule_list'))

@app.route('/schedules/consume/<int:schedule_id>', methods=['POST'])
@admin_or_manager_required
def consume_schedule(schedule_id):
    conn = get_db_connection()
    schedule = conn.execute('SELECT * FROM schedule WHERE id=?', (schedule_id,)).fetchone()
    # manager只能消课自己排的课
    if session.get('role') == 'manager' and schedule and schedule['teacher'] != session.get('username'):
        conn.close()
        flash('只能消课自己排的课！')
        return redirect(url_for('schedule_list'))
    if not schedule:
        conn.close()
        flash('排课不存在！')
        return redirect(url_for('schedule_list'))
    topic = request.form['topic']
    note = request.form['note']
    hours_consumed = int(request.form['hours_consumed'])
    operator = session.get('username')
    date = schedule['date']
    time = schedule['time']
    course_id = schedule['course_id']
    teacher = schedule['teacher']
    student_ids = schedule['student_ids'].split(',')
    cursor = conn.cursor()
    for student_id in student_ids:
        cursor.execute(
            'INSERT INTO record (student_id, course_id, hours_consumed, date, note, topic, teacher, operator) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (student_id, course_id, hours_consumed, date, note, topic, teacher, operator)
        )
        record_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)',
            (record_id, 'add', operator, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None, json.dumps({
                'student_id': student_id, 'course_id': course_id, 'hours_consumed': hours_consumed, 'date': date, 'note': note, 'topic': topic, 'teacher': teacher, 'operator': operator
            }))
        )
    conn.commit()
    # 更新排课状态为已消课
    conn.execute('UPDATE schedule SET status=? WHERE id=?', ('已消课', schedule_id))
    conn.commit()
    # consume_schedule 日志
    conn.execute('INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)', (None, 'consume_schedule', session.get('username'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), json.dumps(dict(schedule)), json.dumps({'topic': topic, 'note': note, 'hours_consumed': hours_consumed})))
    conn.close()
    flash('点名消课成功！')
    return redirect(url_for('schedule_list'))

@app.route('/report')
@admin_or_manager_required
def report():
    conn = get_db_connection()
    # 总排课数
    total_schedules = conn.execute('SELECT COUNT(*) FROM schedule').fetchone()[0]
    # 总消课数
    total_consumed = conn.execute("SELECT COUNT(*) FROM schedule WHERE status='已消课'").fetchone()[0]
    # 消课率
    consume_rate = round((total_consumed / total_schedules) * 100, 2) if total_schedules else 0
    # 按课程统计排课数、消课数
    course_stats = conn.execute('''
        SELECT c.name, COUNT(s.id) as total, SUM(CASE WHEN s.status='已消课' THEN 1 ELSE 0 END) as consumed
        FROM schedule s JOIN course c ON s.course_id = c.id
        GROUP BY c.id
    ''').fetchall()
    # 按老师统计
    teacher_stats = conn.execute('''
        SELECT s.teacher, COUNT(s.id) as total, SUM(CASE WHEN s.status='已消课' THEN 1 ELSE 0 END) as consumed
        FROM schedule s
        GROUP BY s.teacher
    ''').fetchall()
    # 按学生统计（每个学生被排课多少次、消课多少次）
    student_stats = []
    students = {row['id']: row['name'] for row in conn.execute('SELECT * FROM student')}
    for s in conn.execute('SELECT * FROM schedule'):
        for sid in s['student_ids'].split(','):
            name = students.get(int(sid), f'ID{sid}')
            stat = next((x for x in student_stats if x['name']==name), None)
            if not stat:
                stat = {'name': name, 'total': 0, 'consumed': 0}
                student_stats.append(stat)
            stat['total'] += 1
            if s['status'] == '已消课':
                stat['consumed'] += 1
    conn.close()
    return render_template('report.html', total_schedules=total_schedules, total_consumed=total_consumed, consume_rate=consume_rate, course_stats=course_stats, teacher_stats=teacher_stats, student_stats=student_stats)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
