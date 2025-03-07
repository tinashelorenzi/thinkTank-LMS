from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.group import (
    Group, GroupSet, GroupMembership, GroupAssignment, PeerReview, GroupInvitation,
    GroupType
)
from models.assignment import Assignment
from models.submission import Submission
from schemas.group import (
    GroupCreate, GroupUpdate, GroupResponse, GroupListResponse,
    GroupSetCreate, GroupSetUpdate, GroupSetResponse, GroupSetListResponse,
    GroupMembershipCreate, GroupMembershipUpdate, GroupMembershipResponse,
    GroupAssignmentCreate, GroupAssignmentResponse, PeerReviewCreate, PeerReviewResponse,
    GroupInvitationCreate, GroupInvitationResponse, RandomizeGroupsRequest
)
from schemas.submission import SubmissionResponse
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.email import send_email_background
from utils.pagination import get_page_params, paginate_queryset, PageParams
from utils.hashing import generate_join_code
from core.config import settings
from datetime import datetime, timedelta
import random

# Create groups router
router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
        group_in: GroupCreate,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new group (instructor or admin only)
    """
    # Check course if provided
    course = None
    if group_in.course_id:
        course = await Course.get_or_none(id=group_in.course_id)

        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        # Check if user has permission to create groups for this course
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
                    detail="You don't have permission to create groups for this course",
                )

    # Check group set if provided
    group_set = None
    if group_in.group_set_id:
        group_set = await GroupSet.get_or_none(id=group_in.group_set_id)

        if not group_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group set not found",
            )

        # Group must belong to the same course as the group set
        if course and group_set.course_id != course.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Group set belongs to a different course",
            )

        # If course not provided, get it from the group set
        if not course:
            course = await Course.get(id=group_set.course_id)

    # Check leader if provided
    leader = None
    if group_in.leader_id:
        leader = await User.get_or_none(id=group_in.leader_id)

        if not leader:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leader not found",
            )

        # Check if leader is enrolled in the course
        if course:
            enrollment = await Enrollment.get_or_none(
                user=leader,
                course=course,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Leader is not enrolled in the course",
                )

    # Generate join code if self signup is enabled
    join_code = None
    if group_in.allow_self_signup:
        join_code = generate_join_code()

    # Create group
    group = await Group.create(
        name=group_in.name,
        description=group_in.description,
        course=course,
        group_set=group_set,
        max_members=group_in.max_members,
        is_active=group_in.is_active,
        join_code=join_code,
        allow_self_signup=group_in.allow_self_signup,
        leader=leader,
    )

    # Add initial members if specified
    if group_in.member_ids:
        for member_id in group_in.member_ids:
            member = await User.get_or_none(id=member_id)

            if member:
                # Check if member is enrolled in the course
                if course:
                    enrollment = await Enrollment.get_or_none(
                        user=member,
                        course=course,
                        state=EnrollmentState.ACTIVE,
                    )

                    if not enrollment:
                        continue  # Skip users not enrolled in the course

                # Add member to group
                await GroupMembership.create(
                    group=group,
                    user=member,
                    is_active=True,
                    role="member" if member.id != group_in.leader_id else "leader",
                )

                # Send notification to member
                if course:
                    send_email_background(
                        background_tasks=background_tasks,
                        email_to=member.email,
                        subject=f"You've been added to a group in {course.name}",
                        template_name="group_notification",
                        template_data={
                            "username": member.username,
                            "course_name": course.name,
                            "group_name": group.name,
                            "group_url": f"{settings.SERVER_HOST}/courses/{course.id}/groups/{group.id}",
                            "project_name": settings.PROJECT_NAME,
                        },
                    )

    # If leader wasn't added as a member, add them now
    if leader and not any(id == leader.id for id in (group_in.member_ids or [])):
        await GroupMembership.create(
            group=group,
            user=leader,
            is_active=True,
            role="leader",
        )

    return group


@router.get("", response_model=GroupListResponse)
async def list_groups(
        page_params: PageParams = Depends(get_page_params),
        course_id: Optional[int] = Query(None, description="Filter by course ID"),
        group_set_id: Optional[int] = Query(None, description="Filter by group set ID"),
        is_active: Optional[bool] = Query(None, description="Filter by active status"),
        search: Optional[str] = Query(None, description="Search by name"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List groups with various filters
    """
    # Create base query
    query = Group.all()

    # Apply course filter
    if course_id:
        query = query.filter(course_id=course_id)

        # Check if user can access this course
        if current_user.role != UserRole.ADMIN:
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

    # Apply group set filter
    if group_set_id:
        query = query.filter(group_set_id=group_set_id)

    # Apply active filter
    if is_active is not None:
        query = query.filter(is_active=is_active)

    # Apply search filter
    if search:
        query = query.filter(name__icontains=search)

    # For non-admin/non-instructor users, only show their own groups or groups they can join
    if current_user.role != UserRole.ADMIN:
        is_instructor = False

        if course_id:
            is_instructor = await Enrollment.filter(
                user=current_user,
                course_id=course_id,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()

        if not is_instructor:
            # Show groups the user is a member of or can join (self-signup)
            query = query.filter(
                # User's groups
                (Group.memberships.filter(user=current_user, is_active=True)) |
                # Groups with self-signup enabled
                (Group.allow_self_signup == True)
            )

    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=GroupResponse,
    )


