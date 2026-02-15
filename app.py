import os
import sqlite3
import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database helper functions
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'faculty', 'admin'))
        )
    ''')
    
    # Create grievances table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grievances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'In Progress', 'Resolved')),
            admin_remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users (id)
        )
    ''')
    
    # Create resources table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            file_path TEXT NOT NULL,
            uploaded_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uploaded_by) REFERENCES users (id)
        )
    ''')
    
    # Create internships table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS internships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            description TEXT,
            deadline DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def seed_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if data already exists
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    # Create sample users
    users = [
        ('Admin User', 'admin@aegis.edu', generate_password_hash('admin123'), 'admin'),
        ('Faculty Member', 'faculty@aegis.edu', generate_password_hash('faculty123'), 'faculty'),
        ('Student One', 'student1@aegis.edu', generate_password_hash('student123'), 'student'),
        ('Student Two', 'student2@aegis.edu', generate_password_hash('student123'), 'student'),
    ]
    
    cursor.executemany('INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)', users)
    
    # Create sample grievances
    grievances = [
        (3, 'Library Book Issue', 'Cannot borrow more than 5 books at a time', 'Pending', None),
        (3, 'Exam Schedule Conflict', 'Have two exams on the same day', 'In Progress', 'Under review'),
        (4, 'Campus WiFi Problem', 'WiFi not working in hostel', 'Resolved', 'Issue resolved - new router installed'),
    ]
    
    cursor.executemany('INSERT INTO grievances (student_id, title, description, status, admin_remark) VALUES (?, ?, ?, ?, ?)', grievances)
    
    # Create sample internships
    internships = [
        ('Software Development Intern', 'Google', 'Work on real-world projects', '2024-12-31'),
        ('Data Science Intern', 'Microsoft', 'Analyze large datasets', '2024-11-15'),
        ('Web Development Intern', 'Amazon', 'Build web applications', '2024-10-30'),
        ('Cybersecurity Intern', 'IBM', 'Security testing and analysis', '2024-12-01'),
    ]
    
    cursor.executemany('INSERT INTO internships (title, company, description, deadline) VALUES (?, ?, ?, ?)', internships)
    
    conn.commit()
    conn.close()
    print("Database seeded with sample data!")

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session or session['role'] not in roles:
                flash('Unauthorized access', 'error')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ==================== AUTH ROUTES ====================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for(f"{session['role']}_dashboard"))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            
            # Redirect based on role
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'faculty':
                return redirect(url_for('faculty_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        # Validate role
        if role not in ['student', 'faculty', 'admin']:
            flash('Invalid role selected', 'error')
            return redirect(url_for('register'))
        
        # Check if email already exists
        conn = get_db_connection()
        existing_user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if existing_user:
            conn.close()
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        # Hash password and create user
        hashed_password = generate_password_hash(password)
        conn.execute('INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)',
                    (name, email, hashed_password, role))
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==================== STUDENT ROUTES ====================

@app.route('/student/dashboard')
@login_required
@role_required(['student'])
def student_dashboard():
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Get grievance stats
    total = conn.execute('SELECT COUNT(*) FROM grievances WHERE student_id = ?', (user_id,)).fetchone()[0]
    resolved = conn.execute('SELECT COUNT(*) FROM grievances WHERE student_id = ? AND status = ?', (user_id, 'Resolved')).fetchone()[0]
    
    # Get recent internships
    internships = conn.execute('SELECT * FROM internships ORDER BY deadline DESC LIMIT 5').fetchall()
    
    conn.close()
    
    return render_template('student/dashboard.html', total=total, resolved=resolved, internships=internships)

@app.route('/student/grievance/new', methods=['GET', 'POST'])
@login_required
@role_required(['student'])
def student_grievance_new():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        
        conn = get_db_connection()
        conn.execute('INSERT INTO grievances (student_id, title, description) VALUES (?, ?, ?)',
                    (session['user_id'], title, description))
        conn.commit()
        conn.close()
        
        flash('Grievance submitted successfully!', 'success')
        return redirect(url_for('student_grievances'))
    
    return render_template('student/grievance_new.html')

@app.route('/student/grievances')
@login_required
@role_required(['student'])
def student_grievances():
    conn = get_db_connection()
    grievances = conn.execute('''
        SELECT g.*, u.name as student_name 
        FROM grievances g 
        JOIN users u ON g.student_id = u.id 
        WHERE g.student_id = ? 
        ORDER BY g.created_at DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()
    
    return render_template('student/grievances.html', grievances=grievances)

@app.route('/student/internships')
@login_required
@role_required(['student'])
def student_internships():
    conn = get_db_connection()
    internships = conn.execute('SELECT * FROM internships ORDER BY deadline DESC').fetchall()
    conn.close()
    
    return render_template('student/internships.html', internships=internships)

@app.route('/student/resources')
@login_required
@role_required(['student'])
def student_resources():
    conn = get_db_connection()
    resources = conn.execute('''
        SELECT r.*, u.name as uploader_name 
        FROM resources r 
        JOIN users u ON r.uploaded_by = u.id 
        ORDER BY r.created_at DESC
    ''').fetchall()
    conn.close()
    
    return render_template('student/resources.html', resources=resources)

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ==================== ADMIN ROUTES ====================

