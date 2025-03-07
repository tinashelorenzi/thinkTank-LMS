from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course, Section
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.discussion import (
    DiscussionForum, DiscussionTopic, DiscussionReply, DiscussionReplyLike,
    DiscussionTopicSubscription, DiscussionVisibility, DiscussionType
)
from models.module import Module
from models.group import Group
from schemas.discussion import (
    DiscussionTopicCreate, DiscussionTopicUpdate, DiscussionTopicResponse, DiscussionTopicListResponse,
    DiscussionReplyCreate, DiscussionReplyUpdate, DiscussionReplyResponse, DiscussionReplyListResponse,
    DiscussionReplyLikeCreate, DiscussionTopicSubscriptionCreate, DiscussionSubscriptionUpdate
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.email import send_email_background
from utils.pagination import get_page_params, paginate_queryset, PageParams
from core.config import settings

# Create discussions router
router = APIRouter(prefix="/discussions", tags=["discussions"])


@router.post("/forums/{forum_id}/topics", response_model=DiscussionTopicResponse, status_code=status.HTTP_201_CREATED)
async def create_discussion_topic(
    forum_id: int,
    topic_in: DiscussionTopicCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create new discussion topic
    """
    # Get forum
    forum = await DiscussionForum.get_or_none(id=forum_id).prefetch_related("course")
    
    if not forum:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion forum not found",
        )
    
    # Check if user can post to this forum
    if current_user.role != UserRole.ADMIN:
        # Check if user is enrolled in the course
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=forum.course,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
    
    # Check section if specified
    section = None
    if topic_in.section_id:
        section = await Section.get_or_none(id=topic_in.section_id, course=forum.course)
        
        if not section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Section not found",
            )
    
    # Create topic
    topic = await DiscussionTopic.create(
        title=topic_in.title,
        message=topic_in.message,
        forum=forum,
        author=current_user,
        type=topic_in.type,
        visibility=topic_in.visibility,
        is_announcement=topic_in.is_announcement,
        is_pinned=topic_in.is_pinned,
        allow_liking=topic_in.allow_liking,
        is_closed=topic_in.is_closed,
        section=section,
    )
    
    # Add visible to users if specified
    if topic_in.visible_to_user_ids:
        for user_id in topic_in.visible_to_user_ids:
            user = await User.get_or_none(id=user_id)
            if user:
                await topic.visible_to_users.add(user)
    
    # Add visible to groups if specified
    if topic_in.visible_to_group_ids:
        for group_id in topic_in.visible_to_group_ids:
            group = await Group.get_or_none(id=group_id)
            if group:
                await topic.visible_to_groups.add(group)
    
    # Notify subscribed users if this is an announcement
    if topic.is_announcement:
        # Get all enrolled users
        enrolled_users = await User.filter(
            enrollments__course=forum.course,
            enrollments__state=EnrollmentState.ACTIVE,
        )
        
        for user in enrolled_users:
            if user.id != current_user.id:  # Don't notify the author
                send_email_background(
                    background_tasks=background_tasks,
                    email_to=user.email,
                    subject=f"New Discussion: {topic.title}",
                    template_name="new_discussion",
                    template_data={
                        "username": user.username,
                        "course_name": forum.course.name,
                        "topic_title": topic.title,
                        "author_name": current_user.username,
                        "preview": topic.message[:200] + "..." if len(topic.message) > 200 else topic.message,
                        "topic_url": f"{settings.SERVER_HOST}/courses/{forum.course.id}/discussions/{topic.id}",
                    },
                )
    
    # Auto-subscribe the author
    await DiscussionTopicSubscription.create(
        topic=topic,
        user=current_user,
        send_email=True,
    )
    
    return topic


@router.get("/topics", response_model=DiscussionTopicListResponse)
async def list_discussion_topics(
    page_params: PageParams = Depends(get_page_params),
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    forum_id: Optional[int] = Query(None, description="Filter by forum ID"),
    search: Optional[str] = Query(None, description="Search by title or content"),
    is_announcement: Optional[bool] = Query(None, description="Filter by announcement status"),
    author_id: Optional[int] = Query(None, description="Filter by author ID"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List discussion topics with various filters
    """
    # Create base query
    query = DiscussionTopic.all()
    
    # Apply course filter
    if course_id:
        query = query.filter(forum__course_id=course_id)
        
        # Check if user can access this course
        if current_user.role != UserRole.ADMIN:
            # Check if user is enrolled in the course
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=course_id,
                state=EnrollmentState.ACTIVE,
            )
            
            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not enrolled in this course",
                )
    
    # Apply forum filter
    if forum_id:
        query = query.filter(forum_id=forum_id)
    
    # Apply announcement filter
    if is_announcement is not None:
        query = query.filter(is_announcement=is_announcement)
    
    # Apply author filter
    if author_id:
        query = query.filter(author_id=author_id)
    
    # Apply search filter
    if search:
        query = query.filter(
            (DiscussionTopic.title.icontains(search)) | 
            (DiscussionTopic.message.icontains(search))
        )
    
    # Apply visibility filter for non-admin users
    if current_user.role != UserRole.ADMIN:
        # Filter to topics the user can see
        query = query.filter(
            # Everyone topics
            (DiscussionTopic.visibility == DiscussionVisibility.EVERYONE) |
            # Author's own topics
            (DiscussionTopic.author == current_user) |
            # Topics visible to user's groups
            (DiscussionTopic.visible_to_groups.filter(memberships__user=current_user, memberships__is_active=True)) |
            # Topics visible to user directly
            (DiscussionTopic.visible_to_users.filter(id=current_user.id))
        )
        
        # For instructors, also include instructor-only topics
        if current_user.role == UserRole.INSTRUCTOR:
            query = query.filter(
                (DiscussionTopic.visibility == DiscussionVisibility.INSTRUCTORS) |
                query
            )
    
    # Order by pinned and created date
    query = query.order_by("-is_pinned", "-created_at")
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=DiscussionTopicResponse,
    )


