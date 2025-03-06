from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class EventType(str, Enum):
    ASSIGNMENT = "assignment"  # Assignment due date
    QUIZ = "quiz"  # Quiz or exam
    LECTURE = "lecture"  # Class lecture
    OFFICE_HOURS = "office_hours"  # Instructor office hours
    MEETING = "meeting"  # General meeting
    PERSONAL = "personal"  # Personal event (only visible to user)
    COURSE = "course"  # General course event
    OTHER = "other"  # Other event type


class RecurrenceType(str, Enum):
    NONE = "none"  # No recurrence
    DAILY = "daily"  # Repeats daily
    WEEKLY = "weekly"  # Repeats weekly
    BIWEEKLY = "biweekly"  # Repeats every two weeks
    MONTHLY = "monthly"  # Repeats monthly
    YEARLY = "yearly"  # Repeats yearly
    CUSTOM = "custom"  # Custom recurrence rule (uses RFC 5545 RRULE format)


class CalendarEvent(models.Model):
    """
    Calendar event model for scheduling various event types
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Event timing
    start_time = fields.DatetimeField()
    end_time = fields.DatetimeField()
    all_day = fields.BooleanField(default=False)
    time_zone = fields.CharField(max_length=50, default="UTC")
    
    # Event details
    location = fields.CharField(max_length=255, null=True)
    event_type = fields.CharEnumField(EventType, default=EventType.OTHER)
    url = fields.CharField(max_length=2048, null=True)  # For linking to additional resources
    color = fields.CharField(max_length=7, null=True)  # Hex color for the event
    
    # Recurrence
    recurrence_type = fields.CharEnumField(RecurrenceType, default=RecurrenceType.NONE)
    recurrence_end_date = fields.DateField(null=True)
    recurrence_rule = fields.CharField(max_length=255, null=True)  # RRULE format
    
    # Relationships - can be associated with various entities
    course = fields.ForeignKeyField("models.Course", related_name="calendar_events", null=True)
    user = fields.ForeignKeyField("models.User", related_name="calendar_events", null=True)
    section = fields.ForeignKeyField("models.Section", related_name="calendar_events", null=True)
    assignment = fields.ForeignKeyField("models.Assignment", related_name="calendar_events", null=True)
    
    # For private/public events
    is_public = fields.BooleanField(default=True)
    
    # Reminders
    has_reminder = fields.BooleanField(default=False)
    reminder_minutes_before = fields.IntField(null=True)  # Minutes before event to send reminder
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "calendar_events"
    
    def __str__(self):
        return f"{self.title} ({self.start_time.strftime('%Y-%m-%d %H:%M')})"


class CalendarEventAttendee(models.Model):
    """
    Attendees for calendar events
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    event = fields.ForeignKeyField("models.CalendarEvent", related_name="attendees")
    user = fields.ForeignKeyField("models.User", related_name="event_attendances")
    
    # Attendance status
    is_organizer = fields.BooleanField(default=False)
    status = fields.CharField(max_length=20, default="pending")  # pending, accepted, declined, tentative
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "calendar_event_attendees"
        unique_together = (("event", "user"),)
    
    def __str__(self):
        return f"{self.user.username} - {self.event.title}"


class CalendarSubscription(models.Model):
    """
    Calendar subscriptions for users to follow external or shared calendars
    """
    
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    
    # Subscription details
    url = fields.CharField(max_length=2048)  # iCal URL or internal reference
    color = fields.CharField(max_length=7, null=True)  # Hex color for events from this calendar
    
    # Relationships
    user = fields.ForeignKeyField("models.User", related_name="calendar_subscriptions")
    course = fields.ForeignKeyField("models.Course", related_name="calendar_subscriptions", null=True)
    
    # Settings
    is_visible = fields.BooleanField(default=True)
    auto_sync = fields.BooleanField(default=True)
    
    # Sync tracking
    last_synced_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "calendar_subscriptions"
    
    def __str__(self):
        return f"{self.name} ({self.user.username})"


class EventReminder(models.Model):
    """
    Custom reminders for calendar events
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    event = fields.ForeignKeyField("models.CalendarEvent", related_name="reminders")
    user = fields.ForeignKeyField("models.User", related_name="event_reminders")
    
    # Reminder settings
    minutes_before = fields.IntField()  # Minutes before event to send reminder
    notification_method = fields.CharField(max_length=20, default="push")  # push, email, sms
    
    # Status tracking
    is_sent = fields.BooleanField(default=False)
    sent_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "event_reminders"
    
    def __str__(self):
        return f"Reminder for {self.event.title} ({self.minutes_before} min before)"


# Pydantic models for validation and serialization
CalendarEvent_Pydantic = pydantic_model_creator(CalendarEvent, name="CalendarEvent")
CalendarEventCreate_Pydantic = pydantic_model_creator(
    CalendarEvent, name="CalendarEventCreate", exclude=(
        "id", "created_at", "updated_at"
    )
)

CalendarEventAttendee_Pydantic = pydantic_model_creator(CalendarEventAttendee, name="CalendarEventAttendee")
CalendarSubscription_Pydantic = pydantic_model_creator(CalendarSubscription, name="CalendarSubscription")
EventReminder_Pydantic = pydantic_model_creator(EventReminder, name="EventReminder")