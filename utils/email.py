"""
Email notification utilities
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any, Optional

from fastapi import BackgroundTasks
from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config import settings


# Configure logger
logger = logging.getLogger(__name__)

# Configure Jinja2 template environment
templates = Environment(
    loader=FileSystemLoader("templates/email"),
    autoescape=select_autoescape(['html', 'xml'])
)


async def send_email(
    email_to: str,
    subject: str,
    template_name: str,
    template_data: Dict[str, Any],
) -> bool:
    """
    Send an email using a template
    
    Args:
        email_to: Recipient email address
        subject: Email subject
        template_name: Name of the template file (without extension)
        template_data: Data to render the template with
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    # Skip if SMTP settings are not configured
    if not all([settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER, settings.SMTP_PASSWORD]):
        logger.warning("SMTP is not configured. Email not sent.")
        return False
    
    # Set up sender info
    sender_email = settings.EMAILS_FROM_EMAIL
    sender_name = settings.EMAILS_FROM_NAME or "LMS System"
    
    # Create message
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{sender_email}>"
    message["To"] = email_to
    
    # Render HTML and text templates
    try:
        # Try to render both HTML and text templates
        html_template = templates.get_template(f"{template_name}.html")
        html_content = html_template.render(**template_data)
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Try text template if it exists
        try:
            text_template = templates.get_template(f"{template_name}.txt")
            text_content = text_template.render(**template_data)
            text_part = MIMEText(text_content, "plain")
            message.attach(text_part)
        except:
            # No text template, generate a simple one from the template data
            text_content = f"Subject: {subject}\n\n"
            for key, value in template_data.items():
                if isinstance(value, str):
                    text_content += f"{key}: {value}\n"
            text_part = MIMEText(text_content, "plain")
            message.attach(text_part)
            
    except Exception as e:
        logger.error(f"Error rendering email template: {e}")
        return False
    
    # Send email
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_TLS:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(sender_email, email_to, message.as_string())
        logger.info(f"Email sent to {email_to}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {email_to}: {e}")
        return False


def send_email_background(
    background_tasks: BackgroundTasks,
    email_to: str,
    subject: str,
    template_name: str,
    template_data: Dict[str, Any],
) -> None:
    """
    Send email in the background
    
    Args:
        background_tasks: FastAPI BackgroundTasks object
        email_to: Recipient email address
        subject: Email subject
        template_name: Name of the template file (without extension)
        template_data: Data to render the template with
    """
    background_tasks.add_task(
        send_email,
        email_to=email_to,
        subject=subject,
        template_name=template_name,
        template_data=template_data
    )


async def send_verification_email(email_to: str, token: str, username: str) -> bool:
    """
    Send an email verification email
    
    Args:
        email_to: Recipient email address
        token: Verification token
        username: User's username
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    # Create verification URL
    verification_url = f"{settings.SERVER_HOST}/api/v1/auth/verify?token={token}"
    
    # Send email
    return await send_email(
        email_to=email_to,
        subject="Verify your email address",
        template_name="verification",
        template_data={
            "username": username,
            "verification_url": verification_url,
            "project_name": settings.PROJECT_NAME,
            "expires_hours": 24,  # Token expires after 24 hours
        }
    )


async def send_reset_password_email(email_to: str, token: str, username: str) -> bool:
    """
    Send a password reset email
    
    Args:
        email_to: Recipient email address
        token: Password reset token
        username: User's username
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    # Create reset URL
    reset_url = f"{settings.SERVER_HOST}/reset-password?token={token}"
    
    # Send email
    return await send_email(
        email_to=email_to,
        subject="Reset your password",
        template_name="reset_password",
        template_data={
            "username": username,
            "reset_url": reset_url,
            "project_name": settings.PROJECT_NAME,
            "expires_hours": settings.ACCESS_TOKEN_EXPIRE_MINUTES / 60,  # Convert minutes to hours
        }
    )


async def send_assignment_notification(
    email_to: str,
    username: str,
    course_name: str,
    assignment_title: str,
    due_date: str,
    assignment_url: str
) -> bool:
    """
    Send a notification about a new assignment
    
    Args:
        email_to: Recipient email address
        username: User's username
        course_name: Name of the course
        assignment_title: Title of the assignment
        due_date: Due date as a formatted string
        assignment_url: URL to view the assignment
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    return await send_email(
        email_to=email_to,
        subject=f"New Assignment: {assignment_title}",
        template_name="new_assignment",
        template_data={
            "username": username,
            "course_name": course_name,
            "assignment_title": assignment_title,
            "due_date": due_date,
            "assignment_url": assignment_url,
            "project_name": settings.PROJECT_NAME,
        }
    )


async def send_grade_notification(
    email_to: str,
    username: str,
    course_name: str,
    assignment_title: str,
    grade: str,
    feedback: Optional[str],
    grade_url: str
) -> bool:
    """
    Send a notification about a grade on an assignment
    
    Args:
        email_to: Recipient email address
        username: User's username
        course_name: Name of the course
        assignment_title: Title of the assignment
        grade: Grade as a formatted string
        feedback: Optional feedback from the instructor
        grade_url: URL to view the grade
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    return await send_email(
        email_to=email_to,
        subject=f"Grade Posted: {assignment_title}",
        template_name="grade_notification",
        template_data={
            "username": username,
            "course_name": course_name,
            "assignment_title": assignment_title,
            "grade": grade,
            "feedback": feedback,
            "grade_url": grade_url,
            "project_name": settings.PROJECT_NAME,
        }
    )


async def send_announcement_notification(
    email_to: str,
    username: str,
    course_name: str,
    announcement_title: str,
    announcement_snippet: str,
    announcement_url: str
) -> bool:
    """
    Send a notification about a new announcement
    
    Args:
        email_to: Recipient email address
        username: User's username
        course_name: Name of the course
        announcement_title: Title of the announcement
        announcement_snippet: Short preview of the announcement content
        announcement_url: URL to view the full announcement
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    return await send_email(
        email_to=email_to,
        subject=f"Announcement: {announcement_title}",
        template_name="announcement",
        template_data={
            "username": username,
            "course_name": course_name,
            "announcement_title": announcement_title,
            "announcement_snippet": announcement_snippet,
            "announcement_url": announcement_url,
            "project_name": settings.PROJECT_NAME,
        }
    )


async def send_discussion_notification(
    email_to: str,
    username: str,
    course_name: str,
    discussion_title: str,
    reply_author: str,
    reply_snippet: str,
    discussion_url: str
) -> bool:
    """
    Send a notification about a new discussion reply
    
    Args:
        email_to: Recipient email address
        username: User's username
        course_name: Name of the course
        discussion_title: Title of the discussion
        reply_author: Username of the person who replied
        reply_snippet: Short preview of the reply content
        discussion_url: URL to view the discussion
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    return await send_email(
        email_to=email_to,
        subject=f"New Reply: {discussion_title}",
        template_name="discussion_reply",
        template_data={
            "username": username,
            "course_name": course_name,
            "discussion_title": discussion_title,
            "reply_author": reply_author,
            "reply_snippet": reply_snippet,
            "discussion_url": discussion_url,
            "project_name": settings.PROJECT_NAME,
        }
    )