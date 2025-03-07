from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.calendar import (
    CalendarEvent, CalendarEventAttendee, CalendarSubscription, EventReminder,
    EventType, RecurrenceType
)
from models.assignment import Assignment
from schemas.calendar import (
    CalendarEventCreate, CalendarEventUpdate, CalendarEventResponse, CalendarEventListResponse,
    CalendarEventAttendeeCreate, CalendarEventAttendeeUpdate, CalendarEventAttendeeResponse,
    CalendarSubscriptionCreate, CalendarSubscriptionUpdate, CalendarSubscriptionResponse,
    EventReminderCreate, EventReminderUpdate, EventReminderResponse,
    CalendarEventsDateRangeRequest
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.pagination import get_page_params, paginate_queryset, PageParams
from core.config import settings

# Create calendar router
router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
        event_in: CalendarEventCreate,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create a new calendar event
    """
    # Check course if specified
    course = None
    if event_in.course_id:
        course = await Course.get_or_none(id=event_in.course_id)

        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        # Check if user has permission to create events for this course
        if current_user.role != UserRole.ADMIN:
            # Check if user is enrolled in the course
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=course,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not enrolled in this course",
                )

            # Only instructors can create course-wide events
            if event_in.event_type in [EventType.COURSE, EventType.LECTURE, EventType.OFFICE_HOURS] and \
                    enrollment.type != EnrollmentType.TEACHER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only instructors can create course-wide events",
                )

    # Check assignment if specified
    assignment = None
    if event_in.assignment_id:
        assignment = await Assignment.get_or_none(id=event_in.assignment_id)

        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )

        # Validate assignment belongs to the specified course
        if event_in.course_id and assignment.course_id != event_in.course_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignment does not belong to the specified course",
            )

        # For assignment events, automatically set the course
        course = await Course.get(id=assignment.course_id)

    # Create event
    event = await CalendarEvent.create(
        title=event_in.title,
        description=event_in.description,
        start_time=event_in.start_time,
        end_time=event_in.end_time,
        all_day=event_in.all_day,
        time_zone=event_in.time_zone,
        location=event_in.location,
        event_type=event_in.event_type,
        url=event_in.url,
        color=event_in.color,
        recurrence_type=event_in.recurrence_type,
        recurrence_end_date=event_in.recurrence_end_date,
        recurrence_rule=event_in.recurrence_rule,
        course=course,
        user=current_user if not event_in.user_id else await User.get(id=event_in.user_id),
        section_id=event_in.section_id,
        assignment=assignment,
        is_public=event_in.is_public,
        has_reminder=event_in.has_reminder,
        reminder_minutes_before=event_in.reminder_minutes_before,
    )

    # Add attendees if specified
    if event_in.attendee_ids:
        for attendee_id in event_in.attendee_ids:
            attendee = await User.get_or_none(id=attendee_id)
            if attendee:
                await CalendarEventAttendee.create(
                    event=event,
                    user=attendee,
                    is_organizer=False,
                    status="pending",
                )

    # Add organizer as attendee
    await CalendarEventAttendee.create(
        event=event,
        user=current_user,
        is_organizer=True,
        status="accepted",
    )

    # Set up reminder if needed
    if event_in.has_reminder and event_in.reminder_minutes_before:
        await EventReminder.create(
            event=event,
            user=current_user,
            minutes_before=event_in.reminder_minutes_before,
            notification_method="push",
        )

    return event


@router.get("/events", response_model=CalendarEventListResponse)
async def list_events(
        page_params: PageParams = Depends(get_page_params),
        start_date: Optional[datetime] = Query(None, description="Filter by start date"),
        end_date: Optional[datetime] = Query(None, description="Filter by end date"),
        course_id: Optional[int] = Query(None, description="Filter by course ID"),
        event_type: Optional[EventType] = Query(None, description="Filter by event type"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List calendar events with various filters
    """
    # Create base query
    query = CalendarEvent.all()

    # Apply date range filters
    if start_date:
        query = query.filter(start_time__gte=start_date)

    if end_date:
        query = query.filter(end_time__lte=end_date)

    # Apply course filter
    if course_id:
        query = query.filter(course_id=course_id)

        # Check if user has access to this course
        if current_user.role != UserRole.ADMIN:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=course_id,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this course",
                )

    # Apply event type filter
    if event_type:
        query = query.filter(event_type=event_type)

    # Filter to events the user can see
    if current_user.role != UserRole.ADMIN:
        # User can see:
        # 1. Events they created
        # 2. Events where they are an attendee
        # 3. Public events
        # 4. Course events for courses they're enrolled in
        query = query.filter(
            # Events created by user
            (CalendarEvent.user == current_user) |
            # Events where user is an attendee
            (CalendarEvent.attendees.user == current_user) |
            # Public events
            (CalendarEvent.is_public == True) |
            # Course events for enrolled courses
            (CalendarEvent.course_id.in_(
                Enrollment.filter(
                    user=current_user,
                    state=EnrollmentState.ACTIVE
                ).values_list("course_id", flat=True)
            ))
        )

    # Get paginated results
    events = await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=CalendarEventResponse,
    )

    return events