@router.get("/my", response_model=GroupListResponse)
async def list_user_groups(
        page_params: PageParams = Depends(get_page_params),
        course_id: Optional[int] = Query(None, description="Filter by course ID"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List groups the current user is a member of
    """
    # Create base query for user's groups
    query = Group.filter(
        memberships__user=current_user,
        memberships__is_active=True,
    )

    # Apply course filter
    if course_id:
        query = query.filter(course_id=course_id)

    # Only show active groups
    query = query.filter(is_active=True)

    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=GroupResponse,
    )


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
        group_id: int = Path(..., description="The ID of the group"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get group by ID
    """
    # Get group with related objects
    group = await Group.get_or_none(id=group_id).prefetch_related("course", "group_set", "leader")

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Check if user can access this group
    if current_user.role != UserRole.ADMIN:
        # Check if user is enrolled in the course
        if group.course:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=group.course,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not enrolled in this course",
                )

            # Students can only see their own groups or groups they can join
            if enrollment.type != EnrollmentType.TEACHER:
                is_member = await GroupMembership.filter(
                    group=group,
                    user=current_user,
                    is_active=True,
                ).exists()

                if not is_member and not group.allow_self_signup:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have access to this group",
                    )

    # Get members
    memberships = await GroupMembership.filter(
        group=group,
        is_active=True,
    ).prefetch_related("user")

    group.members = [membership.user for membership in memberships]
    group.member_count = len(group.members)

    return group


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
        group_in: GroupUpdate,
        group_id: int = Path(..., description="The ID of the group"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update a group (instructor or admin only)
    """
    # Get group
    group = await Group.get_or_none(id=group_id).prefetch_related("course")

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Check if user has permission to update this group
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        if group.course:
            instructor_enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=group.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            )

            if not instructor_enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to update this group",
                )

    # Check leader if changed
    if group_in.leader_id is not None and group_in.leader_id != group.leader_id:
        if group_in.leader_id:
            leader = await User.get_or_none(id=group_in.leader_id)

            if not leader:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Leader not found",
                )

            # Check if leader is a member of the group
            is_member = await GroupMembership.filter(
                group=group,
                user=leader,
                is_active=True,
            ).exists()

            if not is_member:
                # Add leader to group if not already a member
                await GroupMembership.create(
                    group=group,
                    user=leader,
                    is_active=True,
                    role="leader",
                )
            else:
                # Update existing membership to leader role
                membership = await GroupMembership.get(
                    group=group,
                    user=leader,
                )
                membership.role = "leader"
                await membership.save()

            group.leader = leader
        else:
            group.leader = None

    # Update fields
    for field, value in group_in.dict(exclude_unset=True, exclude={"leader_id", "member_ids"}).items():
        setattr(group, field, value)

    # Update join code if self-signup changed
    if group_in.allow_self_signup is not None:
        if group_in.allow_self_signup and not group.join_code:
            group.join_code = generate_join_code()
        elif not group_in.allow_self_signup:
            group.join_code = None

    # Save group
    await group.save()

    # Update members if specified
    if group_in.member_ids is not None:
        # Get current members
        current_memberships = await GroupMembership.filter(
            group=group,
            is_active=True,
        )
        current_member_ids = {membership.user_id for membership in current_memberships}

        # Members to add
        to_add = set(group_in.member_ids) - current_member_ids
        for user_id in to_add:
            user = await User.get_or_none(id=user_id)

            if user:
                # Check if member is enrolled in the course
                if group.course:
                    enrollment = await Enrollment.get_or_none(
                        user=user,
                        course=group.course,
                        state=EnrollmentState.ACTIVE,
                    )

                    if not enrollment:
                        continue  # Skip users not enrolled in the course

                # Add member to group
                await GroupMembership.create(
                    group=group,
                    user=user,
                    is_active=True,
                    role="member" if user.id != group.leader_id else "leader",
                )

        # Members to remove
        to_remove = current_member_ids - set(group_in.member_ids)
        for user_id in to_remove:
            # Don't remove the leader
            if user_id == group.leader_id:
                continue

            # Deactivate membership
            membership = await GroupMembership.get(
                group=group,
                user_id=user_id,
            )
            membership.is_active = False
            membership.left_at = datetime.utcnow()
            await membership.save()

    # Get members for response
    memberships = await GroupMembership.filter(
        group=group,
        is_active=True,
    ).prefetch_related("user")

    group.members = [membership.user for membership in memberships]
    group.member_count = len(group.members)

    return group


@router.delete("/{group_id}", response_model=Dict[str, Any])
async def delete_group(
        group_id: int = Path(..., description="The ID of the group"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete a group (instructor or admin only)
    """
    # Get group
    group = await Group.get_or_none(id=group_id).prefetch_related("course")

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Check if user has permission to delete this group
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        if group.course:
            instructor_enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=group.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            )

            if not instructor_enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to delete this group",
                )

    # Check if group has submissions
    has_submissions = await group.submissions.exists()

    if has_submissions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete group with existing submissions",
        )

    # Delete group
    await group.delete()

    return {"message": "Group deleted successfully"}


