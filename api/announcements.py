from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course, Section
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.group import Group
from models.file import File
from models.announcement import (
    Announcement, AnnouncementComment, AnnouncementLike, AnnouncementAttachment,
    AnnouncementRead, AnnouncementRecipient, AnnouncementRecipientType, AnnouncementPriority
)
from schemas.annoucement import (
    AnnouncementCreate, AnnouncementUpdate, AnnouncementResponse, AnnouncementListResponse,
    AnnouncementCommentCreate, AnnouncementCommentUpdate, AnnouncementCommentResponse,
    AnnouncementCommentListResponse, AnnouncementLikeCreate, AnnouncementReadCreate,
    AnnouncementAttachmentCreate, AnnouncementRecipientCreate
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.email import send_email_background
from utils.pagination import get_page_params, paginate_queryset, PageParams
from core.config import settings

# Create announcements router
router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(
        announcement_in: AnnouncementCreate,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new announcement (instructor or admin only)
    """
    # Get course
    course = await Course.get_or_none(id=announcement_in.course_id)

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Check if user has permission to create announcements for this course
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create announcements for this course",
            )

    # Check section if specified
    section = None
    if announcement_in.section_id:
        section = await Section.get_or_none(id=announcement_in.section_id, course=course)

        if not section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Section not found",
            )

    # Check group if specified
    group = None
    if announcement_in.group_id:
        group = await Group.get_or_none(id=announcement_in.group_id, course=course)

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

    # Create announcement
    announcement = await Announcement.create(
        title=announcement_in.title,
        message=announcement_in.message,
        course=course,
        author=current_user,
        section=section,
        group=group,
        recipient_type=announcement_in.recipient_type,
        priority=announcement_in.priority,
        is_published=announcement_in.is_published,
        is_pinned=announcement_in.is_pinned,
        publish_at=announcement_in.publish_at,
        send_notification=announcement_in.send_notification,
        allow_comments=announcement_in.allow_comments,
        allow_liking=announcement_in.allow_liking,
    )

    # Add attachments if specified
    if announcement_in.attachment_ids:
        for file_id in announcement_in.attachment_ids:
            file = await File.get_or_none(id=file_id)
            if file:
                await AnnouncementAttachment.create(
                    announcement=announcement,
                    file=file,
                )

    # Add specific recipients if specified
    if announcement_in.recipient_type == AnnouncementRecipientType.INDIVIDUAL and announcement_in.recipient_ids:
        for recipient_id in announcement_in.recipient_ids:
            recipient = await User.get_or_none(id=recipient_id)
            if recipient:
                await AnnouncementRecipient.create(
                    announcement=announcement,
                    user=recipient,
                )

    # Send notifications if enabled and announcement is published
    if announcement.is_published and announcement.send_notification:
        # Determine recipients based on recipient type
        recipient_users = []

        if announcement.recipient_type == AnnouncementRecipientType.COURSE:
            # All course members
            recipient_users = await User.filter(
                enrollments__course=course,
                enrollments__state=EnrollmentState.ACTIVE,
            ).all()

        elif announcement.recipient_type == AnnouncementRecipientType.SECTION and section:
            # Section members
            recipient_users = await User.filter(
                enrollments__course=course,
                enrollments__section=section,
                enrollments__state=EnrollmentState.ACTIVE,
            ).all()

        elif announcement.recipient_type == AnnouncementRecipientType.GROUP and group:
            # Group members
            recipient_users = await User.filter(
                group_memberships__group=group,
                group_memberships__is_active=True,
            ).all()

        elif announcement.recipient_type == AnnouncementRecipientType.ROLE:
            # Determine role type based on the message content
            # Simplified implementation: check if "student" is in the message
            role_type = EnrollmentType.STUDENT if "student" in announcement.message.lower() else EnrollmentType.TEACHER

            recipient_users = await User.filter(
                enrollments__course=course,
                enrollments__type=role_type,
                enrollments__state=EnrollmentState.ACTIVE,
            ).all()

        elif announcement.recipient_type == AnnouncementRecipientType.INDIVIDUAL:
            # Specific individuals
            recipient_ids = await AnnouncementRecipient.filter(
                announcement=announcement
            ).values_list("user_id", flat=True)

            recipient_users = await User.filter(id__in=recipient_ids).all()

        # Send emails to recipients
        for recipient in recipient_users:
            if recipient.id != current_user.id:  # Don't notify the author
                send_email_background(
                    background_tasks=background_tasks,
                    email_to=recipient.email,
                    subject=f"Announcement: {announcement.title}",
                    template_name="announcement",
                    template_data={
                        "username": recipient.username,
                        "course_name": course.name,
                        "announcement_title": announcement.title,
                        "announcement_snippet": announcement.message[:200] + "..." if len(announcement.message) > 200 else announcement.message,
                        "announcement_url": f"{settings.SERVER_HOST}/courses/{course.id}/announcements/{announcement.id}",
                        "project_name": settings.PROJECT_NAME,
                    },
                )

    return announcement


@router.get("", response_model=AnnouncementListResponse)
async def list_announcements(
        page_params: PageParams = Depends(get_page_params),
        course_id: int = Query(..., description="Course ID"),
        section_id: Optional[int] = Query(None, description="Filter by section ID"),
        group_id: Optional[int] = Query(None, description="Filter by group ID"),
        is_pinned: Optional[bool] = Query(None, description="Filter by pinned status"),
        search: Optional[str] = Query(None, description="Search by title or content"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List announcements for a course
    """
    # Get course
    course = await Course.get_or_none(id=course_id)

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Check if user can access this course
    if current_user.role != UserRole.ADMIN:
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

    # Create base query
    query = Announcement.filter(course=course)

    # Apply section filter
    if section_id:
        query = query.filter(section_id=section_id)

        # Check if user is in this section
        if current_user.role != UserRole.ADMIN:
            section_enrollment = await Enrollment.filter(
                user=current_user,
                course=course,
                section_id=section_id,
                state=EnrollmentState.ACTIVE,
            ).exists()

            if not section_enrollment and enrollment.type != EnrollmentType.TEACHER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not a member of this section",
                )

    # Apply group filter
    if group_id:
        query = query.filter(group_id=group_id)

        # Check if user is in this group
        if current_user.role != UserRole.ADMIN:
            group_member = await Group.filter(
                id=group_id,
                memberships__user=current_user,
                memberships__is_active=True,
            ).exists()

            if not group_member and enrollment.type != EnrollmentType.TEACHER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not a member of this group",
                )

    # Apply pinned filter
    if is_pinned is not None:
        query = query.filter(is_pinned=is_pinned)

    # Apply search filter
    if search:
        query = query.filter(
            (Announcement.title.icontains(search)) |
            (Announcement.message.icontains(search))
        )

    # Only show published announcements (or all for instructors)
    is_instructor = current_user.role == UserRole.ADMIN or (
            enrollment and enrollment.type == EnrollmentType.TEACHER
    )

    if not is_instructor:
        now = datetime.utcnow()
        query = query.filter(
            (Announcement.is_published == True) &
            ((Announcement.publish_at.is_null()) | (Announcement.publish_at <= now))
        )

    # Filter to announcements visible to this user
    if not is_instructor:
        # For non-instructors, filter based on recipient type
        recipient_filter = (
            # Course-wide announcements
                (Announcement.recipient_type == AnnouncementRecipientType.COURSE) |
                # Section announcements for user's section
                ((Announcement.recipient_type == AnnouncementRecipientType.SECTION) &
                 (Announcement.section_id == enrollment.section_id) if enrollment.section_id else False) |
                # Group announcements for user's groups
                ((Announcement.recipient_type == AnnouncementRecipientType.GROUP) &
                 (Announcement.group_id.in_(
                     Group.filter(
                         memberships__user=current_user,
                         memberships__is_active=True,
                     ).values_list("id", flat=True)
                 ))) |
                # Role-specific announcements for the user's role
                ((Announcement.recipient_type == AnnouncementRecipientType.ROLE) &
                 (Announcement.message.contains(enrollment.type.value))) |
                # Individual announcements for this user
                ((Announcement.recipient_type == AnnouncementRecipientType.INDIVIDUAL) &
                 (Announcement.recipients.user == current_user))
        )

        query = query.filter(recipient_filter)

    # Order by pinned, then published date
    query = query.order_by("-is_pinned", "-created_at")

    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=AnnouncementResponse,
    )


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement(
        announcement_id: int = Path(..., description="The ID of the announcement"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get announcement by ID
    """
    # Get announcement with related objects
    announcement = await Announcement.get_or_none(id=announcement_id).prefetch_related(
        "course", "author", "section", "group", "attachments", "attachments__file"
    )

    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    # Check if user can access this announcement
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=announcement.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

        # Check if announcement is published (except for instructor)
        is_instructor = enrollment.type == EnrollmentType.TEACHER

        if not is_instructor:
            if not announcement.is_published:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This announcement is not published",
                )

            if announcement.publish_at and announcement.publish_at > datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This announcement is not yet available",
                )

            # Check if announcement is visible to this user based on recipient type
            if announcement.recipient_type == AnnouncementRecipientType.SECTION:
                if enrollment.section_id != announcement.section_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="This announcement is not for your section",
                    )

            elif announcement.recipient_type == AnnouncementRecipientType.GROUP:
                group_member = await Group.filter(
                    id=announcement.group_id,
                    memberships__user=current_user,
                    memberships__is_active=True,
                ).exists()

                if not group_member:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="This announcement is not for your group",
                    )

            elif announcement.recipient_type == AnnouncementRecipientType.ROLE:
                # Check if role matches based on message content
                # Simplified implementation: check if role type is mentioned in the message
                role_mentioned = enrollment.type.value in announcement.message.lower()

                if not role_mentioned:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="This announcement is not for your role",
                    )

            elif announcement.recipient_type == AnnouncementRecipientType.INDIVIDUAL:
                is_recipient = await AnnouncementRecipient.filter(
                    announcement=announcement,
                    user=current_user,
                ).exists()

                if not is_recipient:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="This announcement is not for you",
                    )

    # Mark as read for this user
    read_entry, created = await AnnouncementRead.get_or_create(
        announcement=announcement,
        user=current_user,
    )

    if created:
        # Increment view count
        announcement.view_count += 1
        await announcement.save()

    # Get comment and like counts
    announcement.comment_count = await AnnouncementComment.filter(announcement=announcement).count()
    announcement.like_count = await AnnouncementLike.filter(announcement=announcement).count()

    # Set read status for current user
    announcement.is_read = True

    return announcement


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
        announcement_in: AnnouncementUpdate,
        background_tasks: BackgroundTasks,
        announcement_id: int = Path(..., description="The ID of the announcement"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update an announcement (instructor or admin only)
    """
    # Get announcement
    announcement = await Announcement.get_or_none(id=announcement_id).prefetch_related("course")

    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    # Check if user has permission to update this announcement
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=announcement.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update announcements for this course",
            )

    # Check section if changed
    if announcement_in.section_id is not None and announcement_in.section_id != announcement.section_id:
        if announcement_in.section_id:
            section = await Section.get_or_none(id=announcement_in.section_id, course=announcement.course)

            if not section:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Section not found",
                )

            announcement.section = section
        else:
            announcement.section = None

    # Check group if changed
    if announcement_in.group_id is not None and announcement_in.group_id != announcement.group_id:
        if announcement_in.group_id:
            group = await Group.get_or_none(id=announcement_in.group_id, course=announcement.course)

            if not group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Group not found",
                )

            announcement.group = group
        else:
            announcement.group = None

    # Update fields
    for field, value in announcement_in.dict(exclude_unset=True, exclude={"section_id", "group_id", "attachment_ids", "recipient_ids"}).items():
        setattr(announcement, field, value)

    # Check if publishing status changed
    was_published = announcement.is_published
    now_published = announcement_in.is_published if announcement_in.is_published is not None else was_published

    # Update attachments if specified
    if announcement_in.attachment_ids is not None:
        # Remove existing attachments
        await AnnouncementAttachment.filter(announcement=announcement).delete()

        # Add new attachments
        for file_id in announcement_in.attachment_ids:
            file = await File.get_or_none(id=file_id)
            if file:
                await AnnouncementAttachment.create(
                    announcement=announcement,
                    file=file,
                )

    # Update recipients if specified
    if announcement_in.recipient_type == AnnouncementRecipientType.INDIVIDUAL and announcement_in.recipient_ids is not None:
        # Remove existing recipients
        await AnnouncementRecipient.filter(announcement=announcement).delete()

        # Add new recipients
        for recipient_id in announcement_in.recipient_ids:
            recipient = await User.get_or_none(id=recipient_id)
            if recipient:
                await AnnouncementRecipient.create(
                    announcement=announcement,
                    user=recipient,
                )

    # Save announcement
    await announcement.save()

    # Send notifications if newly published
    if not was_published and now_published and announcement.send_notification:
        # Determine recipients based on recipient type
        recipient_users = []

        if announcement.recipient_type == AnnouncementRecipientType.COURSE:
            # All course members
            recipient_users = await User.filter(
                enrollments__course=announcement.course,
                enrollments__state=EnrollmentState.ACTIVE,
            ).all()

        elif announcement.recipient_type == AnnouncementRecipientType.SECTION and announcement.section:
            # Section members
            recipient_users = await User.filter(
                enrollments__course=announcement.course,
                enrollments__section=announcement.section,
                enrollments__state=EnrollmentState.ACTIVE,
            ).all()

        elif announcement.recipient_type == AnnouncementRecipientType.GROUP and announcement.group:
            # Group members
            recipient_users = await User.filter(
                group_memberships__group=announcement.group,
                group_memberships__is_active=True,
            ).all()

        elif announcement.recipient_type == AnnouncementRecipientType.ROLE:
            # Determine role type based on the message content
            role_type = EnrollmentType.STUDENT if "student" in announcement.message.lower() else EnrollmentType.TEACHER

            recipient_users = await User.filter(
                enrollments__course=announcement.course,
                enrollments__type=role_type,
                enrollments__state=EnrollmentState.ACTIVE,
            ).all()

        elif announcement.recipient_type == AnnouncementRecipientType.INDIVIDUAL:
            # Specific individuals
            recipient_ids = await AnnouncementRecipient.filter(
                announcement=announcement
            ).values_list("user_id", flat=True)

            recipient_users = await User.filter(id__in=recipient_ids).all()

        # Send emails to recipients
        for recipient in recipient_users:
            if recipient.id != current_user.id:  # Don't notify the author
                send_email_background(
                    background_tasks=background_tasks,
                    email_to=recipient.email,
                    subject=f"Announcement: {announcement.title}",
                    template_name="announcement",
                    template_data={
                        "username": recipient.username,
                        "course_name": announcement.course.name,
                        "announcement_title": announcement.title,
                        "announcement_snippet": announcement.message[:200] + "..." if len(announcement.message) > 200 else announcement.message,
                        "announcement_url": f"{settings.SERVER_HOST}/courses/{announcement.course.id}/announcements/{announcement.id}",
                        "project_name": settings.PROJECT_NAME,
                    },
                )

    # Refresh to get related objects
    await announcement.fetch_related("course", "author", "section", "group", "attachments", "attachments__file")

    return announcement