@router.get("/events/{event_id}", response_model=CalendarEventResponse)
async def get_event(
        event_id: int = Path(..., description="The ID of the event"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get event by ID
    """
    # Get event with related objects
    event = await CalendarEvent.get_or_none(id=event_id).prefetch_related(
        "course", "user", "section", "assignment", "attendees", "attendees__user"
    )

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Check if user can view this event
    if current_user.role != UserRole.ADMIN:
        can_view = False

        # User can view events they created
        if event.user_id == current_user.id:
            can_view = True

        # User can view events they're attending
        elif await CalendarEventAttendee.filter(event=event, user=current_user).exists():
            can_view = True

        # User can view public events
        elif event.is_public:
            can_view = True

        # User can view course events for courses they're enrolled in
        elif event.course_id:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=event.course_id,
                state=EnrollmentState.ACTIVE,
            )

            if enrollment:
                can_view = True

        if not can_view:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this event",
            )

    return event


@router.put("/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
        event_in: CalendarEventUpdate,
        event_id: int = Path(..., description="The ID of the event"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update an event
    """
    # Get event
    event = await CalendarEvent.get_or_none(id=event_id)

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Check if user can update this event
    if current_user.role != UserRole.ADMIN:
        # Only the creator or an event organizer can update it
        is_creator = event.user_id == current_user.id
        is_organizer = await CalendarEventAttendee.filter(
            event=event,
            user=current_user,
            is_organizer=True
        ).exists()

        # For course events, instructors can update
        is_course_instructor = False
        if event.course_id:
            is_course_instructor = await Enrollment.filter(
                user=current_user,
                course_id=event.course_id,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()

        if not (is_creator or is_organizer or is_course_instructor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update this event",
            )

    # Check course if changed
    if event_in.course_id is not None and event_in.course_id != event.course_id:
        course = await Course.get_or_none(id=event_in.course_id)

        if not course and event_in.course_id is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        event.course = course

    # Check assignment if changed
    if event_in.assignment_id is not None and event_in.assignment_id != event.assignment_id:
        assignment = await Assignment.get_or_none(id=event_in.assignment_id)

        if not assignment and event_in.assignment_id is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )

        event.assignment = assignment

    # Update fields
    for field, value in event_in.dict(exclude_unset=True, exclude={"course_id", "assignment_id", "attendee_ids"}).items():
        setattr(event, field, value)

    # Save event
    await event.save()

    # Update attendees if specified
    if event_in.attendee_ids is not None:
        # Get current attendees
        current_attendees = await CalendarEventAttendee.filter(
            event=event,
            is_organizer=False
        ).all()

        # Remove attendees not in the new list
        current_attendee_ids = [a.user_id for a in current_attendees]
        for attendee in current_attendees:
            if attendee.user_id not in event_in.attendee_ids:
                await attendee.delete()

        # Add new attendees
        for attendee_id in event_in.attendee_ids:
            if attendee_id not in current_attendee_ids:
                attendee = await User.get_or_none(id=attendee_id)
                if attendee:
                    await CalendarEventAttendee.create(
                        event=event,
                        user=attendee,
                        is_organizer=False,
                        status="pending",
                    )

    # Refresh to get related objects
    await event.fetch_related("course", "user", "section", "assignment", "attendees", "attendees__user")

    return event


@router.delete("/events/{event_id}", response_model=Dict[str, Any])
async def delete_event(
        event_id: int = Path(..., description="The ID of the event"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete an event
    """
    # Get event
    event = await CalendarEvent.get_or_none(id=event_id)

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Check if user can delete this event
    if current_user.role != UserRole.ADMIN:
        # Only the creator or an event organizer can delete it
        is_creator = event.user_id == current_user.id
        is_organizer = await CalendarEventAttendee.filter(
            event=event,
            user=current_user,
            is_organizer=True
        ).exists()

        # For course events, instructors can delete
        is_course_instructor = False
        if event.course_id:
            is_course_instructor = await Enrollment.filter(
                user=current_user,
                course_id=event.course_id,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()

        if not (is_creator or is_organizer or is_course_instructor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this event",
            )

    # Delete event (will cascade delete attendees and reminders)
    await event.delete()

    return {"message": "Event deleted successfully"}


@router.post("/events/{event_id}/attendees", response_model=CalendarEventAttendeeResponse)
async def add_attendee(
        attendee_in: CalendarEventAttendeeCreate,
        event_id: int = Path(..., description="The ID of the event"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Add an attendee to an event
    """
    # Get event
    event = await CalendarEvent.get_or_none(id=event_id)

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Check if user can modify attendees
    if current_user.role != UserRole.ADMIN:
        # Only the creator or an event organizer can add attendees
        is_creator = event.user_id == current_user.id
        is_organizer = await CalendarEventAttendee.filter(
            event=event,
            user=current_user,
            is_organizer=True
        ).exists()

        if not (is_creator or is_organizer):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to add attendees to this event",
            )

    # Get user to add
    user = await User.get_or_none(id=attendee_in.user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if already an attendee
    existing_attendee = await CalendarEventAttendee.get_or_none(
        event=event,
        user=user,
    )

    if existing_attendee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already an attendee of this event",
        )

    # Create attendee
    attendee = await CalendarEventAttendee.create(
        event=event,
        user=user,
        is_organizer=attendee_in.is_organizer,
        status=attendee_in.status,
    )

    # Fetch related objects
    await attendee.fetch_related("user", "event")

    return attendee


@router.put("/events/attendees/{attendee_id}", response_model=CalendarEventAttendeeResponse)
async def update_attendee_status(
        attendee_in: CalendarEventAttendeeUpdate,
        attendee_id: int = Path(..., description="The ID of the attendee"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update attendee status for an event
    """
    # Get attendee
    attendee = await CalendarEventAttendee.get_or_none(id=attendee_id).prefetch_related("event", "user")

    if not attendee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendee not found",
        )

    # Check if user can update this attendee
    if current_user.role != UserRole.ADMIN:
        # Users can update their own attendance status
        is_self = attendee.user_id == current_user.id

        # Organizers can update any attendee
        is_organizer = await CalendarEventAttendee.filter(
            event=attendee.event,
            user=current_user,
            is_organizer=True
        ).exists()

        if not (is_self or is_organizer):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update this attendee",
            )

    # Update fields
    for field, value in attendee_in.dict(exclude_unset=True).items():
        setattr(attendee, field, value)

    # Save attendee
    await attendee.save()

    return attendee


@router.delete("/events/attendees/{attendee_id}", response_model=Dict[str, Any])
async def remove_attendee(
        attendee_id: int = Path(..., description="The ID of the attendee"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Remove an attendee from an event
    """
    # Get attendee
    attendee = await CalendarEventAttendee.get_or_none(id=attendee_id).prefetch_related("event", "user")

    if not attendee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendee not found",
        )

    # Check if user can remove this attendee
    if current_user.role != UserRole.ADMIN:
        # Users can remove themselves
        is_self = attendee.user_id == current_user.id

        # Organizers can remove any attendee
        is_organizer = await CalendarEventAttendee.filter(
            event=attendee.event,
            user=current_user,
            is_organizer=True
        ).exists()

        if not (is_self or is_organizer):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to remove this attendee",
            )

    # Delete attendee
    await attendee.delete()

    return {"message": "Attendee removed successfully"}


@router.post("/subscriptions", response_model=CalendarSubscriptionResponse)
async def create_subscription(
        subscription_in: CalendarSubscriptionCreate,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create a calendar subscription
    """
    # Check if user_id matches current user (non-admins can only create for themselves)
    if current_user.role != UserRole.ADMIN and subscription_in.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create subscriptions for yourself",
        )

    # Check course if specified
    if subscription_in.course_id:
        course = await Course.get_or_none(id=subscription_in.course_id)

        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        # Check if user is enrolled in this course
        if current_user.role != UserRole.ADMIN:
            enrollment = await Enrollment.get_or_none(
                user_id=subscription_in.user_id,
                course_id=subscription_in.course_id,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User is not enrolled in this course",
                )

    # Get user
    user = await User.get(id=subscription_in.user_id)

    # Create subscription
    subscription = await CalendarSubscription.create(
        name=subscription_in.name,
        url=subscription_in.url,
        color=subscription_in.color,
        user=user,
        course_id=subscription_in.course_id,
        is_visible=subscription_in.is_visible,
        auto_sync=subscription_in.auto_sync,
        last_synced_at=subscription_in.last_synced_at,
    )

    return subscription


@router.get("/subscriptions", response_model=List[CalendarSubscriptionResponse])
async def list_subscriptions(
        course_id: Optional[int] = Query(None, description="Filter by course ID"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List calendar subscriptions
    """
    # Create base query
    query = CalendarSubscription.filter(user=current_user)

    # Apply course filter
    if course_id:
        query = query.filter(course_id=course_id)

    # Get subscriptions
    subscriptions = await query.all()

    return subscriptions


@router.put("/subscriptions/{subscription_id}", response_model=CalendarSubscriptionResponse)
async def update_subscription(
        subscription_in: CalendarSubscriptionUpdate,
        subscription_id: int = Path(..., description="The ID of the subscription"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update a calendar subscription
    """
    # Get subscription
    subscription = await CalendarSubscription.get_or_none(id=subscription_id)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Check if user owns this subscription
    if current_user.role != UserRole.ADMIN and subscription.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this subscription",
        )

    # Update fields
    for field, value in subscription_in.dict(exclude_unset=True).items():
        setattr(subscription, field, value)

    # Save subscription
    await subscription.save()

    return subscription


@router.delete("/subscriptions/{subscription_id}", response_model=Dict[str, Any])
async def delete_subscription(
        subscription_id: int = Path(..., description="The ID of the subscription"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete a calendar subscription
    """
    # Get subscription
    subscription = await CalendarSubscription.get_or_none(id=subscription_id)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Check if user owns this subscription
    if current_user.role != UserRole.ADMIN and subscription.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this subscription",
        )

    # Delete subscription
    await subscription.delete()

    return {"message": "Subscription deleted successfully"}


@router.post("/events/{event_id}/reminders", response_model=EventReminderResponse)
async def create_reminder(
        reminder_in: EventReminderCreate,
        event_id: int = Path(..., description="The ID of the event"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create a reminder for an event
    """
    # Get event
    event = await CalendarEvent.get_or_none(id=event_id)

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Check if user can view this event (can only set reminders for events they can see)
    if current_user.role != UserRole.ADMIN:
        can_view = False

        # User can view events they created
        if event.user_id == current_user.id:
            can_view = True

        # User can view events they're attending
        elif await CalendarEventAttendee.filter(event=event, user=current_user).exists():
            can_view = True

        # User can view public events
        elif event.is_public:
            can_view = True

        # User can view course events for courses they're enrolled in
        elif event.course_id:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=event.course_id,
                state=EnrollmentState.ACTIVE,
            )

            if enrollment:
                can_view = True

        if not can_view:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this event",
            )

    # Check if reminder already exists
    existing_reminder = await EventReminder.get_or_none(
        event=event,
        user_id=reminder_in.user_id,
        minutes_before=reminder_in.minutes_before,
    )

    if existing_reminder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reminder with these settings already exists",
        )

    # Get user
    user = await User.get_or_none(id=reminder_in.user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if current user can set reminders for this user
    if current_user.role != UserRole.ADMIN and reminder_in.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create reminders for yourself",
        )

    # Create reminder
    reminder = await EventReminder.create(
        event=event,
        user=user,
        minutes_before=reminder_in.minutes_before,
        notification_method=reminder_in.notification_method,
    )

    return reminder


@router.put("/reminders/{reminder_id}", response_model=EventReminderResponse)
async def update_reminder(
        reminder_in: EventReminderUpdate,
        reminder_id: int = Path(..., description="The ID of the reminder"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update an event reminder
    """
    # Get reminder
    reminder = await EventReminder.get_or_none(id=reminder_id).prefetch_related("event", "user")

    if not reminder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder not found",
        )

    # Check if user owns this reminder
    if current_user.role != UserRole.ADMIN and reminder.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this reminder",
        )

    # Update fields
    for field, value in reminder_in.dict(exclude_unset=True).items():
        setattr(reminder, field, value)

    # Save reminder
    await reminder.save()

    return reminder


@router.delete("/reminders/{reminder_id}", response_model=Dict[str, Any])
async def delete_reminder(
        reminder_id: int = Path(..., description="The ID of the reminder"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete an event reminder
    """
    # Get reminder
    reminder = await EventReminder.get_or_none(id=reminder_id).prefetch_related("user")

    if not reminder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder not found",
        )

    # Check if user owns this reminder
    if current_user.role != UserRole.ADMIN and reminder.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this reminder",
        )

    # Delete reminder
    await reminder.delete()

    return {"message": "Reminder deleted successfully"}


@router.post("/events/date-range", response_model=List[CalendarEventResponse])
async def get_events_in_date_range(
        request: CalendarEventsDateRangeRequest,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get events within a specific date range
    """
    # Create base query
    query = CalendarEvent.filter(
        # Events that start within the range
        (CalendarEvent.start_time >= request.start_date) &
        (CalendarEvent.start_time <= request.end_date)
    ) | CalendarEvent.filter(
        # Events that end within the range
        (CalendarEvent.end_time >= request.start_date) &
        (CalendarEvent.end_time <= request.end_date)
    ) | CalendarEvent.filter(
        # Events that span the entire range
        (CalendarEvent.start_time <= request.start_date) &
        (CalendarEvent.end_time >= request.end_date)
    )

    # Apply course filter
    if request.course_ids:
        query = query.filter(course_id__in=request.course_ids)

        # Check if user has access to these courses
        if current_user.role != UserRole.ADMIN:
            for course_id in request.course_ids:
                enrollment = await Enrollment.get_or_none(
                    user=current_user,
                    course_id=course_id,
                    state=EnrollmentState.ACTIVE,
                )

                if not enrollment:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"You do not have access to course with ID {course_id}",
                    )

    # Apply user filter
    if request.user_id:
        query = query.filter(user_id=request.user_id)

        # Users can only see their own events unless admin
        if current_user.role != UserRole.ADMIN and request.user_id != current_user.id:
            # Allow if events are public
            query = query.filter(is_public=True)

    # Filter by event types
    type_filters = []

    if request.include_assignments:
        type_filters.append(EventType.ASSIGNMENT)

    if request.include_course_events:
        type_filters.extend([EventType.COURSE, EventType.LECTURE, EventType.OFFICE_HOURS])

    if request.include_user_events:
        type_filters.extend([EventType.PERSONAL, EventType.MEETING, EventType.OTHER])

    if type_filters:
        query = query.filter(event_type__in=type_filters)

    # Filter to events the user can see
    if current_user.role != UserRole.ADMIN:
        # User can see:
        # 1. Events they created
        # 2. Events where they are an attendee
        # 3. Public events
        # 4. Course events for courses they're enrolled in
        query = query.filter(
            # Events created by user
            (CalendarEvent.user == current_user) |
            # Events where user is an attendee
            (CalendarEvent.attendees.user == current_user) |
            # Public events
            (CalendarEvent.is_public == True) |
            # Course events for enrolled courses
            (CalendarEvent.course_id.in_(
                Enrollment.filter(
                    user=current_user,
                    state=EnrollmentState.ACTIVE
                ).values_list("course_id", flat=True)
            ))
        )

    # Get events
    events = await query.prefetch_related(
        "course", "user", "section", "assignment", "attendees", "attendees__user"
    ).all()

    # Process recurring events
    expanded_events = []
    for event in events:
        if event.recurrence_type == RecurrenceType.NONE:
            expanded_events.append(event)
        else:
            # Add original event
            expanded_events.append(event)

            # Add recurrence instances
            # Simple implementation for daily, weekly, monthly recurrence
            if event.recurrence_end_date and event.recurrence_end_date > request.end_date:
                recurrence_end = request.end_date
            else:
                recurrence_end = event.recurrence_end_date or request.end_date

            # Handle different recurrence types
            if event.recurrence_type == RecurrenceType.DAILY:
                # Generate daily events
                current_date = event.start_time + timedelta(days=1)  # Start from next day
                while current_date.date() <= recurrence_end.date():
                    # Create copy of event with updated dates
                    duration = event.end_time - event.start_time
                    expanded_events.append({
                        **event.__dict__,
                        "id": f"{event.id}_r_{current_date.strftime('%Y%m%d')}",
                        "start_time": current_date,
                        "end_time": current_date + duration,
                        "is_recurring_instance": True,
                    })
                    current_date += timedelta(days=1)

            elif event.recurrence_type == RecurrenceType.WEEKLY:
                # Generate weekly events
                current_date = event.start_time + timedelta(days=7)  # Start from next week
                while current_date.date() <= recurrence_end.date():
                    # Create copy of event with updated dates
                    duration = event.end_time - event.start_time
                    expanded_events.append({
                        **event.__dict__,
                        "id": f"{event.id}_r_{current_date.strftime('%Y%m%d')}",
                        "start_time": current_date,
                        "end_time": current_date + duration,
                        "is_recurring_instance": True,
                    })
                    current_date += timedelta(days=7)

            elif event.recurrence_type == RecurrenceType.BIWEEKLY:
                # Generate biweekly events
                current_date = event.start_time + timedelta(days=14)  # Start from two weeks later
                while current_date.date() <= recurrence_end.date():
                    # Create copy of event with updated dates
                    duration = event.end_time - event.start_time
                    expanded_events.append({
                        **event.__dict__,
                        "id": f"{event.id}_r_{current_date.strftime('%Y%m%d')}",
                        "start_time": current_date,
                        "end_time": current_date + duration,
                        "is_recurring_instance": True,
                    })
                    current_date += timedelta(days=14)

            elif event.recurrence_type == RecurrenceType.MONTHLY:
                # Generate monthly events
                start_day = event.start_time.day
                current_month = event.start_time.month + 1
                current_year = event.start_time.year

                while True:
                    # Handle year rollover
                    if current_month > 12:
                        current_month = 1
                        current_year += 1

                    # Try to create same day in next month
                    try:
                        current_date = datetime(
                            year=current_year,
                            month=current_month,
                            day=start_day,
                            hour=event.start_time.hour,
                            minute=event.start_time.minute,
                            second=event.start_time.second,
                        )
                    except ValueError:
                        # Handle months with fewer days (e.g., Feb 30)
                        # Just skip this recurrence
                        current_month += 1
                        continue

                    if current_date.date() > recurrence_end.date():
                        break

                    # Create copy of event with updated dates
                    duration = event.end_time - event.start_time
                    expanded_events.append({
                        **event.__dict__,
                        "id": f"{event.id}_r_{current_date.strftime('%Y%m%d')}",
                        "start_time": current_date,
                        "end_time": current_date + duration,
                        "is_recurring_instance": True,
                    })

                    current_month += 1

            elif event.recurrence_type == RecurrenceType.YEARLY:
                # Generate yearly events
                start_month = event.start_time.month
                start_day = event.start_time.day
                current_year = event.start_time.year + 1

                while True:
                    # Try to create same day in next year
                    try:
                        current_date = datetime(
                            year=current_year,
                            month=start_month,
                            day=start_day,
                            hour=event.start_time.hour,
                            minute=event.start_time.minute,
                            second=event.start_time.second,
                        )
                    except ValueError:
                        # Handle Feb 29 in non-leap years
                        # Just skip this recurrence
                        current_year += 1
                        continue

                    if current_date.date() > recurrence_end.date():
                        break

                    # Create copy of event with updated dates
                    duration = event.end_time - event.start_time
                    expanded_events.append({
                        **event.__dict__,
                        "id": f"{event.id}_r_{current_date.strftime('%Y%m%d')}",
                        "start_time": current_date,
                        "end_time": current_date + duration,
                        "is_recurring_instance": True,
                    })

                    current_year += 1

            elif event.recurrence_type == RecurrenceType.CUSTOM and event.recurrence_rule:
                # For custom recurrence, we'd need a more complex parser for RRULE
                # This would typically use a library like dateutil.rrule
                # Simplified implementation just adds a note
                expanded_events[-1]["custom_recurrence_note"] = "Custom recurrence pattern - see event details"

    return expanded_events