@router.get("/topics/{topic_id}", response_model=DiscussionTopicResponse)
async def get_discussion_topic(
    topic_id: int = Path(..., description="The ID of the discussion topic"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get discussion topic by ID
    """
    # Get topic with related objects
    topic = await DiscussionTopic.get_or_none(id=topic_id).prefetch_related("forum", "forum__course", "author")
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion topic not found",
        )
    
    # Check if user can access this topic
    if current_user.role != UserRole.ADMIN:
        can_access = False
        
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=topic.forum.course,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check visibility
        if topic.visibility == DiscussionVisibility.EVERYONE:
            can_access = True
        elif topic.visibility == DiscussionVisibility.INSTRUCTORS:
            can_access = current_user.role == UserRole.INSTRUCTOR or current_user.id == topic.author_id
        elif topic.visibility == DiscussionVisibility.COURSE_SECTION:
            # Check if user is in the section
            if topic.section_id:
                section_enrollment = await Enrollment.filter(
                    user=current_user,
                    course=topic.forum.course,
                    section_id=topic.section_id,
                    state=EnrollmentState.ACTIVE,
                ).exists()
                can_access = section_enrollment or current_user.id == topic.author_id
        elif topic.visibility == DiscussionVisibility.GROUP:
            # Check if user is in one of the visible groups
            is_in_group = await Group.filter(
                id__in=[g.id for g in await topic.visible_to_groups.all()],
                memberships__user=current_user,
                memberships__is_active=True,
            ).exists()
            can_access = is_in_group or current_user.id == topic.author_id
        
        # Check if user is explicitly granted access
        is_explicit_user = await topic.visible_to_users.filter(id=current_user.id).exists()
        if is_explicit_user:
            can_access = True
        
        if not can_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this topic",
            )
    
    # Increment view count
    topic.view_count += 1
    await topic.save()
    
    return topic


@router.put("/topics/{topic_id}", response_model=DiscussionTopicResponse)
async def update_discussion_topic(
    topic_in: DiscussionTopicUpdate,
    topic_id: int = Path(..., description="The ID of the discussion topic"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update discussion topic
    """
    # Get topic
    topic = await DiscussionTopic.get_or_none(id=topic_id).prefetch_related("forum", "forum__course")
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion topic not found",
        )
    
    # Check if user can update this topic
    if current_user.role != UserRole.ADMIN:
        if topic.author_id != current_user.id:
            # Check if user is instructor
            is_instructor = await Enrollment.filter(
                user=current_user,
                course=topic.forum.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()
            
            if not is_instructor:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to update this topic",
                )
    
    # Check section if specified
    if topic_in.section_id:
        section = await Section.get_or_none(id=topic_in.section_id, course=topic.forum.course)
        
        if not section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Section not found",
            )
        
        topic.section = section
    
    # Update fields
    for field, value in topic_in.dict(exclude_unset=True, exclude={"section_id", "visible_to_user_ids", "visible_to_group_ids"}).items():
        setattr(topic, field, value)
    
    # Update visible to users if specified
    if topic_in.visible_to_user_ids is not None:
        # Clear existing relationships
        await topic.visible_to_users.clear()
        
        # Add new relationships
        for user_id in topic_in.visible_to_user_ids:
            user = await User.get_or_none(id=user_id)
            if user:
                await topic.visible_to_users.add(user)
    
    # Update visible to groups if specified
    if topic_in.visible_to_group_ids is not None:
        # Clear existing relationships
        await topic.visible_to_groups.clear()
        
        # Add new relationships
        for group_id in topic_in.visible_to_group_ids:
            group = await Group.get_or_none(id=group_id)
            if group:
                await topic.visible_to_groups.add(group)
    
    # Save topic
    await topic.save()
    
    return topic


