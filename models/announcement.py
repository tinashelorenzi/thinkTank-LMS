from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class AnnouncementRecipientType(str, Enum):
    COURSE = "course"  # All course members
    SECTION = "section"  # Specific section
    GROUP = "group"  # Specific group
    ROLE = "role"  # Specific role (e.g., all students)
    INDIVIDUAL = "individual"  # Specific individuals


class AnnouncementPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Announcement(models.Model):
    """
    Announcement model for course-wide announcements and notifications
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    message = fields.TextField()
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="announcements")
    author = fields.ForeignKeyField("models.User", related_name="authored_announcements")
    
    # Optional relationships for specific audiences
    section = fields.ForeignKeyField("models.Section", related_name="announcements", null=True)
    group = fields.ForeignKeyField("models.Group", related_name="announcements", null=True)
    
    # Announcement settings
    recipient_type = fields.CharEnumField(AnnouncementRecipientType, default=AnnouncementRecipientType.COURSE)
    priority = fields.CharEnumField(AnnouncementPriority, default=AnnouncementPriority.NORMAL)
    
    # Visibility settings
    is_published = fields.BooleanField(default=True)
    is_pinned = fields.BooleanField(default=False)  # Pin to top of announcements
    
    # Scheduling
    publish_at = fields.DatetimeField(null=True)  # Schedule for future publishing
    
    # Notifications
    send_notification = fields.BooleanField(default=True)
    
    # Content settings
    allow_comments = fields.BooleanField(default=True)
    allow_liking = fields.BooleanField(default=True)
    
    # Stats
    view_count = fields.IntField(default=0)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships - will be referenced by other models
    # comments: ReverseRelation[AnnouncementComment]
    # likes: ReverseRelation[AnnouncementLike]
    # attachments: ReverseRelation[AnnouncementAttachment]
    
    class Meta:
        table = "announcements"
        ordering = ["-is_pinned", "-created_at"]
    
    def __str__(self):
        return f"{self.title} ({self.course.name})"


class AnnouncementComment(models.Model):
    """
    Comments on announcements
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    announcement = fields.ForeignKeyField("models.Announcement", related_name="comments")
    author = fields.ForeignKeyField("models.User", related_name="announcement_comments")
    
    # Comment content
    text = fields.TextField()
    
    # For threaded comments
    parent = fields.ForeignKeyField("models.AnnouncementComment", related_name="replies", null=True)
    
    # Moderation
    is_hidden = fields.BooleanField(default=False)
    hidden_reason = fields.CharField(max_length=255, null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "announcement_comments"
        ordering = ["created_at"]
    
    def __str__(self):
        return f"Comment by {self.author.username} on {self.announcement.title}"


class AnnouncementLike(models.Model):
    """
    Likes on announcements
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    announcement = fields.ForeignKeyField("models.Announcement", related_name="likes")
    user = fields.ForeignKeyField("models.User", related_name="announcement_likes")
    
    # Timestamp
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "announcement_likes"
        unique_together = (("announcement", "user"),)
    
    def __str__(self):
        return f"Like by {self.user.username} on {self.announcement.title}"


class AnnouncementAttachment(models.Model):
    """
    Files attached to announcements
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    announcement = fields.ForeignKeyField("models.Announcement", related_name="attachments")
    file = fields.ForeignKeyField("models.File", related_name="announcement_attachments")
    
    # Attachment settings
    display_name = fields.CharField(max_length=255, null=True)  # Override file name for display
    position = fields.IntField(default=0)  # Order of attachments
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "announcement_attachments"
        ordering = ["position", "created_at"]
    
    def __str__(self):
        return f"Attachment on {self.announcement.title}"


class AnnouncementRead(models.Model):
    """
    Tracks if a user has read an announcement
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    announcement = fields.ForeignKeyField("models.Announcement", related_name="reads")
    user = fields.ForeignKeyField("models.User", related_name="read_announcements")
    
    # Read status
    is_read = fields.BooleanField(default=True)
    read_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "announcement_reads"
        unique_together = (("announcement", "user"),)
    
    def __str__(self):
        return f"Read status for {self.user.username} on {self.announcement.title}"


class AnnouncementRecipient(models.Model):
    """
    Specific recipients for an announcement when using individual recipient type
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    announcement = fields.ForeignKeyField("models.Announcement", related_name="recipients")
    user = fields.ForeignKeyField("models.User", related_name="targeted_announcements")
    
    # Delivery status
    is_delivered = fields.BooleanField(default=False)
    delivered_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "announcement_recipients"
        unique_together = (("announcement", "user"),)
    
    def __str__(self):
        return f"Recipient {self.user.username} for {self.announcement.title}"


# Pydantic models for validation and serialization
Announcement_Pydantic = pydantic_model_creator(Announcement, name="Announcement")
AnnouncementCreate_Pydantic = pydantic_model_creator(
    Announcement, name="AnnouncementCreate", exclude=("id", "created_at", "updated_at", "view_count")
)

AnnouncementComment_Pydantic = pydantic_model_creator(AnnouncementComment, name="AnnouncementComment")
AnnouncementLike_Pydantic = pydantic_model_creator(AnnouncementLike, name="AnnouncementLike")
AnnouncementRead_Pydantic = pydantic_model_creator(AnnouncementRead, name="AnnouncementRead")