@router.delete("/{announcement_id}", response_model=Dict[str, Any])
async def delete_announcement(
        announcement_id: int = Path(..., description="The ID of the announcement"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete an announcement (instructor or admin only)
    """
    # Get announcement
    announcement = await Announcement.get_or_none(id=announcement_id).prefetch_related("course")

    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    # Check if user has permission to delete this announcement
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=announcement.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete announcements for this course",
            )

    # Delete announcement (will cascade delete attachments, comments, likes, etc.)
    await announcement.delete()

    return {"message": "Announcement deleted successfully"}


@router.post("/{announcement_id}/comments", response_model=AnnouncementCommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
        comment_in: AnnouncementCommentCreate,
        announcement_id: int = Path(..., description="The ID of the announcement"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Add a comment to an announcement
    """
    # Get announcement
    announcement = await Announcement.get_or_none(id=announcement_id).prefetch_related("course")

    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    # Check if comments are allowed
    if not announcement.allow_comments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comments are not allowed for this announcement",
        )

    # Check if user has access to this announcement
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=announcement.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    # Check parent comment if specified
    parent = None
    if comment_in.parent_id:
        parent = await AnnouncementComment.get_or_none(id=comment_in.parent_id, announcement=announcement)

        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found",
            )

    # Create comment
    comment = await AnnouncementComment.create(
        announcement=announcement,
        author=current_user,
        text=comment_in.text,
        parent=parent,
    )

    # Refresh to get related objects
    await comment.fetch_related("author")

    # Get replies if parent is None
    if not parent:
        comment.replies = []

    return comment


