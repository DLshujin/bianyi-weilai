from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
import pandas as pd
from flask import send_file
import io
from functools import wraps
import os

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
    records = conn.execute('''
        SELECT record.id, student.name AS student_name, course.name AS course_name, record.hours_consumed, record.date, record.note, record.topic
        FROM record
        JOIN student ON record.student_id = student.id
        JOIN course ON record.course_id = course.id
        ORDER BY record.date DESC
    ''').fetchall()
    # 查询学生课时余额
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
    conn.close()
    return render_template('index.html', records=records, balances=balances)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    conn = get_db_connection()
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
        conn.execute(
            'INSERT INTO record (student_id, course_id, hours_consumed, date, note, topic, teacher) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (student_id, course_id, hours_consumed, date, note, topic, teacher)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    conn.close()
    return render_template('add.html', students=students, courses=courses)

@app.route('/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
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
        conn.execute('''
            UPDATE record SET student_id=?, course_id=?, hours_consumed=?, date=?, note=?, topic=?, teacher=? WHERE id=?''',
            (student_id, course_id, hours_consumed, date, note, topic, teacher, record_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    conn.close()
    return render_template('edit.html', record=record, students=students, courses=courses)

@app.route('/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM record WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/students')
@login_required
def students():
    conn = get_db_connection()
    students = conn.execute('SELECT * FROM student').fetchall()
    conn.close()
    return render_template('students.html', students=students)

@app.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        course_names = request.form.getlist('course_name')
        total_hours_list = request.form.getlist('total_hours')
        price_list = request.form.getlist('price')
        conn = get_db_connection()
        cursor = conn.cursor()
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
@login_required
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
@admin_required
def user_list():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM user').fetchall()
    conn.close()
    return render_template('users.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
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
@admin_required
def edit_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('用户不存在')
        return redirect(url_for('user_list'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
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
@admin_required
def delete_user(user_id):
    if user_id == 1:
        flash('不能删除admin账号')
        return redirect(url_for('user_list'))
    conn = get_db_connection()
    conn.execute('DELETE FROM user WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('删除成功')
    return redirect(url_for('user_list'))

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