@app.route('/admin/dashboard')
@login_required
@role_required(['admin'])
def admin_dashboard():
    conn = get_db_connection()
    
    # Get stats
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_grievances = conn.execute('SELECT COUNT(*) FROM grievances').fetchone()[0]
    pending_grievances = conn.execute('SELECT COUNT(*) FROM grievances WHERE status = ?', ('Pending',)).fetchone()[0]
    resolved_grievances = conn.execute('SELECT COUNT(*) FROM grievances WHERE status = ?', ('Resolved',)).fetchone()[0]
    total_internships = conn.execute('SELECT COUNT(*) FROM internships').fetchone()[0]
    total_resources = conn.execute('SELECT COUNT(*) FROM resources').fetchone()[0]
    
    conn.close()
    
    return render_template('admin/dashboard.html', 
                         total_users=total_users,
                         total_grievances=total_grievances,
                         pending_grievances=pending_grievances,
                         resolved_grievances=resolved_grievances,
                         total_internships=total_internships,
                         total_resources=total_resources)

@app.route('/admin/grievances')
@login_required
@role_required(['admin'])
def admin_grievances():
    conn = get_db_connection()
    grievances = conn.execute('''
        SELECT g.*, u.name as student_name, u.email as student_email
        FROM grievances g 
        JOIN users u ON g.student_id = u.id 
        ORDER BY g.created_at DESC
    ''').fetchall()
    conn.close()
    
    return render_template('admin/grievances.html', grievances=grievances)

@app.route('/admin/grievance/update/<int:id>', methods=['POST'])
@login_required
@role_required(['admin'])
def admin_grievance_update(id):
    status = request.form['status']
    admin_remark = request.form['admin_remark']
    
    conn = get_db_connection()
    conn.execute('UPDATE grievances SET status = ?, admin_remark = ? WHERE id = ?',
                (status, admin_remark, id))
    conn.commit()
    conn.close()
    
    flash('Grievance updated successfully!', 'success')
    return redirect(url_for('admin_grievances'))

@app.route('/admin/internships', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def admin_internships():
    if request.method == 'POST':
        title = request.form['title']
        company = request.form['company']
        description = request.form['description']
        deadline = request.form['deadline']
        
        conn = get_db_connection()
        conn.execute('INSERT INTO internships (title, company, description, deadline) VALUES (?, ?, ?, ?)',
                    (title, company, description, deadline))
        conn.commit()
        conn.close()
        
        flash('Internship added successfully!', 'success')
        return redirect(url_for('admin_internships'))
    
    conn = get_db_connection()
    internships = conn.execute('SELECT * FROM internships ORDER BY deadline DESC').fetchall()
    conn.close()
    
    return render_template('admin/internships.html', internships=internships)

@app.route('/admin/internship/delete/<int:id>')
@login_required
@role_required(['admin'])
def admin_internship_delete(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM internships WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    flash('Internship deleted successfully!', 'success')
    return redirect(url_for('admin_internships'))

@app.route('/admin/resources', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def admin_resources():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        file = request.files['file']
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            conn = get_db_connection()
            conn.execute('INSERT INTO resources (title, description, file_path, uploaded_by) VALUES (?, ?, ?, ?)',
                        (title, description, filename, session['user_id']))
            conn.commit()
            conn.close()
            
            flash('Resource uploaded successfully!', 'success')
            return redirect(url_for('admin_resources'))
        else:
            flash('Invalid file type', 'error')
    
    conn = get_db_connection()
    resources = conn.execute('''
        SELECT r.*, u.name as uploader_name 
        FROM resources r 
        JOIN users u ON r.uploaded_by = u.id 
        ORDER BY r.created_at DESC
    ''').fetchall()
    conn.close()
    
    return render_template('admin/resources.html', resources=resources)

@app.route('/admin/resources/delete/<int:id>')
@login_required
@role_required(['admin'])
def admin_resource_delete(id):
    conn = get_db_connection()
    resource = conn.execute('SELECT file_path FROM resources WHERE id = ?', (id,)).fetchone()
    
    if resource:
        # Delete file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], resource['file_path'])
        if os.path.exists(file_path):
            os.remove(file_path)
        
        conn.execute('DELETE FROM resources WHERE id = ?', (id,))
        conn.commit()
    
    conn.close()
    
    flash('Resource deleted successfully!', 'success')
    return redirect(url_for('admin_resources'))

@app.route('/admin/users')
@login_required
@role_required(['admin'])
def admin_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users ORDER BY role, name').fetchall()
    conn.close()
    
    return render_template('admin/users.html', users=users)

# ==================== FACULTY ROUTES ====================

@app.route('/faculty/dashboard')
@login_required
@role_required(['faculty'])
def faculty_dashboard():
    conn = get_db_connection()
    
    # Get stats
    total_grievances = conn.execute('SELECT COUNT(*) FROM grievances').fetchone()[0]
    total_resources = conn.execute('SELECT COUNT(*) FROM resources').fetchone()[0]
    
    conn.close()
    
    return render_template('faculty/dashboard.html', 
                         total_grievances=total_grievances,
                         total_resources=total_resources)

@app.route('/faculty/resources', methods=['GET', 'POST'])
@login_required
@role_required(['faculty'])
def faculty_resources():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        file = request.files['file']
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            conn = get_db_connection()
            conn.execute('INSERT INTO resources (title, description, file_path, uploaded_by) VALUES (?, ?, ?, ?)',
                        (title, description, filename, session['user_id']))
            conn.commit()
            conn.close()
            
            flash('Resource uploaded successfully!', 'success')
            return redirect(url_for('faculty_resources'))
        else:
            flash('Invalid file type', 'error')
    
    conn = get_db_connection()
    resources = conn.execute('''
        SELECT r.*, u.name as uploader_name 
        FROM resources r 
        JOIN users u ON r.uploaded_by = u.id 
        ORDER BY r.created_at DESC
    ''').fetchall()
    conn.close()
    
    return render_template('faculty/resources.html', resources=resources)

if __name__ == '__main__':
    init_db()
    seed_data()
    app.run(debug=True , host='0.0.0.0', port=3122)
