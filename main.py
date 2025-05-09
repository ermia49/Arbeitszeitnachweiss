import os
import pandas as pd
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, session, send_file
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from werkzeug.utils import secure_filename
from models import db, User, Driver
from forms import LoginForm, DriverForm, UserForm, ProcessForm
from utils import generate_pdf, process_files, calculate_meal_allowance
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-for-testing')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI', 'sqlite:///arbeitszeitnachweise.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
app.config['TEMP_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_first_request
def create_tables():
    db.create_all()
    # Create admin user if no users exist
    if not User.query.first():
        admin = User(username='admin', email='admin@example.com', is_admin=True)
        admin.set_password('admin')
        db.session.add(admin)
        db.session.commit()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next', url_for('index'))
            return redirect(next_page)
        flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Driver management routes
@app.route('/drivers')
@login_required
def drivers():
    drivers_list = Driver.query.all()
    return render_template('drivers.html', drivers=drivers_list)

@app.route('/drivers/add', methods=['GET', 'POST'])
@login_required
def add_driver():
    form = DriverForm()
    if form.validate_on_submit():
        driver = Driver(
            name=form.name.data,
            employee_id=form.employee_id.data,
            role=form.role.data,
            contract=form.contract.data,
            schedule=form.schedule.data,
            pay=form.pay.data,
            is_active=form.is_active.data
        )
        db.session.add(driver)
        db.session.commit()
        flash('Driver added successfully', 'success')
        return redirect(url_for('drivers'))
    return render_template('driver_form.html', form=form, title='Add Driver')

@app.route('/drivers/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_driver(id):
    driver = Driver.query.get_or_404(id)
    form = DriverForm(obj=driver)
    if form.validate_on_submit():
        driver.name = form.name.data
        driver.employee_id = form.employee_id.data
        driver.role = form.role.data
        driver.contract = form.contract.data
        driver.schedule = form.schedule.data
        driver.pay = form.pay.data
        driver.is_active = form.is_active.data
        db.session.commit()
        flash('Driver updated successfully', 'success')
        return redirect(url_for('drivers'))
    return render_template('driver_form.html', form=form, title='Edit Driver')

@app.route('/drivers/toggle/<int:id>')
@login_required
def toggle_driver(id):
    driver = Driver.query.get_or_404(id)
    driver.is_active = not driver.is_active
    db.session.commit()
    flash(f"Driver {driver.name} is now {'active' if driver.is_active else 'inactive'}", 'success')
    return redirect(url_for('drivers'))

# User management routes (admin only)
@app.route('/users')
@login_required
def users():
    if not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    users_list = User.query.all()
    return render_template('users.html', users=users_list)

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    form = UserForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            is_admin=form.is_admin.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('User added successfully', 'success')
        return redirect(url_for('users'))
    return render_template('user_form.html', form=form, title='Add User')

@app.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    if not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    form = UserForm(obj=user)
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        user.is_admin = form.is_admin.data
        if form.password.data:
            user.set_password(form.password.data)
        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('users'))
    return render_template('user_form.html', form=form, title='Edit User')

# File processing routes
@app.route('/process', methods=['GET', 'POST'])
@login_required
def process():
    form = ProcessForm()
    if form.validate_on_submit():
        # Save uploaded files
        fahrtenbuch_file = form.fahrtenbuch.data
        fahreruebersicht_file = form.fahreruebersicht.data
        month_year = form.month_year.data
        include_inactive = form.include_inactive.data
        special_days = form.special_days.data
        
        fahrtenbuch_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                      secure_filename(fahrtenbuch_file.filename))
        fahreruebersicht_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                           secure_filename(fahreruebersicht_file.filename))
        
        fahrtenbuch_file.save(fahrtenbuch_path)
        fahreruebersicht_file.save(fahreruebersicht_path)
        
        # Process files
        try:
            processed_data = process_files(fahrtenbuch_path, fahreruebersicht_path, month_year, 
                                          include_inactive, special_days)
            session['processed_data'] = processed_data
            session['month_year'] = month_year.strftime('%Y-%m')
            flash('Files processed successfully', 'success')
            return redirect(url_for('review'))
        except Exception as e:
            flash(f'Error processing files: {str(e)}', 'danger')
    
    return render_template('process.html', form=form)

@app.route('/review')
@login_required
def review():
    if 'processed_data' not in session:
        flash('No processed data available. Please upload files first.', 'warning')
        return redirect(url_for('process'))
    
    processed_data = session['processed_data']
    month_year = session['month_year']
    return render_template('review.html', processed_data=processed_data, month_year=month_year)

