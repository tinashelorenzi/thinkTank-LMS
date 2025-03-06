from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from models.calendar import EventType, RecurrenceType


class CalendarEventBase(BaseModel):
    """Base schema for calendar event"""
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    all_day: bool = False
    time_zone: str = "UTC"
    location: Optional[str] = None
    event_type: EventType = EventType.OTHER
    url: Optional[str] = None
    color: Optional[str] = None
    recurrence_type: RecurrenceType = RecurrenceType.NONE
    recurrence_end_date: Optional[datetime] = None
    recurrence_rule: Optional[str] = None
    course_id: Optional[int] = None
    user_id: Optional[int] = None
    section_id: Optional[int] = None
    assignment_id: Optional[int] = None
    is_public: bool = True
    has_reminder: bool = False
    reminder_minutes_before: Optional[int] = None


class CalendarEventCreate(CalendarEventBase):
    """Schema for creating a calendar event"""
    attendee_ids: Optional[List[int]] = None  # User IDs to add as attendees


class CalendarEventUpdate(BaseModel):
    """Schema for updating a calendar event"""
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    all_day: Optional[bool] = None
    time_zone: Optional[str] = None
    location: Optional[str] = None
    event_type: Optional[EventType] = None
    url: Optional[str] = None
    color: Optional[str] = None
    recurrence_type: Optional[RecurrenceType] = None
    recurrence_end_date: Optional[datetime] = None
    recurrence_rule: Optional[str] = None
    course_id: Optional[int] = None
    user_id: Optional[int] = None
    section_id: Optional[int] = None
    assignment_id: Optional[int] = None
    is_public: Optional[bool] = None
    has_reminder: Optional[bool] = None
    reminder_minutes_before: Optional[int] = None
    attendee_ids: Optional[List[int]] = None


class CalendarEventResponse(CalendarEventBase):
    """Response schema for a calendar event"""
    id: int
    created_at: datetime
    updated_at: datetime
    course: Optional[Dict[str, Any]] = None
    user: Optional[Dict[str, Any]] = None
    section: Optional[Dict[str, Any]] = None
    assignment: Optional[Dict[str, Any]] = None
    attendees: List[Dict[str, Any]] = []
    
    class Config:
        orm_mode = True


class CalendarEventListResponse(BaseModel):
    """Response schema for list of calendar events"""
    total: int
    events: List[CalendarEventResponse]

    class Config:
        orm_mode = True


class CalendarEventAttendeeBase(BaseModel):
    """Base schema for calendar event attendee"""
    event_id: int
    user_id: int
    is_organizer: bool = False
    status: str = "pending"  # pending, accepted, declined, tentative


class CalendarEventAttendeeCreate(CalendarEventAttendeeBase):
    """Schema for creating a calendar event attendee"""
    pass


class CalendarEventAttendeeUpdate(BaseModel):
    """Schema for updating a calendar event attendee"""
    is_organizer: Optional[bool] = None
    status: Optional[str] = None


class CalendarEventAttendeeResponse(CalendarEventAttendeeBase):
    """Response schema for a calendar event attendee"""
    id: int
    created_at: datetime
    updated_at: datetime
    user: Dict[str, Any]
    
    class Config:
        orm_mode = True


class CalendarSubscriptionBase(BaseModel):
    """Base schema for calendar subscription"""
    name: str
    url: str
    color: Optional[str] = None
    user_id: int
    course_id: Optional[int] = None
    is_visible: bool = True
    auto_sync: bool = True
    last_synced_at: Optional[datetime] = None


class CalendarSubscriptionCreate(CalendarSubscriptionBase):
    """Schema for creating a calendar subscription"""
    pass


class CalendarSubscriptionUpdate(BaseModel):
    """Schema for updating a calendar subscription"""
    name: Optional[str] = None
    url: Optional[str] = None
    color: Optional[str] = None
    is_visible: Optional[bool] = None
    auto_sync: Optional[bool] = None
    last_synced_at: Optional[datetime] = None


class CalendarSubscriptionResponse(CalendarSubscriptionBase):
    """Response schema for a calendar subscription"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class EventReminderBase(BaseModel):
    """Base schema for event reminder"""
    event_id: int
    user_id: int
    minutes_before: int
    notification_method: str = "push"  # push, email, sms


class EventReminderCreate(EventReminderBase):
    """Schema for creating an event reminder"""
    pass


class EventReminderUpdate(BaseModel):
    """Schema for updating an event reminder"""
    minutes_before: Optional[int] = None
    notification_method: Optional[str] = None
    is_sent: Optional[bool] = None
    sent_at: Optional[datetime] = None


class EventReminderResponse(EventReminderBase):
    """Response schema for an event reminder"""
    id: int
    is_sent: bool = False
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class CalendarEventsDateRangeRequest(BaseModel):
    """Request schema for getting events in a date range"""
    start_date: datetime
    end_date: datetime
    course_ids: Optional[List[int]] = None
    user_id: Optional[int] = None
    include_assignments: bool = True
    include_course_events: bool = True
    include_user_events: bool = True