@router.get("/{announcement_id}/comments", response_model=AnnouncementCommentListResponse)
async def list_comments(
        announcement_id: int = Path(..., description="The ID of the announcement"),
        page_params: PageParams = Depends(get_page_params),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List comments for an announcement
    """
    # Get announcement
    announcement = await Announcement.get_or_none(id=announcement_id).prefetch_related("course")

    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    # Check if user has access to this announcement
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=announcement.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    # Get top-level comments (no parent)
    query = AnnouncementComment.filter(announcement=announcement, parent=None)

    # Order by creation date
    query = query.order_by("created_at")

    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=AnnouncementCommentResponse,
    )


@router.put("/comments/{comment_id}", response_model=AnnouncementCommentResponse)
async def update_comment(
        comment_in: AnnouncementCommentUpdate,
        comment_id: int = Path(..., description="The ID of the comment"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update a comment
    """
    # Get comment
    comment = await AnnouncementComment.get_or_none(id=comment_id).prefetch_related("announcement", "author")

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )

    # Check if user has permission to update this comment
    if current_user.role != UserRole.ADMIN:
        # Only the author can update their comment
        if comment.author_id != current_user.id:
            # Or an instructor of the course
            instructor_enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=comment.announcement.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            )

            if not instructor_enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to update this comment",
                )

    # Update fields
    for field, value in comment_in.dict(exclude_unset=True).items():
        setattr(comment, field, value)

    # Save comment
    await comment.save()

    # Get replies if parent is None
    if not comment.parent_id:
        await comment.fetch_related("replies")
    else:
        comment.replies = []

    return comment


