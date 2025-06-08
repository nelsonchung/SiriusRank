from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = 'secret-key-change-me'
DB_PATH = 'data.db'

# Ensure database and tables exist
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        role TEXT NOT NULL
                    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS passwords (
                        user_id INTEGER UNIQUE,
                        password TEXT NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(id)
                    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS classes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL
                    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS subjects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL
                    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS grades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER,
                        class_id INTEGER,
                        subject_id INTEGER,
                        score REAL,
                        FOREIGN KEY(student_id) REFERENCES users(id),
                        FOREIGN KEY(class_id) REFERENCES classes(id),
                        FOREIGN KEY(subject_id) REFERENCES subjects(id)
                    )''')
    conn.commit()
    conn.close()

# Helper to get db connection

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if 'user_id' in session:
        if session['role'] == 'teacher':
            return redirect(url_for('teacher'))
        elif session['role'] == 'admin':
            return redirect(url_for('admin'))
        else:
            return redirect(url_for('student'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO users (username, role) VALUES (?, ?)', (username, role))
            user_id = cur.lastrowid
            hashed = generate_password_hash(password)
            cur.execute('INSERT INTO passwords (user_id, password) VALUES (?, ?)', (user_id, hashed))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            return 'Username already exists'
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, role FROM users WHERE username=?', (username,))
        user = cur.fetchone()
        if user:
            user_id, role = user
            cur.execute('SELECT password FROM passwords WHERE user_id=?', (user_id,))
            pw_row = cur.fetchone()
            if pw_row and check_password_hash(pw_row[0], password):
                session['user_id'] = user_id
                session['role'] = role
                conn.close()
                if role == 'teacher':
                    return redirect(url_for('teacher'))
                elif role == 'admin':
                    return redirect(url_for('admin'))
                else:
                    return redirect(url_for('student'))
        conn.close()
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/teacher', methods=['GET', 'POST'])
def teacher():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == 'POST':
        student_id = request.form['student']
        class_id = request.form['class']
        subject_id = request.form['subject']
        score = request.form['score']
        cur.execute('INSERT INTO grades (student_id, class_id, subject_id, score) VALUES (?, ?, ?, ?)',
                    (student_id, class_id, subject_id, score))
        conn.commit()
    cur.execute('SELECT id, username FROM users WHERE role="student"')
    students = cur.fetchall()
    cur.execute('SELECT id, name FROM classes')
    classes = cur.fetchall()
    cur.execute('SELECT id, name FROM subjects')
    subjects = cur.fetchall()
    conn.close()
    return render_template('teacher.html', students=students, classes=classes, subjects=subjects)

@app.route('/student')
def student():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT subjects.name, classes.name, score
                   FROM grades
                   JOIN subjects ON grades.subject_id = subjects.id
                   JOIN classes ON grades.class_id = classes.id
                   WHERE student_id=?''', (user_id,))
    grades = cur.fetchall()
    cur.execute('SELECT SUM(score), AVG(score) FROM grades WHERE student_id=?', (user_id,))
    total, avg = cur.fetchone()
    conn.close()
    total = total or 0
    avg = avg or 0
    return render_template('student.html', grades=grades, total=total, avg=avg)


@app.route('/manage', methods=['GET', 'POST'])
def manage():
    if 'user_id' not in session or session['role'] not in ('teacher', 'admin'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == 'POST':
        item_type = request.form['type']
        name = request.form['name']
        if item_type == 'class':
            cur.execute('INSERT INTO classes (name) VALUES (?)', (name,))
        elif item_type == 'subject':
            cur.execute('INSERT INTO subjects (name) VALUES (?)', (name,))
        conn.commit()
    cur.execute('SELECT id, name FROM classes')
    classes = cur.fetchall()
    cur.execute('SELECT id, name FROM subjects')
    subjects = cur.fetchall()
    conn.close()
    return render_template('manage.html', classes=classes, subjects=subjects)

@app.route('/admin')
def admin():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM classes')
    classes = cur.fetchall()
    conn.close()
    return render_template('admin.html', classes=classes)

@app.route('/rank/class/<int:class_id>')
def class_rank(class_id):
    if 'user_id' not in session or session['role'] not in ('teacher', 'admin'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT name FROM classes WHERE id=?', (class_id,))
    row = cur.fetchone()
    class_name = row[0] if row else 'Unknown'
    cur.execute('''SELECT users.username, SUM(grades.score) as total
                   FROM grades
                   JOIN users ON grades.student_id = users.id
                   WHERE grades.class_id=?
                   GROUP BY grades.student_id
                   ORDER BY total DESC''', (class_id,))
    ranks = cur.fetchall()
    conn.close()
    return render_template('ranking.html', ranks=ranks, title=f"{class_name} Ranking")

@app.route('/rank/school')
def school_rank():
    if 'user_id' not in session or session['role'] not in ('teacher', 'admin'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT users.username, SUM(grades.score) as total
                   FROM grades
                   JOIN users ON grades.student_id = users.id
                   GROUP BY grades.student_id
                   ORDER BY total DESC''')
    ranks = cur.fetchall()
    conn.close()
    return render_template('ranking.html', ranks=ranks, title='School Ranking')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