@router.delete("/topics/{topic_id}", response_model=Dict[str, Any])
async def delete_discussion_topic(
    topic_id: int = Path(..., description="The ID of the discussion topic"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete discussion topic
    """
    # Get topic
    topic = await DiscussionTopic.get_or_none(id=topic_id).prefetch_related("forum", "forum__course")
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion topic not found",
        )
    
    # Check if user can delete this topic
    if current_user.role != UserRole.ADMIN:
        if topic.author_id != current_user.id:
            # Check if user is instructor
            is_instructor = await Enrollment.filter(
                user=current_user,
                course=topic.forum.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()
            
            if not is_instructor:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to delete this topic",
                )
    
    # Delete topic
    await topic.delete()
    
    return {"message": "Discussion topic deleted successfully"}


@router.post("/topics/{topic_id}/replies", response_model=DiscussionReplyResponse, status_code=status.HTTP_201_CREATED)
async def create_discussion_reply(
    reply_in: DiscussionReplyCreate,
    topic_id: int = Path(..., description="The ID of the discussion topic"),
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create new discussion reply
    """
    # Get topic
    topic = await DiscussionTopic.get_or_none(id=topic_id).prefetch_related("forum", "forum__course", "author")
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion topic not found",
        )
    
    # Check if user can reply to this topic
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=topic.forum.course,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check if topic is closed
        if topic.is_closed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This topic is closed for replies",
            )
        
        # Check visibility
        can_reply = False
        
        if topic.visibility == DiscussionVisibility.EVERYONE:
            can_reply = True
        elif topic.visibility == DiscussionVisibility.INSTRUCTORS:
            can_reply = current_user.role == UserRole.INSTRUCTOR or current_user.id == topic.author_id
        elif topic.visibility == DiscussionVisibility.COURSE_SECTION:
            # Check if user is in the section
            if topic.section_id:
                section_enrollment = await Enrollment.filter(
                    user=current_user,
                    course=topic.forum.course,
                    section_id=topic.section_id,
                    state=EnrollmentState.ACTIVE,
                ).exists()
                can_reply = section_enrollment or current_user.id == topic.author_id
        elif topic.visibility == DiscussionVisibility.GROUP:
            # Check if user is in one of the visible groups
            is_in_group = await Group.filter(
                id__in=[g.id for g in await topic.visible_to_groups.all()],
                memberships__user=current_user,
                memberships__is_active=True,
            ).exists()
            can_reply = is_in_group or current_user.id == topic.author_id
        
        # Check if user is explicitly granted access
        is_explicit_user = await topic.visible_to_users.filter(id=current_user.id).exists()
        if is_explicit_user:
            can_reply = True
        
        if not can_reply:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to reply to this topic",
            )
    
    # Check parent reply if specified
    parent_reply = None
    if reply_in.parent_reply_id:
        parent_reply = await DiscussionReply.get_or_none(id=reply_in.parent_reply_id, topic=topic)
        
        if not parent_reply:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent reply not found",
            )
    
    # Create reply
    reply = await DiscussionReply.create(
        message=reply_in.message,
        topic=topic,
        author=current_user,
        parent_reply=parent_reply,
    )
    
    # Notify topic author and subscribers
    if topic.author_id != current_user.id:
        # Notify topic author
        send_email_background(
            background_tasks=background_tasks,
            email_to=topic.author.email,
            subject=f"New Reply: {topic.title}",
            template_name="discussion_reply",
            template_data={
                "username": topic.author.username,
                "course_name": topic.forum.course.name,
                "discussion_title": topic.title,
                "reply_author": current_user.username,
                "reply_snippet": reply.message[:200] + "..." if len(reply.message) > 200 else reply.message,
                "discussion_url": f"{settings.SERVER_HOST}/courses/{topic.forum.course.id}/discussions/{topic.id}",
                "project_name": settings.PROJECT_NAME,
            },
        )
    
    # Notify subscribers
    subscribers = await DiscussionTopicSubscription.filter(
        topic=topic,
        send_email=True,
    ).prefetch_related("user")
    
    for subscription in subscribers:
        if subscription.user_id != current_user.id and subscription.user_id != topic.author_id:
            send_email_background(
                background_tasks=background_tasks,
                email_to=subscription.user.email,
                subject=f"New Reply: {topic.title}",
                template_name="discussion_reply",
                template_data={
                    "username": subscription.user.username,
                    "course_name": topic.forum.course.name,
                    "discussion_title": topic.title,
                    "reply_author": current_user.username,
                    "reply_snippet": reply.message[:200] + "..." if len(reply.message) > 200 else reply.message,
                    "discussion_url": f"{settings.SERVER_HOST}/courses/{topic.forum.course.id}/discussions/{topic.id}",
                    "project_name": settings.PROJECT_NAME,
                },
            )
    
    # Auto-subscribe user to the topic if not already subscribed
    subscription = await DiscussionTopicSubscription.get_or_none(topic=topic, user=current_user)
    if not subscription:
        await DiscussionTopicSubscription.create(
            topic=topic,
            user=current_user,
            send_email=True,
        )
    
    return reply


