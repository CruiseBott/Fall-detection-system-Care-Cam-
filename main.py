from flask import Flask, render_template, Response, request, jsonify, send_from_directory, redirect, url_for, flash
import os
import queue
from esp32cam_streamer import ESP32CamStreamer
from video import VideoProcessor, VideoStreamer, FileVideoStreamer
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.urls import url_parse
from models import db, User, EmergencyContact, FallDetection
from forms import LoginForm, RegistrationForm, EmergencyContactForm, UserProfileForm
from alerts import AlertSystem
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import json
# Add Flask-SocketIO import
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this to a secure random key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fall_detection.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  # Change this
app.config['MAIL_PASSWORD'] = 'your-app-password'  # Change this
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@gmail.com'  # Change this

# Twilio configuration
app.config['TWILIO_ACCOUNT_SID'] = 'your-twilio-sid'  # Change this
app.config['TWILIO_AUTH_TOKEN'] = 'your-twilio-token'  # Change this
app.config['TWILIO_PHONE_NUMBER'] = '+1234567890'  # Change this
app.config['TWILIO_WHATSAPP_NUMBER'] = '+1234567890'  # Change this

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
alert_system = AlertSystem(app)
# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Global variables
frame_queues = {
    1: queue.Queue(maxsize=10),
    2: queue.Queue(maxsize=10),
    3: queue.Queue(maxsize=10),
    4: queue.Queue(maxsize=10) 
}
ip_addresses = {}
file_streams = {}
model_path = "ok.pt"

# Initialize VideoProcessors for each camera
video_processors = {
    camera_id: VideoProcessor(model_path, frame_queues[camera_id])
    for camera_id in frame_queues
}
video_streamers_file = {
    camera_id: FileVideoStreamer(frame_queues[camera_id])
    for camera_id in frame_queues
}

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