@router.delete("/comments/{comment_id}", response_model=Dict[str, Any])
async def delete_comment(
        comment_id: int = Path(..., description="The ID of the comment"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete a comment
    """
    # Get comment
    comment = await AnnouncementComment.get_or_none(id=comment_id).prefetch_related("announcement", "author")

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )

    # Check if user has permission to delete this comment
    if current_user.role != UserRole.ADMIN:
        # Only the author can delete their comment
        if comment.author_id != current_user.id:
            # Or an instructor of the course
            instructor_enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=comment.announcement.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            )

            if not instructor_enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to delete this comment",
                )

    # Check if comment has replies
    has_replies = await AnnouncementComment.filter(parent=comment).exists()

    if has_replies:
        # Just mark as hidden instead of deleting
        comment.is_hidden = True
        comment.hidden_reason = "Deleted by user"
        await comment.save()
    else:
        # Delete comment
        await comment.delete()

    return {"message": "Comment deleted successfully"}


@router.post("/{announcement_id}/like", response_model=Dict[str, Any])
async def like_announcement(
        announcement_id: int = Path(..., description="The ID of the announcement"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Like or unlike an announcement
    """
    # Get announcement
    announcement = await Announcement.get_or_none(id=announcement_id).prefetch_related("course")

    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    # Check if liking is allowed
    if not announcement.allow_liking:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Liking is not allowed for this announcement",
        )

    # Check if user has access to this announcement
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=announcement.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    # Check if user already liked this announcement
    existing_like = await AnnouncementLike.get_or_none(
        announcement=announcement,
        user=current_user,
    )

    if existing_like:
        # Unlike
        await existing_like.delete()
        return {"message": "Announcement unliked successfully"}
    else:
        # Like
        await AnnouncementLike.create(
            announcement=announcement,
            user=current_user,
        )
        return {"message": "Announcement liked successfully"}


@router.post("/{announcement_id}/read", response_model=Dict[str, Any])
async def mark_as_read(
        announcement_id: int = Path(..., description="The ID of the announcement"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Mark an announcement as read
    """
    # Get announcement
    announcement = await Announcement.get_or_none(id=announcement_id)

    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
        )

    # Create or update read record
    read_entry, created = await AnnouncementRead.get_or_create(
        announcement=announcement,
        user=current_user,
        defaults={"is_read": True, "read_at": datetime.utcnow()}
    )

    if not created:
        read_entry.is_read = True
        read_entry.read_at = datetime.utcnow()
        await read_entry.save()

    # Increment view count if newly read
    if created:
        announcement.view_count += 1
        await announcement.save()

    return {"message": "Announcement marked as read successfully"}