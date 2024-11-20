import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from modules import configFunctions



def send_email(config_location, subject, body, to_emails):
    config = configFunctions.get_config(config_location)
    email_config = config.get('email', {})
    smtp_server = email_config.get('smtpServer', '')
    smtp_port = email_config.get('smtpPort', 587)
    smtp_username = email_config.get('smtpUsername', '')
    smtp_password = email_config.get('smtpPassword', '')

    if not smtp_server or not smtp_username or not smtp_password:
        raise ValueError("Email configuration is incomplete. Please check your config file.")

    msg = MIMEMultipart()
    msg['From'] = smtp_username
    msg['To'] = to_emails
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, to_emails, msg.as_string())