@router.post("/join/{join_code}", response_model=GroupResponse)
async def join_group_by_code(
        join_code: str = Path(..., description="The join code of the group"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Join a group using its join code
    """
    # Find group by join code
    group = await Group.get_or_none(join_code=join_code, allow_self_signup=True, is_active=True)

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found or self-signup not allowed",
        )

    # Check if user is already a member
    existing_membership = await GroupMembership.get_or_none(
        group=group,
        user=current_user,
    )

    if existing_membership:
        if existing_membership.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already a member of this group",
            )
        else:
            # Reactivate membership
            existing_membership.is_active = True
            existing_membership.left_at = None
            await existing_membership.save()

            return await get_group(group.id, current_user)

    # Check if user is enrolled in the course
    if group.course:
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=group.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    # Check if group has reached maximum members
    if group.max_members:
        member_count = await GroupMembership.filter(
            group=group,
            is_active=True,
        ).count()

        if member_count >= group.max_members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Group has reached maximum members",
            )

    # Add user to group
    await GroupMembership.create(
        group=group,
        user=current_user,
        is_active=True,
        role="member",
    )

    return await get_group(group.id, current_user)


@router.post("/{group_id}/leave", response_model=Dict[str, Any])
async def leave_group(
        group_id: int = Path(..., description="The ID of the group"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Leave a group
    """
    # Get group
    group = await Group.get_or_none(id=group_id)

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Check if user is a member
    membership = await GroupMembership.get_or_none(
        group=group,
        user=current_user,
        is_active=True,
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are not a member of this group",
        )

    # Check if user is the leader
    if group.leader_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group leader cannot leave the group",
        )

    # Deactivate membership
    membership.is_active = False
    membership.left_at = datetime.utcnow()
    await membership.save()

    return {"message": "You have left the group successfully"}


@router.post("/sets", response_model=GroupSetResponse, status_code=status.HTTP_201_CREATED)
async def create_group_set(
        group_set_in: GroupSetCreate,
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new group set (instructor or admin only)
    """
    # Get course
    course = await Course.get_or_none(id=group_set_in.course_id)

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Check if user has permission to create group sets for this course
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
                detail="You don't have permission to create group sets for this course",
            )

    # Create group set
    group_set = await GroupSet.create(
        name=group_set_in.name,
        description=group_set_in.description,
        course=course,
        group_type=group_set_in.group_type,
        allow_self_signup=group_set_in.allow_self_signup,
        self_signup_deadline=group_set_in.self_signup_deadline,
        create_group_count=group_set_in.create_group_count,
        members_per_group=group_set_in.members_per_group,
        is_active=group_set_in.is_active,
    )

    # If random groups are requested, create them now
    if group_set.group_type == GroupType.RANDOM and group_set.create_group_count:
        # Get enrolled students
        students = await User.filter(
            enrollments__course=course,
            enrollments__type=EnrollmentType.STUDENT,
            enrollments__state=EnrollmentState.ACTIVE,
        ).all()

        # Randomize student order
        random.shuffle(students)

        # Create groups
        groups_created = 0
        for i in range(group_set.create_group_count):
            # Create group
            group = await Group.create(
                name=f"{group_set.name} Group {i+1}",
                course=course,
                group_set=group_set,
                max_members=group_set.members_per_group,
                is_active=True,
            )

            # Add members
            start_idx = i * group_set.members_per_group
            end_idx = min((i + 1) * group_set.members_per_group, len(students))

            if start_idx >= len(students):
                break  # No more students to add

            group_members = students[start_idx:end_idx]

            for student in group_members:
                await GroupMembership.create(
                    group=group,
                    user=student,
                    is_active=True,
                    role="member",
                )

            groups_created += 1

        group_set.group_count = groups_created
    else:
        group_set.group_count = 0

    return group_set


@router.get("/sets", response_model=GroupSetListResponse)
async def list_group_sets(
        page_params: PageParams = Depends(get_page_params),
        course_id: int = Query(..., description="Course ID"),
        is_active: Optional[bool] = Query(None, description="Filter by active status"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List group sets for a course
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
    query = GroupSet.filter(course=course)

    # Apply active filter
    if is_active is not None:
        query = query.filter(is_active=is_active)

    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=GroupSetResponse,
    )


@router.get("/sets/{group_set_id}", response_model=GroupSetResponse)
async def get_group_set(
        group_set_id: int = Path(..., description="The ID of the group set"),
        include_groups: bool = Query(False, description="Include groups in response"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get group set by ID
    """
    # Get group set
    group_set = await GroupSet.get_or_none(id=group_set_id).prefetch_related("course")

    if not group_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group set not found",
        )

    # Check if user can access this group set
    if current_user.role != UserRole.ADMIN:
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=group_set.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    # Get group count
    group_set.group_count = await Group.filter(group_set=group_set).count()

    # Include groups if requested
    if include_groups:
        group_set.groups = await Group.filter(group_set=group_set).all()

    return group_set


@router.put("/sets/{group_set_id}", response_model=GroupSetResponse)
async def update_group_set(
        group_set_in: GroupSetUpdate,
        group_set_id: int = Path(..., description="The ID of the group set"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update a group set (instructor or admin only)
    """
    # Get group set
    group_set = await GroupSet.get_or_none(id=group_set_id).prefetch_related("course")

    if not group_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group set not found",
        )

    # Check if user has permission to update this group set
    if current_user.role != UserRole.ADMIN:
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=group_set.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this group set",
            )

    # Update fields
    for field, value in group_set_in.dict(exclude_unset=True).items():
        setattr(group_set, field, value)

    # Save group set
    await group_set.save()

    # Get group count
    group_set.group_count = await Group.filter(group_set=group_set).count()

    return group_set


@router.delete("/sets/{group_set_id}", response_model=Dict[str, Any])
async def delete_group_set(
        group_set_id: int = Path(..., description="The ID of the group set"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete a group set (instructor or admin only)
    """
    # Get group set
    group_set = await GroupSet.get_or_none(id=group_set_id).prefetch_related("course")

    if not group_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group set not found",
        )

    # Check if user has permission to delete this group set
    if current_user.role != UserRole.ADMIN:
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=group_set.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this group set",
            )

    # Check if group set has groups
    group_count = await Group.filter(group_set=group_set).count()

    if group_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete group set with {group_count} groups. Remove groups first.",
        )

    # Delete group set
    await group_set.delete()

    return {"message": "Group set deleted successfully"}