@app.route('/edit/<driver_name>', methods=['GET', 'POST'])
@login_required
def edit_work_time(driver_name):
    if 'processed_data' not in session:
        flash('No processed data available. Please upload files first.', 'warning')
        return redirect(url_for('process'))
    
    processed_data = session['processed_data']
    if driver_name not in processed_data:
        flash('Driver not found', 'danger')
        return redirect(url_for('review'))
    
    driver_data = processed_data[driver_name]
    
    if request.method == 'POST':
        # Update driver data based on form submission
        for day in driver_data['days']:
            day_str = str(day['date'])
            if day_str in request.form:
                day_data = request.form[day_str].split(',')
                if len(day_data) >= 5:
                    day['work_hours'] = float(day_data[0]) if day_data[0] else 0
                    day['break_time'] = float(day_data[1]) if day_data[1] else 0
                    day['night_hours'] = float(day_data[2]) if day_data[2] else 0
                    day['sunday_hours'] = float(day_data[3]) if day_data[3] else 0
                    day['holiday_hours'] = float(day_data[4]) if day_data[4] else 0
                if len(day_data) >= 6:
                    day['status'] = day_data[5]
        
        # Recalculate totals
        total_work_hours = sum(day['work_hours'] for day in driver_data['days'])
        driver_data['total_work_hours'] = total_work_hours
        driver_data['total_break_time'] = sum(day['break_time'] for day in driver_data['days'])
        driver_data['total_night_hours'] = sum(day['night_hours'] for day in driver_data['days'])
        driver_data['total_sunday_hours'] = sum(day['sunday_hours'] for day in driver_data['days'])
        driver_data['total_holiday_hours'] = sum(day['holiday_hours'] for day in driver_data['days'])
        driver_data['meal_allowance'] = calculate_meal_allowance(total_work_hours)
        
        # Update session data
        processed_data[driver_name] = driver_data
        session['processed_data'] = processed_data
        
        flash('Work time data updated successfully', 'success')
        return redirect(url_for('review'))
    
    return render_template('edit_work_time.html', driver_name=driver_name, driver_data=driver_data)

@app.route('/generate')
@login_required
def generate():
    if 'processed_data' not in session:
        flash('No processed data available. Please upload files first.', 'warning')
        return redirect(url_for('process'))
    
    processed_data = session['processed_data']
    month_year = session['month_year']
    
    # Create temp directory for PDF files
    temp_dir = tempfile.mkdtemp(dir=app.config['TEMP_FOLDER'])
    pdf_files = []
    
    # Generate PDF for each driver
    for driver_name, driver_data in processed_data.items():
        pdf_path = os.path.join(temp_dir, f"{driver_name}_{month_year}.pdf")
        generate_pdf(driver_name, driver_data, month_year, pdf_path)
        pdf_files.append(pdf_path)
    
    # Create ZIP file with all PDFs
    zip_filename = f"arbeitszeitnachweise_{month_year}.zip"
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for pdf_file in pdf_files:
            zipf.write(pdf_file, os.path.basename(pdf_file))
    
    # Save to session for download page
    session['pdf_files'] = pdf_files
    session['zip_path'] = zip_path
    
    return redirect(url_for('download'))

@app.route('/download')
@login_required
def download():
    if 'pdf_files' not in session or 'zip_path' not in session:
        flash('No generated reports available. Please process files first.', 'warning')
        return redirect(url_for('process'))
    
    pdf_files = session['pdf_files']
    zip_path = session['zip_path']
    
    return render_template('download.html', pdf_files=pdf_files, zip_path=zip_path)

@app.route('/download/zip')
@login_required
def download_zip():
    if 'zip_path' not in session:
        flash('No ZIP file available for download.', 'warning')
        return redirect(url_for('process'))
    
    zip_path = session['zip_path']
    return send_file(zip_path, as_attachment=True)

@app.route('/download/pdf/<filename>')
@login_required
def download_pdf(filename):
    if 'pdf_files' not in session:
        flash('No PDF files available for download.', 'warning')
        return redirect(url_for('process'))
    
    for pdf_path in session['pdf_files']:
        if os.path.basename(pdf_path) == filename:
            return send_file(pdf_path, as_attachment=True)
    
    flash('PDF file not found.', 'danger')
    return redirect(url_for('download'))

if __name__ == '__main__':
    app.run(debug=True)
