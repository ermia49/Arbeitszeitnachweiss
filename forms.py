from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SelectField, TextAreaField, DateField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from models import User, Driver
from datetime import datetime

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[Length(min=6, max=40)])
    password2 = PasswordField('Confirm Password', validators=[EqualTo('password')])
    is_admin = BooleanField('Admin')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already in use.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already in use.')

class DriverForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    employee_id = StringField('Employee ID')
    role = StringField('Role')
    contract = StringField('Contract Type')
    schedule = StringField('Schedule')
    pay = StringField('Pay Rate')
    is_active = BooleanField('Active')
    
    def validate_employee_id(self, employee_id):
        if employee_id.data:
            driver = Driver.query.filter_by(employee_id=employee_id.data).first()
            if driver:
                raise ValidationError('Employee ID already in use.')

class ProcessForm(FlaskForm):
    fahrtenbuch = FileField('Fahrtenbuch (CSV/Excel)', validators=[
        FileRequired(),
        FileAllowed(['csv', 'xlsx', 'xls'], 'CSV or Excel files only')
    ])
    fahreruebersicht = FileField('Fahrerübersicht (CSV/Excel)', validators=[
        FileRequired(),
        FileAllowed(['csv', 'xlsx', 'xls'], 'CSV or Excel files only')
    ])
    month_year = DateField('Month/Year', validators=[DataRequired()], 
                          default=datetime.today().replace(day=1))
    include_inactive = BooleanField('Include Inactive Drivers')
    special_days = TextAreaField('Special Days (format: YYYY-MM-DD,type - e.g., 2023-05-01,sick)')