@router.post("/sets/{group_set_id}/randomize", response_model=GroupSetResponse)
async def randomize_groups(
        randomize_in: RandomizeGroupsRequest,
        group_set_id: int = Path(..., description="The ID of the group set"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Randomize groups in a group set (instructor or admin only)
    """
    # Get group set
    group_set = await GroupSet.get_or_none(id=group_set_id).prefetch_related("course")

    if not group_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group set not found",
        )

    # Check if user has permission to update this group set
    if current_user.role != UserRole.ADMIN:
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=group_set.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this group set",
            )

    # Get all existing groups in the set
    existing_groups = await Group.filter(group_set=group_set).all()

    # Check if there are submissions associated with existing groups
    has_submissions = False
    for group in existing_groups:
        if await group.submissions.exists():
            has_submissions = True
            break

    if has_submissions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot randomize groups that have submissions",
        )

    # Get enrolled students
    students = await User.filter(
        enrollments__course=group_set.course,
        enrollments__type=EnrollmentType.STUDENT,
        enrollments__state=EnrollmentState.ACTIVE,
    ).all()

    # Handle existing members if needed
    existing_members = set()
    if not randomize_in.include_existing_members:
        for group in existing_groups:
            memberships = await GroupMembership.filter(
                group=group,
                is_active=True,
            ).all()
            for membership in memberships:
                existing_members.add(membership.user_id)

        # Filter students to exclude existing members
        students = [s for s in students if s.id not in existing_members]

    # Delete existing groups if any
    for group in existing_groups:
        await group.delete()

    # Randomize student order
    random.shuffle(students)

    # Create groups
    groups_created = 0
    members_per_group = randomize_in.members_per_group or group_set.members_per_group or 4

    for i in range(randomize_in.count):
        # Create group
        group = await Group.create(
            name=f"{group_set.name} Group {i+1}",
            course=group_set.course,
            group_set=group_set,
            max_members=members_per_group,
            is_active=True,
        )

        # Add members
        start_idx = i * members_per_group
        end_idx = min((i + 1) * members_per_group, len(students))

        if start_idx >= len(students):
            break  # No more students to add

        group_members = students[start_idx:end_idx]

        for student in group_members:
            await GroupMembership.create(
                group=group,
                user=student,
                is_active=True,
                role="member",
            )

        groups_created += 1

    # Update group set
    group_set.group_count = groups_created

    return group_set


@router.post("/assignments", response_model=GroupAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_group_assignment(
        assignment_in: GroupAssignmentCreate,
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new group assignment (instructor or admin only)
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=assignment_in.assignment_id).prefetch_related("course")

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    # Get group set
    group_set = await GroupSet.get_or_none(id=assignment_in.group_set_id).prefetch_related("course")

    if not group_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group set not found",
        )

    # Check if both are in the same course
    if assignment.course_id != group_set.course_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment and group set must be in the same course",
        )

    # Check if user has permission to create group assignments
    if current_user.role != UserRole.ADMIN:
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create group assignments for this course",
            )

    # Check if assignment is already a group assignment
    existing = await GroupAssignment.get_or_none(assignment=assignment)

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This assignment is already a group assignment",
        )

    # Create group assignment
    group_assignment = await GroupAssignment.create(
        assignment=assignment,
        group_set=group_set,
        require_all_members=assignment_in.require_all_members,
        grade_individually=assignment_in.grade_individually,
    )

    # Update assignment to indicate it's a group assignment
    assignment.is_group_assignment = True
    await assignment.save()

    return group_assignment


@router.get("/assignments/{assignment_id}", response_model=GroupAssignmentResponse)
async def get_group_assignment(
        assignment_id: int = Path(..., description="The ID of the assignment"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get group assignment by assignment ID
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=assignment_id).prefetch_related("course")

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    # Get group assignment
    group_assignment = await GroupAssignment.get_or_none(assignment=assignment).prefetch_related("group_set")

    if not group_assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group assignment not found",
        )

    # Check if user can access this assignment
    if current_user.role != UserRole.ADMIN:
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    return group_assignment


@router.delete("/assignments/{assignment_id}", response_model=Dict[str, Any])
async def delete_group_assignment(
        assignment_id: int = Path(..., description="The ID of the assignment"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete a group assignment (instructor or admin only)
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=assignment_id).prefetch_related("course")

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    # Get group assignment
    group_assignment = await GroupAssignment.get_or_none(assignment=assignment)

    if not group_assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group assignment not found",
        )

    # Check if user has permission to delete this group assignment
    if current_user.role != UserRole.ADMIN:
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete group assignments for this course",
            )

    # Check if there are group submissions
    submission_count = await assignment.submissions.filter(group__isnull=False).count()

    if submission_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete group assignment with {submission_count} group submissions",
        )

    # Delete group assignment
    await group_assignment.delete()

    # Update assignment
    assignment.is_group_assignment = False
    await assignment.save()

    return {"message": "Group assignment deleted successfully"}


@router.post("/peer-reviews", response_model=PeerReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_peer_review(
        review_in: PeerReviewCreate,
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new peer review assignment (instructor or admin only)
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=review_in.assignment_id).prefetch_related("course")

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    # Get reviewer
    reviewer = await User.get_or_none(id=review_in.reviewer_id)

    if not reviewer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reviewer not found",
        )

    # Get reviewee
    reviewee = await User.get_or_none(id=review_in.reviewee_id)

    if not reviewee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reviewee not found",
        )

    # Check if user has permission to create peer reviews
    if current_user.role != UserRole.ADMIN:
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create peer reviews for this course",
            )

    # Check if reviewers and reviewees are enrolled in the course
    reviewer_enrollment = await Enrollment.get_or_none(
        user=reviewer,
        course=assignment.course,
        state=EnrollmentState.ACTIVE,
    )

    if not reviewer_enrollment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reviewer is not enrolled in the course",
        )

    reviewee_enrollment = await Enrollment.get_or_none(
        user=reviewee,
        course=assignment.course,
        state=EnrollmentState.ACTIVE,
    )

    if not reviewee_enrollment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reviewer is not enrolled in the course",
        )

    # Check if there's a submission to review
    submission = None
    if review_in.submission_id:
        submission = await Submission.get_or_none(id=review_in.submission_id, assignment=assignment)

        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found",
            )

    # Create peer review
    peer_review = await PeerReview.create(
        assignment=assignment,
        reviewer=reviewer,
        reviewee=reviewee,
        submission=submission,
        is_completed=False,
    )

    return peer_review


@router.get("/peer-reviews", response_model=List[PeerReviewResponse])
async def list_peer_reviews(
        assignment_id: int = Query(..., description="Assignment ID"),
        reviewer_id: Optional[int] = Query(None, description="Filter by reviewer ID"),
        reviewee_id: Optional[int] = Query(None, description="Filter by reviewee ID"),
        is_completed: Optional[bool] = Query(None, description="Filter by completion status"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List peer reviews for an assignment
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=assignment_id).prefetch_related("course")

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    # Check if user can access this assignment
    is_instructor = False
    if current_user.role != UserRole.ADMIN:
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

        is_instructor = enrollment.type == EnrollmentType.TEACHER
    else:
        is_instructor = True

    # Create base query
    query = PeerReview.filter(assignment=assignment)

    # Apply reviewer filter
    if reviewer_id:
        query = query.filter(reviewer_id=reviewer_id)
    elif not is_instructor:
        # For students, only show their own reviews to complete
        query = query.filter(reviewer=current_user)

    # Apply reviewee filter
    if reviewee_id:
        query = query.filter(reviewee_id=reviewee_id)

    # Apply completion filter
    if is_completed is not None:
        query = query.filter(is_completed=is_completed)

    # Get reviews
    reviews = await query.all()

    return reviews


@router.get("/peer-reviews/{review_id}", response_model=PeerReviewResponse)
async def get_peer_review(
        review_id: int = Path(..., description="The ID of the peer review"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get peer review by ID
    """
    # Get peer review
    review = await PeerReview.get_or_none(id=review_id).prefetch_related(
        "assignment", "assignment__course", "reviewer", "reviewee", "submission"
    )

    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Peer review not found",
        )

    # Check if user can access this review
    if current_user.role != UserRole.ADMIN:
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=review.assignment.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

        # Students can only see reviews they are assigned to complete
        if enrollment.type != EnrollmentType.TEACHER and review.reviewer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this peer review",
            )

    return review


