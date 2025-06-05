from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length
from models import User

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')
            
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

class EmergencyContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    phone_number = StringField('Phone Number')
    email = StringField('Email', validators=[Email()])
    alert_channel = SelectField('Alert Channel', 
                               choices=[('sms', 'SMS'), ('email', 'Email'), 
                                       ('whatsapp', 'WhatsApp'), ('all', 'All')])
    submit = SubmitField('Save Contact')
    
    def validate(self):
        if not super(EmergencyContactForm, self).validate():
            return False
        
        # Ensure at least one contact method is provided based on alert channel
        if self.alert_channel.data in ['sms', 'whatsapp', 'all'] and not self.phone_number.data:
            self.phone_number.errors = ['Phone number is required for SMS or WhatsApp alerts']
            return False
            
        if self.alert_channel.data in ['email', 'all'] and not self.email.data:
            self.email.errors = ['Email is required for email alerts']
            return False
            
        return True

class UserProfileForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    current_password = PasswordField('Current Password')
    new_password = PasswordField('New Password')
    confirm_password = PasswordField('Confirm New Password', validators=[EqualTo('new_password')])
    submit = SubmitField('Update Profile')