@app.route('/')
def index():
    # Redirect to login page if user is not authenticated
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    # If user is authenticated, show the fall detection page
    return render_template('index.html', title='Fall Detection')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))
        
        # Update last login time
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    
    return render_template('login.html', title='Login', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')
        return redirect(url_for('login'))
    
    return render_template('register.html', title='Register', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get user's emergency contacts
    contacts = EmergencyContact.query.filter_by(user_id=current_user.id).all()
    
    # Get user's fall detections
    detections = FallDetection.query.filter_by(user_id=current_user.id).order_by(FallDetection.timestamp.desc()).limit(10).all()
    
    return render_template('dashboard.html', title='Dashboard', 
                          contacts=contacts, detections=detections)

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('You do not have permission to access the admin dashboard')
        return redirect(url_for('dashboard'))
    
    # Get all users
    users = User.query.all()
    
    # Get all fall detections
    detections = FallDetection.query.order_by(FallDetection.timestamp.desc()).all()
    
    return render_template('admin.html', title='Admin Dashboard', 
                          users=users, detections=detections)

@app.route('/contacts', methods=['GET', 'POST'])
@login_required
def manage_contacts():
    form = EmergencyContactForm()
    
    if form.validate_on_submit():
        contact = EmergencyContact(
            user_id=current_user.id,
            name=form.name.data,
            phone_number=form.phone_number.data,
            email=form.email.data,
            alert_channel=form.alert_channel.data
        )
        db.session.add(contact)
        db.session.commit()
        flash('Emergency contact added successfully!')
        return redirect(url_for('manage_contacts'))
    
    contacts = EmergencyContact.query.filter_by(user_id=current_user.id).all()
    return render_template('contacts.html', title='Emergency Contacts', 
                          form=form, contacts=contacts)

@app.route('/contacts/delete/<int:contact_id>', methods=['POST'])
@login_required
def delete_contact(contact_id):
    contact = EmergencyContact.query.get_or_404(contact_id)
    
    # Ensure the contact belongs to the current user
    if contact.user_id != current_user.id:
        flash('You do not have permission to delete this contact')
        return redirect(url_for('manage_contacts'))
    
    db.session.delete(contact)
    db.session.commit()
    flash('Contact deleted successfully')
    return redirect(url_for('manage_contacts'))

@app.route('/fall_detections')
@login_required
def fall_detections():
    # Get user's fall detections with pagination
    page = request.args.get('page', 1, type=int)
    
    if current_user.role == 'admin':
        # Admins can see all detections
        pagination = FallDetection.query.order_by(FallDetection.timestamp.desc()).paginate(
            page=page, per_page=10, error_out=False)
    else:
        # Regular users only see their own detections
        pagination = FallDetection.query.filter_by(user_id=current_user.id).order_by(
            FallDetection.timestamp.desc()).paginate(page=page, per_page=10, error_out=False)
    
    detections = pagination.items
    
    return render_template('fall_detections.html', title='Fall Detections', 
                          detections=detections, pagination=pagination)

@app.route('/update_role/<int:user_id>', methods=['POST'])
@login_required
def update_role(user_id):
    if current_user.role != 'admin':
        flash('You do not have permission to update user roles')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    
    if new_role in ['user', 'admin']:
        user.role = new_role
        db.session.commit()
        flash(f'User {user.username} role updated to {new_role}')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/analytics')
@login_required
def analytics():
    if current_user.role != 'admin':
        flash('You do not have permission to access analytics')
        return redirect(url_for('dashboard'))
    
    # Get fall detection data for the past 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Fall detections by day
    detections = FallDetection.query.filter(FallDetection.timestamp >= thirty_days_ago).all()
    
    # Prepare data for charts
    dates = [detection.timestamp.strftime('%Y-%m-%d') for detection in detections]
    date_counts = {}
    for date in dates:
        date_counts[date] = date_counts.get(date, 0) + 1
    
    # Create a complete date range for the past 30 days
    all_dates = [(datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]
    all_dates.reverse()  # Sort chronologically
    
    # Fill in missing dates with zero counts
    for date in all_dates:
        if date not in date_counts:
            date_counts[date] = 0
    
    # Sort by date
    sorted_dates = sorted(date_counts.items())
    chart_dates = [item[0] for item in sorted_dates]
    chart_counts = [item[1] for item in sorted_dates]
    
    # User activity data
    users = User.query.all()
    active_users = [user for user in users if user.is_active]
    inactive_users = [user for user in users if not user.is_active]
    
    # Create charts using Plotly
    fall_chart = {
        'x': chart_dates,
        'y': chart_counts,
        'type': 'bar',
        'title': 'Fall Detections by Day (Last 30 Days)'
    }
    
    user_chart = {
        'labels': ['Active', 'Inactive'],
        'values': [len(active_users), len(inactive_users)],
        'type': 'pie',
        'title': 'User Account Status'
    }
    
    return render_template('analytics.html', title='Analytics',
                          fall_chart=json.dumps(fall_chart),
                          user_chart=json.dumps(user_chart))

@app.route('/send_alert/<int:user_id>', methods=['POST'])
def send_alert(user_id):
    # This endpoint would be called when a fall is detected
    # It could be triggered by your existing fall detection system
    
    user = User.query.get_or_404(user_id)
    
    # Create a new fall detection record
    location = request.form.get('location', 'Unknown')
    severity = request.form.get('severity', 'Unknown')
    
    fall_detection = FallDetection(
        user_id=user.id,
        location=location,
        severity=severity
    )
    db.session.add(fall_detection)
    db.session.commit()
    
    # Get user's emergency contacts
    contacts = EmergencyContact.query.filter_by(user_id=user.id).all()
    
    # Send alerts to all contacts
    results = alert_system.send_fall_alert(user, fall_detection, contacts)
    
    # Emit WebSocket event to the user
    socketio.emit('fall_detection', {
        'type': 'fall_detection',
        'fall_id': fall_detection.id,
        'timestamp': fall_detection.timestamp.isoformat(),
        'location': location,
        'severity': severity
    }, room=f'user_{user.id}')
    
    return jsonify({
        'message': 'Fall alert sent',
        'fall_id': fall_detection.id,
        'alert_results': results
    })

# Add WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f'user_{current_user.id}')
        print(f'User {current_user.username} connected to WebSocket')

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(f'user_{current_user.id}')
        print(f'User {current_user.username} disconnected from WebSocket')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = UserProfileForm()
    
    if form.validate_on_submit():
        # Update email
        current_user.email = form.email.data
        
        # Update password if provided
        if form.current_password.data and form.new_password.data:
            if current_user.check_password(form.current_password.data):
                current_user.set_password(form.new_password.data)
                flash('Your password has been updated')
            else:
                flash('Current password is incorrect')
                return redirect(url_for('profile'))
        
        db.session.commit()
        flash('Your profile has been updated')
        return redirect(url_for('dashboard'))
    
    # Pre-populate form with current user data
    if request.method == 'GET':
        form.email.data = current_user.email
    
    return render_template('profile.html', title='Profile', form=form)

# Existing routes
@app.route('/set_ip', methods=['POST'])
def set_ip():
    data = request.get_json()
    camera_id = data.get('camera_id')
    ip_address = data.get('ip')
    
    # Ensure the IP is complete, adding 'http://' if not already there
    if not ip_address.startswith("http://"):
        ip_address = "http://" + ip_address
    
    ip_addresses[camera_id] = ip_address
    print(f"Received IP address: {ip_address} for camera ID: {camera_id}")  # Log for debugging
    return jsonify({'message': 'IP address set successfully'}), 200

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    camera_id = int(request.form.get('camera_id'))
    if camera_id not in frame_queues:
        return jsonify({'error': 'Invalid camera ID'}), 400

    filename = file.filename
    file_path = os.path.join('uploads', filename)
    try:
        file.save(file_path)
        print(f"File saved at: {file_path}")
        video_processors[camera_id].start_processing(file_path, camera_id)
        file_streams[camera_id] = file_path  # Store the file path for the camera ID
        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename,
            'url': f'/uploads/{filename}'
        }), 200
    except Exception as e:
        print(f"Error saving file: {e}")
        return jsonify({'error': 'Error uploading file'}), 500

@app.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    if camera_id in ip_addresses:
        ip_address = ip_addresses[camera_id]
        print(f"Streaming from IP address: {ip_address} for camera ID: {camera_id}")  # Log IP address
        esp32_cam = ESP32CamStreamer(f"{ip_address}/")  # Ensure the complete URL is passed
        video_processor = video_processors[camera_id]
        streamer = VideoStreamer(esp32_cam, video_processor)
        return Response(streamer.generate_frames(), 
                       mimetype='multipart/x-mixed-replace; boundary=frame',
                       headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                                'Pragma': 'no-cache',
                                'Expires': '0'})
    elif camera_id in file_streams:
        print(f"Streaming from file for camera ID: {camera_id}")
        streamer = video_streamers_file[camera_id]
        return Response(streamer.get_frame(), 
                       mimetype='multipart/x-mixed-replace; boundary=frame',
                       headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                                'Pragma': 'no-cache',
                                'Expires': '0'})
    else:
        print(f"Camera ID {camera_id} not found")
        return jsonify({'error': 'Camera ID not found'}), 404

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        upload_dir = os.path.abspath('uploads')
        file_path = os.path.join(upload_dir, filename)
        print(f"Attempting to serve file: {file_path}")
        print(f"File exists: {os.path.exists(file_path)}")
        return send_from_directory(upload_dir, filename)
    except Exception as e:
        print(f"Error serving file {filename}: {str(e)}")
        return str(e), 500

