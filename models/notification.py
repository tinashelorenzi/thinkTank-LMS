from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class NotificationType(str, Enum):
    ASSIGNMENT = "assignment"  # Assignment posted or due soon
    GRADE = "grade"  # Grade posted
    DISCUSSION = "discussion"  # New discussion post or reply
    ANNOUNCEMENT = "announcement"  # Course announcement
    MESSAGE = "message"  # Direct message from user
    CALENDAR = "calendar"  # Calendar event
    COURSE = "course"  # Course-related notification
    SYSTEM = "system"  # System notification
    ENROLLMENT = "enrollment"  # Enrollment status change
    OTHER = "other"  # Other notification type


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(str, Enum):
    IN_APP = "in_app"  # Notification shown in the application
    EMAIL = "email"  # Email notification
    SMS = "sms"  # SMS notification
    PUSH = "push"  # Push notification to mobile device
    ALL = "all"  # All available channels


class Notification(models.Model):
    """
    Notification model for system and user-generated notifications
    """

    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    message = fields.TextField()

    # Notification details
    notification_type = fields.CharEnumField(NotificationType, default=NotificationType.SYSTEM)
    priority = fields.CharEnumField(NotificationPriority, default=NotificationPriority.NORMAL)

    # Delivery channels
    channels = fields.JSONField(default=lambda: [NotificationChannel.IN_APP])

    # Icon/image for the notification
    icon = fields.CharField(max_length=255, null=True)
    image_url = fields.CharField(max_length=2048, null=True)

    # Action link - where clicking the notification takes the user
    action_url = fields.CharField(max_length=2048, null=True)

    # Related entities - what the notification is about
    course = fields.ForeignKeyField("models.Course", related_name="notifications", null=True)
    assignment = fields.ForeignKeyField("models.Assignment", related_name="notifications", null=True)
    discussion_topic = fields.ForeignKeyField("models.DiscussionTopic", related_name="notifications", null=True)
    discussion_reply = fields.ForeignKeyField("models.DiscussionReply", related_name="notifications", null=True)
    calendar_event = fields.ForeignKeyField("models.CalendarEvent", related_name="notifications", null=True)

    # For system-wide notifications with no specific recipients
    is_system_wide = fields.BooleanField(default=False)

    # Global notification visibility
    is_public = fields.BooleanField(default=False)

    # Expiration of the notification
    expires_at = fields.DatetimeField(null=True)

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "notifications"

    def __str__(self):
        return f"{self.title} ({self.notification_type})"


class UserNotification(models.Model):
    """
    Links notifications to specific users and tracks their status
    """

    id = fields.IntField(pk=True)

    # Relationships
    notification = fields.ForeignKeyField("models.Notification", related_name="user_notifications")
    user = fields.ForeignKeyField("models.User", related_name="notifications")

    # Status tracking
    is_read = fields.BooleanField(default=False)
    read_at = fields.DatetimeField(null=True)
    is_dismissed = fields.BooleanField(default=False)
    dismissed_at = fields.DatetimeField(null=True)

    # Delivery status for each channel
    delivery_status = fields.JSONField(default=dict)
    # e.g., {"in_app": "delivered", "email": "sent", "sms": "failed"}

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_notifications"
        unique_together = (("notification", "user"),)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.notification.title}"


class NotificationPreference(models.Model):
    """
    User preferences for notifications
    """

    id = fields.IntField(pk=True)

    # Relationships
    user = fields.ForeignKeyField("models.User", related_name="notification_preferences")

    # Preferences by notification type
    preferences = fields.JSONField(default=dict)
    # e.g., {
    #   "assignment": {"in_app": true, "email": true, "sms": false, "push": true},
    #   "grade": {"in_app": true, "email": true, "sms": false, "push": true},
    #   ...
    # }

    # Course-specific preferences override the general preferences
    course = fields.ForeignKeyField("models.Course", related_name="notification_preferences", null=True)

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "notification_preferences"
        unique_together = (("user", "course"),)

    def __str__(self):
        return f"Notification preferences for {self.user.username}" + (f" in {self.course.name}" if self.course else "")


class NotificationBatch(models.Model):
    """
    Batch of notifications for bulk processing
    """

    id = fields.IntField(pk=True)

    # Batch details
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)

    # Status tracking
    status = fields.CharField(max_length=20, default="pending")  # pending, processing, completed, failed
    total_count = fields.IntField(default=0)
    processed_count = fields.IntField(default=0)
    success_count = fields.IntField(default=0)
    failure_count = fields.IntField(default=0)

    # Error tracking
    error_log = fields.TextField(null=True)

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    completed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "notification_batches"

    def __str__(self):
        return f"Notification batch: {self.name} ({self.status})"


# Pydantic models for validation and serialization
Notification_Pydantic = pydantic_model_creator(Notification, name="Notification")
NotificationCreate_Pydantic = pydantic_model_creator(
    Notification, name="NotificationCreate", exclude=("id", "created_at", "updated_at")
)

UserNotification_Pydantic = pydantic_model_creator(UserNotification, name="UserNotification")
NotificationPreference_Pydantic = pydantic_model_creator(NotificationPreference, name="NotificationPreference")
NotificationBatch_Pydantic = pydantic_model_creator(NotificationBatch, name="NotificationBatch")