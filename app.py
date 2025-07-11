from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
import pandas as pd
from flask import send_file
import io
from functools import wraps
import os
import json
from pypinyin import lazy_pinyin, Style
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

EMAIL_CONFIG_FILE = 'email_config.json'

def load_email_config():
    try:
        with open(EMAIL_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_email_config(config):
    with open(EMAIL_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

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
    forgot_tip = None
    if request.method == 'POST':
        login_id = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        # 先按用户名查找
        user = conn.execute('SELECT * FROM user WHERE username = ? AND password = ?', (login_id, password)).fetchone()
        # 如果用户名查不到，再按邮箱查找
        if not user:
            user = conn.execute('SELECT * FROM user WHERE email = ? AND password = ?', (login_id, password)).fetchone()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            conn.close()
            return redirect(url_for('index'))
        else:
            # 检查该用户名是否为普通用户
            u = conn.execute('SELECT * FROM user WHERE username = ? OR email = ?', (login_id, login_id)).fetchone()
            if u and u['role'] == 'user':
                forgot_tip = '如忘记密码请联系上课老师'
            error = '用户名/邮箱或密码错误'
        conn.close()
    return render_template('login.html', error=error, forgot_tip=forgot_tip)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- 需要登录的页面 ---
@app.route('/', methods=['GET'])
@login_required
def index():
    conn = get_db_connection()
    search_name = request.args.get('search_name', '').strip().lower()
    course_filter = request.args.get('course_filter', '').strip()
    export = request.args.get('export', '')
    # 获取所有学生
    students = conn.execute('SELECT * FROM student').fetchall()
    # 获取所有课程
    courses = {c['id']: c for c in conn.execute('SELECT * FROM course').fetchall()}
    course_list = list(courses.values())
    # 获取所有学生-课程关联
    sc_rows = conn.execute('SELECT * FROM student_course').fetchall()
    # 获取所有消课记录
    records = conn.execute('''
        SELECT r.*, s.name as student_name, c.name as course_name
        FROM record r
        JOIN student s ON r.student_id = s.id
        JOIN course c ON r.course_id = c.id
        ORDER BY r.date DESC
        ''').fetchall()
    # 聚合每个学生的课程信息
    student_info = {}
    role = session.get('role')
    username = session.get('username')
    for s in students:
        name = s['name'].lower().replace(' ', '')
        pinyin_full = ''.join(lazy_pinyin(s['name'], style=Style.NORMAL)).lower()
        pinyin_abbr = ''.join([p[0] for p in lazy_pinyin(s['name'], style=Style.NORMAL)]).lower()
        # 权限过滤：普通用户只能看自己
        if role not in ['admin', 'manager']:
            if s['name'] != username:
                continue
        # 仅有搜索条件时才过滤
        if search_name:
            if (search_name not in name and
                search_name not in pinyin_full and
                search_name not in pinyin_abbr):
                continue
        s_courses = []
        for sc in sc_rows:
            if sc['student_id'] == s['id']:
                course = courses.get(sc['course_id'])
                if not course:
                    continue
                # 课程筛选
                if course_filter and str(course['id']) != course_filter:
                    continue
                # 统计已上课时
                consumed = sum(r['hours_consumed'] for r in records if r['student_id']==s['id'] and r['course_id']==sc['course_id'])
                s_courses.append({
                    'course_name': course['name'],
                    'total_hours': sc['total_hours'],
                    'price': sc['price'],
                    'consumed_hours': consumed,
                    'remaining_hours': sc['total_hours'] - consumed
                })
        # 该学生所有消课记录
        s_records = [r for r in records if r['student_id']==s['id'] and (not course_filter or str(r['course_id'])==course_filter)]
        # 只显示有课程或有消课记录的学生
        if not s_courses and not s_records:
            continue
        student_info[s['id']] = {
            'student': s,
            'courses': s_courses,
            'records': s_records
        }
    # 导出Excel
    if export == '1':
        import pandas as pd
        from io import BytesIO
        rows = []
        for sid, info in student_info.items():
            for c in info['courses']:
                rows.append({
                    '学生': info['student']['name'],
                    '联系方式': info['student']['contact'],
                    '课程': c['course_name'],
                    '总课时': c['total_hours'],
                    '单价': c['price'],
                    '已上课时': c['consumed_hours'],
                    '剩余课时': c['remaining_hours']
                })
        df = pd.DataFrame(rows)
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='学生课程信息.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    # 课程剩余详情筛选参数
    student_name = request.args.get('student_name', '').strip() if role in ['admin', 'manager'] else ''
    course_name = request.args.get('course_name', '').strip() if role in ['admin', 'manager'] else ''
    sort_by = request.args.get('sort_by', 'remain_hours')
    sort_order = request.args.get('sort_order', 'desc')
    # 查询所有学生-课程关联及相关信息
    query = '''
        SELECT s.name as student_name, c.name as course_name, sc.total_hours, sc.price,
               IFNULL(SUM(r.hours_consumed), 0) as consumed_hours,
               (sc.total_hours - IFNULL(SUM(r.hours_consumed), 0)) as remain_hours,
               MIN(r.date) as first_class_time, MAX(r.date) as last_class_time
        FROM student_course sc
        JOIN student s ON sc.student_id = s.id
        JOIN course c ON sc.course_id = c.id
        LEFT JOIN record r ON r.student_id = s.id AND r.course_id = c.id
        WHERE 1=1
    '''
    params = []
    if role not in ['admin', 'manager']:
        # 普通用户只能看到与自己手机号绑定的学生
        student = conn.execute('SELECT * FROM student WHERE contact=?', (username,)).fetchone()
        if student:
            query += ' AND s.id=?'
            params.append(student['id'])
        else:
            query += ' AND 1=0'  # 没有绑定学生
    else:
        if student_name:
            query += ' AND s.name LIKE ?'
            params.append(f'%{student_name}%')
        if course_name:
            query += ' AND c.name LIKE ?'
            params.append(f'%{course_name}%')
    query += ' GROUP BY sc.id'
    # 排序
    sort_map = {
        'student': 'student_name',
        'course': 'course_name',
        'total_hours': 'total_hours',
        'remain_hours': 'remain_hours',
        'first_class_time': 'first_class_time',
        'last_class_time': 'last_class_time'
    }
    sort_col = sort_map.get(sort_by, 'remain_hours')
    query += f' ORDER BY {sort_col} {"DESC" if sort_order=="desc" else "ASC"}'
    remain_rows = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('index.html', student_info=student_info, search_name=search_name, course_list=course_list, course_filter=course_filter, remain_rows=remain_rows, request=request, role=role)

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
        course_selects = request.form.getlist('course_name_select')
        custom_courses = request.form.getlist('custom_course_name')
        total_hours_list = request.form.getlist('total_hours')
        price_list = request.form.getlist('price')
        email = request.form.get('email', '').strip()
        
        # 先插入学生信息
        cursor.execute('INSERT INTO student (name, contact) VALUES (?, ?)', (name, contact))
        student_id = cursor.lastrowid
        
        # 自动创建普通用户账号（用户名为学生姓名，密码为手机号，邮箱可选）
        user_exists = cursor.execute('SELECT 1 FROM user WHERE username=?', (name,)).fetchone()
        if not user_exists:
            cursor.execute('INSERT INTO user (username, password, role, email) VALUES (?, ?, ?, ?)', (name, contact, 'user', email))
        
        # 插入学生课程信息
        for idx, course_sel in enumerate(course_selects):
            if course_sel == 'other':
                course_name = custom_courses[idx].strip()
            else:
                course_name = course_sel
            if course_name and total_hours_list[idx] and price_list[idx]:
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
        flash('学生添加成功！')
        return redirect(url_for('students'))
    return render_template('add_student.html')

@app.route('/students/delete/<int:student_id>', methods=['POST'])
@admin_or_manager_required
def delete_student(student_id):
    conn = get_db_connection()
    
    # 先获取学生信息，用于删除对应的用户账号
    student = conn.execute('SELECT * FROM student WHERE id = ?', (student_id,)).fetchone()
    
    if student:
        # 删除对应的普通用户账号（如果存在）
        # 根据学生姓名查找对应的用户账号
        conn.execute('DELETE FROM user WHERE username = ? AND role = "user"', (student['name'],))
        
        # 删除学生相关的所有数据
        # 删除学生课程记录
        conn.execute('DELETE FROM student_course WHERE student_id = ?', (student_id,))
        # 删除学生消费记录
        conn.execute('DELETE FROM record WHERE student_id = ?', (student_id,))
        # 删除学生排课记录
        conn.execute("DELETE FROM schedule WHERE ',' || student_ids || ',' LIKE ?", (f'%,{student_id},%',))
        # 最后删除学生本身
        conn.execute('DELETE FROM student WHERE id = ?', (student_id,))
        
        conn.commit()
        flash('学生及其相关数据已删除')
    else:
        flash('学生不存在')
    
    conn.close()
    return redirect(url_for('students'))

@app.route('/students/edit/<int:student_id>', methods=['GET', 'POST'])
@admin_or_manager_required
def edit_student(student_id):
    conn = get_db_connection()
    student = conn.execute('SELECT * FROM student WHERE id = ?', (student_id,)).fetchone()
    if not student:
        conn.close()
        flash('学生不存在！')
        return redirect(url_for('students'))
    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        conn.execute('UPDATE student SET name=?, contact=? WHERE id=?', (name, contact, student_id))
        conn.commit()
        conn.close()
        flash('学生信息已更新！')
        return redirect(url_for('students'))
    conn.close()
    return render_template('edit_student.html', student=student)

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
    import traceback
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        email = request.form['email']
        print(f"[DEBUG] add_user: username={username}, password={password}, role={role}, email={email}")
        # 只有admin能添加manager，admin和manager都不能添加admin
        if role == 'admin':
            flash('不能添加admin账号')
            print('[DEBUG] 拒绝添加admin账号')
            return redirect(url_for('user_list'))
        if session.get('role') != 'admin' and role == 'manager':
            flash('无权限添加该类型用户')
            print('[DEBUG] 非admin尝试添加manager')
            return redirect(url_for('user_list'))
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO user (username, password, role, email) VALUES (?, ?, ?, ?)', (username, password, role, email))
            conn.commit()
            flash('添加成功')
            print('[DEBUG] 添加用户成功')
        except Exception as e:
            flash(f'添加失败：{e}')
            print('[ERROR] 添加用户失败:', e)
            traceback.print_exc()
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
        email = request.form['email']
        # manager不能将user改为admin/manager
        if session.get('role') != 'admin' and role in ['admin', 'manager']:
            flash('无权限修改为该类型用户')
            return redirect(url_for('user_list'))
        try:
            if password:
                conn.execute('UPDATE user SET username=?, password=?, role=?, email=? WHERE id=?', (username, password, role, email, user_id))
            else:
                conn.execute('UPDATE user SET username=?, role=?, email=? WHERE id=?', (username, role, email, user_id))
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
    schedules = conn.execute('SELECT * FROM schedule ORDER BY start_datetime DESC').fetchall()
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
    # 获取所有有邮箱的manager/admin账号
    teachers = conn.execute("SELECT * FROM user WHERE role IN ('admin', 'manager') AND email IS NOT NULL AND email != ''").fetchall()
    if request.method == 'POST':
        course_id = request.form['course_id']
        student_ids = ','.join(request.form.getlist('student_ids'))
        teacher = request.form['teacher']
        start_datetime = request.form['start_datetime']
        end_datetime = request.form['end_datetime']
        note = request.form['note']
        conn.execute('INSERT INTO schedule (course_id, student_ids, teacher, start_datetime, end_datetime, note) VALUES (?, ?, ?, ?, ?, ?)',
                     (course_id, student_ids, teacher, start_datetime, end_datetime, note))
        conn.commit()
        conn.close()
        flash('排课添加成功')
        return redirect(url_for('schedule_list'))
    conn.close()
    return render_template('add_schedule.html', courses=courses, students=students, teachers=teachers)

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
        start_datetime = request.form['start_datetime']
        end_datetime = request.form['end_datetime']
        note = request.form['note']
        # 冲突检测
        for sid in student_ids:
            conflict = conn.execute('SELECT * FROM schedule WHERE ((start_datetime<=? AND end_datetime>=?) OR (start_datetime<=? AND end_datetime>=?)) AND instr(student_ids, ?) > 0 AND id!=?', (end_datetime, end_datetime, start_datetime, start_datetime, sid, schedule_id)).fetchone()
            if conflict:
                flash(f'学生ID {sid} 在该时间段已排课，请检查！')
                conn.close()
                return redirect(request.url)
        student_ids_str = ','.join(student_ids)
        conn.execute('UPDATE schedule SET course_id=?, student_ids=?, teacher=?, start_datetime=?, end_datetime=?, note=? WHERE id=?',
                     (course_id, student_ids_str, teacher, start_datetime, end_datetime, note, schedule_id))
        conn.commit()
        # edit_schedule 日志
        conn.execute('INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)', (None, 'edit_schedule', session.get('username'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), json.dumps(dict(schedule)), json.dumps({'course_id': course_id, 'student_ids': student_ids_str, 'teacher': teacher, 'start_datetime': start_datetime, 'end_datetime': end_datetime, 'note': note})))
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
    start_datetime = schedule['start_datetime']
    end_datetime = schedule['end_datetime']
    course_id = schedule['course_id']
    teacher = schedule['teacher']
    student_ids = schedule['student_ids'].split(',')
    cursor = conn.cursor()
    for student_id in student_ids:
        cursor.execute(
            'INSERT INTO record (student_id, course_id, hours_consumed, date, note, topic, teacher, operator) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (student_id, course_id, hours_consumed, start_datetime, note, topic, teacher, operator)
        )
        record_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO record_log (record_id, operation_type, operator, operation_time, before_content, after_content) VALUES (?, ?, ?, ?, ?, ?)',
            (record_id, 'add', operator, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), None, json.dumps({
                'student_id': student_id, 'course_id': course_id, 'hours_consumed': hours_consumed, 'date': start_datetime, 'note': note, 'topic': topic, 'teacher': teacher, 'operator': operator
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

# 课程管理相关路由
@app.route('/courses')
@admin_or_manager_required
def course_list():
    conn = get_db_connection()
    courses = conn.execute('SELECT * FROM course').fetchall()
    conn.close()
    return render_template('courses.html', courses=courses)

@app.route('/courses/add', methods=['GET', 'POST'])
@admin_or_manager_required
def add_course():
    if request.method == 'POST':
        name_sel = request.form['name_select']
        if name_sel == 'other':
            name = request.form.get('custom_name', '').strip()
        else:
            name = name_sel
        total_hours = request.form['total_hours']
        price = request.form['price']
        conn = get_db_connection()
        # 检查是否重名
        exists = conn.execute('SELECT 1 FROM course WHERE name=?', (name,)).fetchone()
        if exists:
            conn.close()
            flash('课程已存在！')
            return redirect(url_for('course_list'))
        conn.execute('INSERT INTO course (name, total_hours, price) VALUES (?, ?, ?)', (name, total_hours, price))
        conn.commit()
        conn.close()
        flash('课程添加成功！')
        return redirect(url_for('course_list'))
    return render_template('add_course.html')

@app.route('/courses/delete/<int:course_id>', methods=['POST'])
@admin_or_manager_required
def delete_course(course_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM course WHERE id=?', (course_id,))
    conn.commit()
    conn.close()
    flash('课程已删除！')
    return redirect(url_for('course_list'))

@app.route('/email_config', methods=['GET', 'POST'])
@admin_required
def email_config():
    config = load_email_config()
    if request.method == 'POST':
        qq_email = request.form['qq_email']
        qq_auth_code = request.form['qq_auth_code']
        config['qq_email'] = qq_email
        config['qq_auth_code'] = qq_auth_code
        save_email_config(config)
        flash('邮箱配置已保存')
        return redirect(url_for('email_config'))
    return render_template('email_config.html', config=config)

def send_email(to_email, subject, content, html=False):
    config = load_email_config()
    from_email = config.get('qq_email')
    auth_code = config.get('qq_auth_code')
    if not from_email or not auth_code:
        return False, '请先在邮箱配置中填写发件邮箱和授权码'
    try:
        msg = MIMEText(content, 'html' if html else 'plain', 'utf-8')
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = Header(subject, 'utf-8')
        server = smtplib.SMTP_SSL('smtp.qq.com', 465)
        server.login(from_email, auth_code)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()
        return True, '邮件发送成功'
    except Exception as e:
        return False, f'邮件发送失败: {e}'

def get_tomorrow_courses():
    conn = get_db_connection()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    schedules = conn.execute('SELECT * FROM schedule WHERE date(start_datetime)=?', (tomorrow,)).fetchall()
    conn.close()
    return schedules

def get_today_unconsumed_courses():
    conn = get_db_connection()
    today = datetime.now().strftime('%Y-%m-%d')
    # 假设 status 字段为“未消课”或空表示未消课
    schedules = conn.execute('SELECT * FROM schedule WHERE date(end_datetime)=? AND (status IS NULL OR status="未消课")', (today,)).fetchall()
    conn.close()
    return schedules

def send_course_reminders():
    # 上课前一天提醒
    schedules = get_tomorrow_courses()
    for s in schedules:
        conn = get_db_connection()
        teacher = s['teacher']
        user = conn.execute('SELECT * FROM user WHERE username=?', (teacher,)).fetchone()
        # 获取课程名
        course_row = conn.execute('SELECT name FROM course WHERE id=?', (s['course_id'],)).fetchone()
        course_name = course_row['name'] if course_row else s['course_id']
        # 获取学生名
        student_names = []
        for sid in s['student_ids'].split(','):
            stu = conn.execute('SELECT name FROM student WHERE id=?', (sid,)).fetchone()
            if stu: student_names.append(stu['name'])
        conn.close()
        if user and user['email']:
            subject = f"明天有课提醒：{s['start_datetime']} 课程：{course_name}"
            content = f"""
            <html><body>
            <p>老师您好，您<b>明天有一节课安排</b>：</p>
            <ul style='list-style:none;padding-left:0;'>
              <li><b>课程名称：</b>{course_name}</li>
              <li><b>学生名单：</b>{'、'.join(student_names)}</li>
              <li><b>上课时间：</b>{s['start_datetime']}</li>
              <li><b>结束时间：</b>{s['end_datetime']}</li>
              <li><b>备注：</b>{s['note'] or '无'}</li>
            </ul>
            <p style='color:#2563eb;font-weight:bold;'>请提前做好准备，谢谢！</p>
            </body></html>
            """
            send_email(user['email'], subject, content, html=True)
    # 课后提醒消课
    schedules = get_today_unconsumed_courses()
    for s in schedules:
        conn = get_db_connection()
        teacher = s['teacher']
        user = conn.execute('SELECT * FROM user WHERE username=?', (teacher,)).fetchone()
        # 获取课程名
        course_row = conn.execute('SELECT name FROM course WHERE id=?', (s['course_id'],)).fetchone()
        course_name = course_row['name'] if course_row else s['course_id']
        # 获取学生名
        student_names = []
        for sid in s['student_ids'].split(','):
            stu = conn.execute('SELECT name FROM student WHERE id=?', (sid,)).fetchone()
            if stu: student_names.append(stu['name'])
        conn.close()
        if user and user['email']:
            subject = f"今日课程消课提醒：{s['start_datetime']} 课程：{course_name}"
            content = f"""
            <html><body>
            <p>老师您好，您<b>今日有一节课尚未消课</b>：</p>
            <ul style='list-style:none;padding-left:0;'>
              <li><b>课程名称：</b>{course_name}</li>
              <li><b>学生名单：</b>{'、'.join(student_names)}</li>
              <li><b>上课时间：</b>{s['start_datetime']}</li>
              <li><b>结束时间：</b>{s['end_datetime']}</li>
              <li><b>备注：</b>{s['note'] or '无'}</li>
            </ul>
            <p style='color:#e53935;font-weight:bold;'>请及时登录系统进行消课操作，谢谢！</p>
            </body></html>
            """
            send_email(user['email'], subject, content, html=True)

# 启动APScheduler
scheduler = BackgroundScheduler()
scheduler.add_job(send_course_reminders, 'cron', hour=20, minute=0)  # 每天20:00执行
scheduler.start()

@app.route('/email_test', methods=['GET', 'POST'])
@admin_required
def email_test():
    msg = None
    if request.method == 'POST':
        to_email = request.form['to_email']
        subject = request.form['subject']
        content = request.form['content']
        success, info = send_email(to_email, subject, content)
        msg = info
    return render_template('email_test.html', msg=msg)

@app.route('/remind_all_teachers', methods=['POST'])
@admin_required
def remind_all_teachers():
    try:
        send_course_reminders()
        flash('已一键提醒所有待上课和待消课的老师！')
    except Exception as e:
        flash(f'提醒失败：{e}')
    return redirect(url_for('index'))

@app.route('/student_course_manage', methods=['GET'])
@admin_or_manager_required
def student_course_manage():
    conn = get_db_connection()
    # 获取筛选参数
    student_name = request.args.get('student_name', '').strip()
    course_name = request.args.get('course_name', '').strip()
    min_total_hours = request.args.get('min_total_hours', '')
    max_total_hours = request.args.get('max_total_hours', '')
    min_remain_hours = request.args.get('min_remain_hours', '')
    max_remain_hours = request.args.get('max_remain_hours', '')
    start_time = request.args.get('start_time', '')
    end_time = request.args.get('end_time', '')
    sort_by = request.args.get('sort_by', 'student')
    sort_order = request.args.get('sort_order', 'asc')

    # 查询所有学生-课程关联及相关信息
    query = '''
        SELECT s.name as student_name, c.name as course_name, sc.total_hours, sc.price,
               IFNULL(SUM(r.hours_consumed), 0) as consumed_hours,
               (sc.total_hours - IFNULL(SUM(r.hours_consumed), 0)) as remain_hours,
               MIN(r.date) as first_class_time, MAX(r.date) as last_class_time
        FROM student_course sc
        JOIN student s ON sc.student_id = s.id
        JOIN course c ON sc.course_id = c.id
        LEFT JOIN record r ON r.student_id = s.id AND r.course_id = c.id
        WHERE 1=1
    '''
    params = []
    if student_name:
        query += ' AND s.name LIKE ?'
        params.append(f'%{student_name}%')
    if course_name:
        query += ' AND c.name LIKE ?'
        params.append(f'%{course_name}%')
    query += ' GROUP BY sc.id'
    # 课时筛选
    if min_total_hours:
        query += ' HAVING total_hours >= ?'
        params.append(min_total_hours)
    if max_total_hours:
        query += ' AND total_hours <= ?'
        params.append(max_total_hours)
    if min_remain_hours:
        query += ' AND remain_hours >= ?'
        params.append(min_remain_hours)
    if max_remain_hours:
        query += ' AND remain_hours <= ?'
        params.append(max_remain_hours)
    # 上课时间筛选
    if start_time:
        query += ' AND first_class_time >= ?'
        params.append(start_time)
    if end_time:
        query += ' AND last_class_time <= ?'
        params.append(end_time)
    # 排序
    sort_map = {
        'student': 'student_name',
        'course': 'course_name',
        'total_hours': 'total_hours',
        'remain_hours': 'remain_hours',
        'first_class_time': 'first_class_time',
        'last_class_time': 'last_class_time'
    }
    sort_col = sort_map.get(sort_by, 'student_name')
    query += f' ORDER BY {sort_col} {"DESC" if sort_order=="desc" else "ASC"}'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('student_course_manage.html', rows=rows, sort_by=sort_by, sort_order=sort_order, request=request)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