# Function to create a fall detection for testing
@app.route('/test_fall/<int:user_id>', methods=['GET'])
@login_required
def test_fall(user_id):
    if current_user.role != 'admin' and current_user.id != user_id:
        flash('You do not have permission to test falls for other users')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Create a test fall detection
    fall_detection = FallDetection(
        user_id=user.id,
        location='Test Location',
        severity='Medium'
    )
    db.session.add(fall_detection)
    db.session.commit()
    
    # Get user's emergency contacts
    contacts = EmergencyContact.query.filter_by(user_id=user.id).all()
    
    # Send alerts to all contacts
    results = alert_system.send_fall_alert(user, fall_detection, contacts)
    
    flash('Test fall detection created and alerts sent')
    return redirect(url_for('dashboard'))

# Replace the @app.before_first_request decorator with a different approach
# Remove this code:
# @app.before_first_request
# def create_tables():
#     db.create_all()
#     
#     # Create admin user if it doesn't exist
#     admin = User.query.filter_by(username='admin').first()
#     if admin is None:
#         admin = User(username='admin', email='admin@example.com', role='admin')
#         admin.set_password('admin123')  # Change this in production
#         db.session.add(admin)
#         db.session.commit()

# Instead, use the with app.app_context() approach which is already in your __main__ block
if __name__ == "__main__":
    os.makedirs('uploads', exist_ok=True)
    with app.app_context():
        db.create_all()
        # Create admin user if it doesn't exist
        admin = User.query.filter_by(username='admin').first()
        if admin is None:
            admin = User(username='admin', email='admin@example.com', role='admin')
            admin.set_password('admin123')  # Change this in production
            db.session.add(admin)
            db.session.commit()
    # Remove app.run and use only socketio.run
    socketio.run(app, debug=True, use_reloader=False)