@router.put("/peer-reviews/{review_id}", response_model=PeerReviewResponse)
async def complete_peer_review(
        review_id: int = Path(..., description="The ID of the peer review"),
        comments: str = Query(..., description="Review comments"),
        rating: Optional[float] = Query(None, description="Review rating"),
        rubric_assessment: Optional[Dict[str, Any]] = Query(None, description="Rubric assessment data"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Complete a peer review
    """
    # Get peer review
    review = await PeerReview.get_or_none(id=review_id).prefetch_related(
        "assignment", "assignment__course", "reviewer", "reviewee"
    )

    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Peer review not found",
        )

    # Check if user is the assigned reviewer
    if review.reviewer_id != current_user.id and current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=review.assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )

        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to complete this peer review",
            )

    # Update review
    review.comments = comments
    review.rating = rating
    review.rubric_assessment = rubric_assessment
    review.is_completed = True
    review.completed_at = datetime.utcnow()

    await review.save()

    return review


@router.post("/invitations", response_model=GroupInvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_group_invitation(
        invitation_in: GroupInvitationCreate,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create a new group invitation
    """
    # Get group
    group = await Group.get_or_none(id=invitation_in.group_id).prefetch_related("course")

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Get user to invite
    invitee = await User.get_or_none(id=invitation_in.user_id)

    if not invitee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if user has permission to send invitations
    if current_user.role != UserRole.ADMIN:
        # Check if user is a member of the group
        is_member = await GroupMembership.filter(
            group=group,
            user=current_user,
            is_active=True,
        ).exists()

        # Or an instructor of the course
        is_instructor = False
        if group.course:
            is_instructor = await Enrollment.filter(
                user=current_user,
                course=group.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()

        if not is_member and not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to send invitations for this group",
            )

    # Check if user is already a member
    is_already_member = await GroupMembership.filter(
        group=group,
        user=invitee,
        is_active=True,
    ).exists()

    if is_already_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this group",
        )

    # Check if there's already a pending invitation
    existing_invitation = await GroupInvitation.get_or_none(
        group=group,
        user=invitee,
        status="pending",
    )

    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An invitation is already pending for this user",
        )

    # Set expiration date (default to 7 days)
    expires_at = invitation_in.expires_at or (datetime.utcnow() + timedelta(days=7))

    # Create invitation
    invitation = await GroupInvitation.create(
        group=group,
        user=invitee,
        inviter=current_user,
        status="pending",
        message=invitation_in.message,
        expires_at=expires_at,
    )

    # Send email notification
    if group.course:
        send_email_background(
            background_tasks=background_tasks,
            email_to=invitee.email,
            subject=f"Invitation to join group: {group.name}",
            template_name="group_invitation",
            template_data={
                "username": invitee.username,
                "course_name": group.course.name,
                "group_name": group.name,
                "inviter_name": current_user.username,
                "message": invitation.message or "Join our group!",
                "expires_at": invitation.expires_at.strftime("%Y-%m-%d"),
                "invitation_url": f"{settings.SERVER_HOST}/courses/{group.course.id}/groups/invitations/{invitation.id}",
                "project_name": settings.PROJECT_NAME,
            },
        )

    return invitation


