import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from twilio.rest import Client
import os
from datetime import datetime

class AlertSystem:
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
            
    def init_app(self, app):
        self.app = app
        # Initialize Twilio client
        self.twilio_client = Client(
            app.config.get('TWILIO_ACCOUNT_SID'),
            app.config.get('TWILIO_AUTH_TOKEN')
        )
        self.twilio_phone = app.config.get('TWILIO_PHONE_NUMBER')
        self.twilio_whatsapp = app.config.get('TWILIO_WHATSAPP_NUMBER')
        
        # Email settings
        self.mail_server = app.config.get('MAIL_SERVER')
        self.mail_port = app.config.get('MAIL_PORT')
        self.mail_username = app.config.get('MAIL_USERNAME')
        self.mail_password = app.config.get('MAIL_PASSWORD')
        self.mail_use_tls = app.config.get('MAIL_USE_TLS', False)
        self.mail_use_ssl = app.config.get('MAIL_USE_SSL', True)
        self.mail_default_sender = app.config.get('MAIL_DEFAULT_SENDER')
    
    def send_sms(self, to_number, message):
        try:
            message = self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_phone,
                to=to_number
            )
            return True, message.sid
        except Exception as e:
            return False, str(e)
    
    def send_whatsapp(self, to_number, message):
        try:
            # Format WhatsApp number with 'whatsapp:' prefix
            from_whatsapp = f"whatsapp:{self.twilio_whatsapp}"
            to_whatsapp = f"whatsapp:{to_number}"
            
            message = self.twilio_client.messages.create(
                body=message,
                from_=from_whatsapp,
                to=to_whatsapp
            )
            return True, message.sid
        except Exception as e:
            return False, str(e)
    
    def send_email(self, to_email, subject, message):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.mail_default_sender
            msg['To'] = to_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(message, 'plain'))
            
            if self.mail_use_ssl:
                server = smtplib.SMTP_SSL(self.mail_server, self.mail_port)
            else:
                server = smtplib.SMTP(self.mail_server, self.mail_port)
                if self.mail_use_tls:
                    server.starttls()
            
            server.login(self.mail_username, self.mail_password)
            server.send_message(msg)
            server.quit()
            
            return True, "Email sent successfully"
        except Exception as e:
            return False, str(e)
    
    def send_fall_alert(self, user, fall_detection, emergency_contacts):
        timestamp = fall_detection.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        location = fall_detection.location or "Unknown location"
        
        message = f"🚨 Fall Alert! A fall was detected for {user.username} at {timestamp}. Location: {location}. Please check on them."
        
        results = []
        
        for contact in emergency_contacts:
            if contact.alert_channel in ['sms', 'all'] and contact.phone_number:
                success, details = self.send_sms(contact.phone_number, message)
                results.append({
                    'contact': contact.name,
                    'method': 'SMS',
                    'success': success,
                    'details': details
                })
                
            if contact.alert_channel in ['whatsapp', 'all'] and contact.phone_number:
                success, details = self.send_whatsapp(contact.phone_number, message)
                results.append({
                    'contact': contact.name,
                    'method': 'WhatsApp',
                    'success': success,
                    'details': details
                })
                
            if contact.alert_channel in ['email', 'all'] and contact.email:
                subject = f"🚨 Fall Alert for {user.username}"
                success, details = self.send_email(contact.email, subject, message)
                results.append({
                    'contact': contact.name,
                    'method': 'Email',
                    'success': success,
                    'details': details
                })
                
        return results