@router.get("/topics/{topic_id}/replies", response_model=DiscussionReplyListResponse)
async def list_discussion_replies(
    topic_id: int = Path(..., description="The ID of the discussion topic"),
    page_params: PageParams = Depends(get_page_params),
    parent_id: Optional[int] = Query(None, description="Filter by parent reply ID"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List discussion replies for a topic
    """
    # Get topic
    topic = await DiscussionTopic.get_or_none(id=topic_id).prefetch_related("forum", "forum__course")
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion topic not found",
        )
    
    # Check if user can view this topic
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=topic.forum.course,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check visibility
        can_view = False
        
        if topic.visibility == DiscussionVisibility.EVERYONE:
            can_view = True
        elif topic.visibility == DiscussionVisibility.INSTRUCTORS:
            can_view = current_user.role == UserRole.INSTRUCTOR or current_user.id == topic.author_id
        elif topic.visibility == DiscussionVisibility.COURSE_SECTION:
            # Check if user is in the section
            if topic.section_id:
                section_enrollment = await Enrollment.filter(
                    user=current_user,
                    course=topic.forum.course,
                    section_id=topic.section_id,
                    state=EnrollmentState.ACTIVE,
                ).exists()
                can_view = section_enrollment or current_user.id == topic.author_id
        elif topic.visibility == DiscussionVisibility.GROUP:
            # Check if user is in one of the visible groups
            is_in_group = await Group.filter(
                id__in=[g.id for g in await topic.visible_to_groups.all()],
                memberships__user=current_user,
                memberships__is_active=True,
            ).exists()
            can_view = is_in_group or current_user.id == topic.author_id
        
        # Check if user is explicitly granted access
        is_explicit_user = await topic.visible_to_users.filter(id=current_user.id).exists()
        if is_explicit_user:
            can_view = True
        
        if not can_view:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this topic",
            )
    
    # Create query
    query = DiscussionReply.filter(topic=topic)
    
    # Apply parent filter
    if parent_id is not None:
        query = query.filter(parent_reply_id=parent_id)
    else:
        # If no parent filter, show only top-level replies
        query = query.filter(parent_reply=None)
    
    # Order by creation date
    query = query.order_by("created_at")
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=DiscussionReplyResponse,
    )


@router.put("/replies/{reply_id}", response_model=DiscussionReplyResponse)
async def update_discussion_reply(
    reply_in: DiscussionReplyUpdate,
    reply_id: int = Path(..., description="The ID of the discussion reply"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update discussion reply
    """
    # Get reply
    reply = await DiscussionReply.get_or_none(id=reply_id).prefetch_related("topic", "topic__forum", "topic__forum__course")
    
    if not reply:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion reply not found",
        )
    
    # Check if user can update this reply
    if current_user.role != UserRole.ADMIN:
        if reply.author_id != current_user.id:
            # Check if user is instructor
            is_instructor = await Enrollment.filter(
                user=current_user,
                course=reply.topic.forum.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()
            
            if not is_instructor:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to update this reply",
                )
    
    # Update fields
    reply.message = reply_in.message
    reply.is_edited = True
    reply.edited_at = datetime.utcnow()
    
    # Save reply
    await reply.save()
    
    return reply


@router.delete("/replies/{reply_id}", response_model=Dict[str, Any])
async def delete_discussion_reply(
    reply_id: int = Path(..., description="The ID of the discussion reply"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete discussion reply
    """
    # Get reply
    reply = await DiscussionReply.get_or_none(id=reply_id).prefetch_related("topic", "topic__forum", "topic__forum__course")
    
    if not reply:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion reply not found",
        )
    
    # Check if user can delete this reply
    if current_user.role != UserRole.ADMIN:
        if reply.author_id != current_user.id:
            # Check if user is instructor
            is_instructor = await Enrollment.filter(
                user=current_user,
                course=reply.topic.forum.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()
            
            if not is_instructor:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to delete this reply",
                )
    
    # Check if reply has child replies
    has_children = await DiscussionReply.filter(parent_reply=reply).exists()
    
    if has_children:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a reply with child replies",
        )
    
    # Delete reply
    await reply.delete()
    
    return {"message": "Discussion reply deleted successfully"}


@router.post("/replies/{reply_id}/like", response_model=Dict[str, Any])
async def like_discussion_reply(
    reply_id: int = Path(..., description="The ID of the discussion reply"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Like a discussion reply
    """
    # Get reply
    reply = await DiscussionReply.get_or_none(id=reply_id).prefetch_related("topic", "topic__forum", "topic__forum__course")
    
    if not reply:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion reply not found",
        )
    
    # Check if user can like this reply
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=reply.topic.forum.course,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )
        
        # Check if liking is allowed
        if not reply.topic.allow_liking:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Liking is not allowed for this topic",
            )
    
    # Check if user already liked this reply
    existing_like = await DiscussionReplyLike.get_or_none(reply=reply, user=current_user)
    
    if existing_like:
        # Remove like
        await existing_like.delete()
        
        # Update like count
        reply.like_count = max(0, reply.like_count - 1)
        await reply.save()
        
        return {"message": "Like removed successfully"}
    else:
        # Add like
        await DiscussionReplyLike.create(
            reply=reply,