@router.get("/invitations/my", response_model=List[GroupInvitationResponse])
async def list_user_invitations(
        status: Optional[str] = Query(None, description="Filter by status"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List invitations for the current user
    """
    # Create base query
    query = GroupInvitation.filter(user=current_user)

    # Apply status filter
    if status:
        query = query.filter(status=status)

    # Get all invitations
    invitations = await query.prefetch_related("group", "inviter").all()

    return invitations


@router.post("/invitations/{invitation_id}/accept", response_model=GroupResponse)
async def accept_invitation(
        invitation_id: int = Path(..., description="The ID of the invitation"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Accept a group invitation
    """
    # Get invitation
    invitation = await GroupInvitation.get_or_none(id=invitation_id).prefetch_related("group")

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    # Check if invitation is for this user
    if invitation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is not for you",
        )

    # Check if invitation is pending
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation is already {invitation.status}",
        )

    # Check if invitation has expired
    if invitation.expires_at and invitation.expires_at < datetime.utcnow():
        invitation.status = "expired"
        await invitation.save()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    # Check if user is already a member
    is_member = await GroupMembership.filter(
        group=invitation.group,
        user=current_user,
        is_active=True,
    ).exists()

    if is_member:
        invitation.status = "accepted"
        invitation.responded_at = datetime.utcnow()
        await invitation.save()

        return await get_group(invitation.group.id, current_user)

    # Check if group has reached maximum members
    if invitation.group.max_members:
        member_count = await GroupMembership.filter(
            group=invitation.group,
            is_active=True,
        ).count()

        if member_count >= invitation.group.max_members:
            invitation.status = "rejected"
            invitation.responded_at = datetime.utcnow()
            await invitation.save()

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Group has reached maximum members",
            )

    # Add user to group
    await GroupMembership.create(
        group=invitation.group,
        user=current_user,
        is_active=True,
        role="member",
    )

    # Update invitation
    invitation.status = "accepted"
    invitation.responded_at = datetime.utcnow()
    await invitation.save()

    return await get_group(invitation.group.id, current_user)


@router.post("/invitations/{invitation_id}/decline", response_model=Dict[str, Any])
async def decline_invitation(
        invitation_id: int = Path(..., description="The ID of the invitation"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Decline a group invitation
    """
    # Get invitation
    invitation = await GroupInvitation.get_or_none(id=invitation_id)

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    # Check if invitation is for this user
    if invitation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is not for you",
        )

    # Check if invitation is pending
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation is already {invitation.status}",
        )

    # Update invitation
    invitation.status = "declined"
    invitation.responded_at = datetime.utcnow()
    await invitation.save()

    return {"message": "Invitation declined successfully"}