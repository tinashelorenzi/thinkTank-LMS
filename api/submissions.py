from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, UploadFile, File, BackgroundTasks

from models.course import Course
from models.users import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.assignment import Assignment
from models.submission import Submission, SubmissionAttachment, Grade, Comment, SubmissionStatus
from models.group import Group
from schemas.submission import (
    SubmissionCreate, SubmissionUpdate, SubmissionResponse, SubmissionListResponse,
    GradeCreate, GradeUpdate, GradeResponse, CommentCreate, CommentResponse,
    SubmissionAttachmentCreate, SubmissionAttachmentResponse, BulkGradeUpdate, SubmissionAnalytics
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.email import send_email_background
from utils.pagination import get_page_params, paginate_queryset, PageParams
from utils.files import save_upload_file
from core.config import settings

# Create submissions router
router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_submission(
    submission_in: SubmissionCreate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create new submission
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=submission_in.assignment_id).prefetch_related("course")
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
    
    # Check if assignment is published
    if not assignment.published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot submit to an unpublished assignment",
        )
    
    # Check if user is enrolled in the course
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
    
    # Check if submission is valid for the assignment type
    if submission_in.submission_type not in assignment.submission_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid submission type. Allowed types: {assignment.submission_types}",
        )
    
    # Check group if this is a group submission
    group = None
    if submission_in.group_id:
        group = await Group.get_or_none(id=submission_in.group_id)
        
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )
        
        # Check if user is in the group
        group_member = await Group.filter(
            id=group.id,
            memberships__user=current_user,
            memberships__is_active=True,
        ).exists()
        
        if not group_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this group",
            )
    
    # Check if assignment requires a group but none was provided
    if assignment.is_group_assignment and not submission_in.group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This assignment requires a group submission",
        )
    
    # Check if maximum attempts has been reached
    submission_count = await Submission.filter(
        assignment=assignment,
        user=current_user,
    ).count()
    
    if assignment.max_attempts > 0 and submission_count >= assignment.max_attempts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum number of attempts ({assignment.max_attempts}) reached",
        )
    
    # Calculate if submission is late
    is_late = False
    if assignment.due_date and datetime.utcnow() > assignment.due_date:
        is_late = True
        
        # Check if late submissions are allowed
        if not assignment.allow_late_submissions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Late submissions are not allowed for this assignment",
            )
    
    # Create submission
    submission = await Submission.create(
        assignment=assignment,
        user=current_user,
        group=group,
        submission_type=submission_in.submission_type,
        body=submission_in.body,
        url=submission_in.url,
        status=SubmissionStatus.LATE if is_late else SubmissionStatus.SUBMITTED,
        attempt_number=submission_count + 1,
    )
    
    return submission


@router.post("/{submission_id}/attachments", response_model=SubmissionAttachmentResponse)
async def add_attachment(
    submission_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Add attachment to submission
    """
    # Get submission
    submission = await Submission.get_or_none(id=submission_id).prefetch_related("assignment", "assignment__course")
    
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    
    # Check if user owns this submission
    if submission.user_id != current_user.id:
        # Check if user is in the same group for group submissions
        if submission.group_id:
            group_member = await Group.filter(
                id=submission.group_id,
                memberships__user=current_user,
                memberships__is_active=True,
            ).exists()
            
            if not group_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to add attachments to this submission",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to add attachments to this submission",
            )
    
    # Check if file type is allowed for this assignment
    course_id = submission.assignment.course.id
    allowed_extensions = ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "zip", "jpg", "jpeg", "png", "gif"]
    
    # Save file
    upload_dir = f"uploads/courses/{course_id}/assignments/{submission.assignment_id}/submissions/{submission_id}"
    
    try:
        file_info = await save_upload_file(
            file,
            directory=upload_dir,
            allowed_extensions=allowed_extensions,
            max_size_bytes=10 * 1024 * 1024,  # 10MB
        )
        
        # Create attachment record
        attachment = await SubmissionAttachment.create(
            submission=submission,
            filename=file_info["original_filename"],
            file_path=file_info["filepath"],
            file_type=file_info["content_type"],
            file_size=file_info["size"],
        )
        
        return attachment
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=SubmissionListResponse)
async def list_submissions(
    page_params: PageParams = Depends(get_page_params),
    assignment_id: Optional[int] = Query(None, description="Filter by assignment ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    status: Optional[SubmissionStatus] = Query(None, description="Filter by submission status"),
    graded: Optional[bool] = Query(None, description="Filter by graded status"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List submissions with various filters
    """
    # Create base query
    query = Submission.all()
    
    # Apply filters
    if assignment_id:
        query = query.filter(assignment_id=assignment_id)
        
        # Get the assignment to check permissions
        assignment = await Assignment.get_or_none(id=assignment_id).prefetch_related("course")
        
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )
        
        # Check permissions
        if current_user.role != UserRole.ADMIN:
            # Check if user is the instructor of the course
            is_instructor = await Enrollment.filter(
                user=current_user,
                course=assignment.course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            ).exists()
            
            if is_instructor:
                # Instructors can see all submissions for their course
                pass
            else:
                # Students can only see their own submissions
                query = query.filter(user=current_user)
    else:
        # If no specific assignment, users can only see:
        if current_user.role == UserRole.ADMIN:
            # Admins can see all submissions
            pass
        elif current_user.role == UserRole.INSTRUCTOR:
            # Instructors can see submissions for courses they teach
            query = query.filter(
                assignment__course__enrollments__user=current_user,
                assignment__course__enrollments__type=EnrollmentType.TEACHER,
                assignment__course__enrollments__state=EnrollmentState.ACTIVE,
            )
        else:
            # Others can only see their own submissions
            query = query.filter(user=current_user)
    
    # Apply user filter (for instructors and admins)
    if user_id and current_user.role in [UserRole.ADMIN, UserRole.INSTRUCTOR]:
        query = query.filter(user_id=user_id)
    
    # Apply status filter
    if status:
        query = query.filter(status=status)
    
    # Apply graded filter
    if graded is not None:
        if graded:
            query = query.filter(grades__isnull=False)
        else:
            query = query.filter(grades__isnull=True)
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=SubmissionResponse,
    )


@router.get("/my", response_model=SubmissionListResponse)
async def list_user_submissions(
    page_params: PageParams = Depends(get_page_params),
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List current user's submissions
    """
    # Create base query for user's submissions
    query = Submission.filter(user=current_user)
    
    # Apply course filter
    if course_id:
        query = query.filter(assignment__course_id=course_id)
    
    # Order by newest first
    query = query.order_by("-submitted_at")
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=SubmissionResponse,
    )


@router.get("/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: int = Path(..., description="The ID of the submission"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get submission by ID
    """
    # Get submission with related models
    submission = await Submission.get_or_none(id=submission_id).prefetch_related(
        "assignment", "assignment__course", "user", "group", "files", "grades", "comments"
    )
    
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    
    # Check permissions
    if current_user.role == UserRole.ADMIN:
        # Admins can see all submissions
        pass
    elif current_user.role == UserRole.INSTRUCTOR:
        # Instructors can see submissions for courses they teach
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=submission.assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()
        
        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this submission",
            )
    else:
        # Students can only see their own submissions or group submissions
        if submission.user_id != current_user.id:
            # Check if user is in the same group for group submissions
            if submission.group_id:
                group_member = await Group.filter(
                    id=submission.group_id,
                    memberships__user=current_user,
                    memberships__is_active=True,
                ).exists()
                
                if not group_member:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You don't have permission to view this submission",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view this submission",
                )
    
    return submission


@router.put("/{submission_id}", response_model=SubmissionResponse)
async def update_submission(
    submission_in: SubmissionUpdate,
    submission_id: int = Path(..., description="The ID of the submission"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update submission
    """
    # Get submission
    submission = await Submission.get_or_none(id=submission_id).prefetch_related("assignment")
    
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    
    # Check if user owns this submission
    if submission.user_id != current_user.id:
        # Check if user is in the same group for group submissions
        if submission.group_id:
            group_member = await Group.filter(
                id=submission.group_id,
                memberships__user=current_user,
                memberships__is_active=True,
            ).exists()
            
            if not group_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to update this submission",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this submission",
            )
    
    # Check if submission can be updated (not graded yet)
    if await Grade.filter(submission=submission).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update a submission that has been graded",
        )
    
    # Update fields
    for field, value in submission_in.dict(exclude_unset=True).items():
        setattr(submission, field, value)
    
    # Save submission
    await submission.save()
    
    return submission


@router.post("/{submission_id}/grade", response_model=GradeResponse)
async def grade_submission(
    grade_in: GradeCreate,
    background_tasks: BackgroundTasks,
    submission_id: int = Path(..., description="The ID of the submission"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Grade a submission (instructor or admin only)
    """
    # Get submission
    submission = await Submission.get_or_none(id=submission_id).prefetch_related(
        "assignment", "assignment__course", "user"
    )
    
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    
    # Check if user has permission to grade this submission
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=submission.assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()
        
        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to grade this submission",
            )
    
    # Create grade
    grade = await Grade.create(
        submission=submission,
        grader=current_user,
        score=grade_in.score,
        feedback=grade_in.feedback,
        is_auto_graded=grade_in.is_auto_graded,
        rubric_assessment=grade_in.rubric_assessment,
        graded_at=datetime.utcnow(),
    )
    
    # Update submission status
    submission.status = SubmissionStatus.GRADED
    await submission.save()
    
    # Send notification email to student
    course_name = submission.assignment.course.name
    assignment_title = submission.assignment.title
    
    send_email_background(
        background_tasks=background_tasks,
        email_to=submission.user.email,
        subject=f"Grade Posted: {assignment_title}",
        template_name="grade_notification",
        template_data={
            "username": submission.user.username,
            "course_name": course_name,
            "assignment_title": assignment_title,
            "grade": f"{grade.score}/{submission.assignment.points_possible}",
            "feedback": grade.feedback or "No feedback provided",
            "grade_url": f"{settings.SERVER_HOST}/courses/{submission.assignment.course.id}/assignments/{submission.assignment.id}/submissions/{submission.id}",
            "project_name": settings.PROJECT_NAME,
        },
    )
    
    return grade


@router.post("/bulk-grade", response_model=Dict[str, Any])
async def bulk_grade_submissions(
    grade_in: BulkGradeUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Grade multiple submissions at once (instructor or admin only)
    """
    graded_count = 0
    failed_ids = []
    
    for submission_id in grade_in.submission_ids:
        try:
            # Get submission
            submission = await Submission.get_or_none(id=submission_id).prefetch_related(
                "assignment", "assignment__course", "user"
            )
            
            if not submission:
                failed_ids.append(submission_id)
                continue
            
            # Check if user has permission to grade this submission
            if current_user.role != UserRole.ADMIN:
                # Check if user is the instructor of the course
                is_instructor = await Enrollment.filter(
                    user=current_user,
                    course=submission.assignment.course,
                    type=EnrollmentType.TEACHER,
                    state=EnrollmentState.ACTIVE,
                ).exists()
                
                if not is_instructor:
                    failed_ids.append(submission_id)
                    continue
            
            # Create grade
            grade = await Grade.create(
                submission=submission,
                grader=grade_in.grader_id if grade_in.grader_id else current_user,
                score=grade_in.score,
                feedback=grade_in.feedback,
                rubric_assessment=grade_in.rubric_assessment,
                graded_at=datetime.utcnow(),
            )
            
            # Update submission status
            submission.status = SubmissionStatus.GRADED
            await submission.save()
            
            # Send notification email to student
            course_name = submission.assignment.course.name
            assignment_title = submission.assignment.title
            
            send_email_background(
                background_tasks=background_tasks,
                email_to=submission.user.email,
                subject=f"Grade Posted: {assignment_title}",
                template_name="grade_notification",
                template_data={
                    "username": submission.user.username,
                    "course_name": course_name,
                    "assignment_title": assignment_title,
                    "grade": f"{grade.score}/{submission.assignment.points_possible}",
                    "feedback": grade.feedback or "No feedback provided",
                    "grade_url": f"{settings.SERVER_HOST}/courses/{submission.assignment.course.id}/assignments/{submission.assignment.id}/submissions/{submission.id}",
                    "project_name": settings.PROJECT_NAME,
                },
            )
            
            graded_count += 1
        
        except Exception:
            failed_ids.append(submission_id)
    
    return {
        "message": "Bulk grading processed",
        "graded_count": graded_count,
        "failed_count": len(failed_ids),
        "failed_ids": failed_ids,
    }


@router.post("/{submission_id}/comment", response_model=CommentResponse)
async def add_comment(
    comment_in: CommentCreate,
    submission_id: int = Path(..., description="The ID of the submission"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Add comment to submission
    """
    # Get submission
    submission = await Submission.get_or_none(id=submission_id).prefetch_related(
        "assignment", "assignment__course"
    )
    
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    
    # Check permissions
    can_comment = False
    
    if current_user.role == UserRole.ADMIN:
        # Admins can comment on any submission
        can_comment = True
    elif current_user.role == UserRole.INSTRUCTOR:
        # Instructors can comment on submissions for courses they teach
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=submission.assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()
        
        can_comment = is_instructor
    else:
        # Students can comment on their own submissions or group submissions
        if submission.user_id == current_user.id:
            can_comment = True
        elif submission.group_id:
            # Check if user is in the same group
            group_member = await Group.filter(
                id=submission.group_id,
                memberships__user=current_user,
                memberships__is_active=True,
            ).exists()
            
            can_comment = group_member
    
    if not can_comment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to comment on this submission",
        )
    
    # Create comment
    comment = await Comment.create(
        submission=submission,
        author=current_user,
        text=comment_in.text,
        parent_id=comment_in.parent_id,
    )
    
    # Refresh to get related objects
    await comment.fetch_related("author")
    
    return comment


@router.get("/{submission_id}/comments", response_model=List[CommentResponse])
async def list_comments(
    submission_id: int = Path(..., description="The ID of the submission"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List comments for a submission
    """
    # Get submission
    submission = await Submission.get_or_none(id=submission_id).prefetch_related(
        "assignment", "assignment__course"
    )
    
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    
    # Check permissions
    can_view = False
    
    if current_user.role == UserRole.ADMIN:
        # Admins can view any submission
        can_view = True
    elif current_user.role == UserRole.INSTRUCTOR:
        # Instructors can view submissions for courses they teach
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=submission.assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()
        
        can_view = is_instructor
    else:
        # Students can view their own submissions or group submissions
        if submission.user_id == current_user.id:
            can_view = True
        elif submission.group_id:
            # Check if user is in the same group
            group_member = await Group.filter(
                id=submission.group_id,
                memberships__user=current_user,
                memberships__is_active=True,
            ).exists()
            
            can_view = group_member
    
    if not can_view:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view comments for this submission",
        )
    
    # Get top-level comments
    comments = await Comment.filter(
        submission=submission,
        parent=None,
    ).prefetch_related("author", "replies", "replies__author").all()
    
    return comments


@router.get("/analytics/user/{user_id}", response_model=SubmissionAnalytics)
async def get_user_submission_analytics(
    user_id: int = Path(..., description="The ID of the user"),
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get analytics for a user's submissions
    """
    # Check permissions
    if current_user.id != user_id and current_user.role not in [UserRole.ADMIN, UserRole.INSTRUCTOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view analytics for this user",
        )
    
    # If instructor, check if they teach the course (if specified)
    if current_user.role == UserRole.INSTRUCTOR and course_id:
        is_instructor = await Enrollment.filter(
            user=current_user,
            course_id=course_id,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()
        
        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view analytics for this course",
            )
    
    # Get user
    user = await User.get_or_none(id=user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Create base query for user's submissions
    query = Submission.filter(user=user)
    
    # Add course filter if specified
    if course_id:
        query = query.filter(assignment__course_id=course_id)
    
    # Get submissions
    submissions = await query.prefetch_related("assignment", "grades").all()
    
    # Calculate analytics
    total_submissions = len(submissions)
    on_time_submissions = 0
    late_submissions = 0
    missing_submissions = 0
    scores = []
    
    for submission in submissions:
        if submission.status == SubmissionStatus.LATE:
            late_submissions += 1
        else:
            on_time_submissions += 1
        
        # Get latest grade
        if submission.grades:
            grade = max(submission.grades, key=lambda g: g.created_at)
            if grade.score is not None:
                scores.append(grade.score)
    
    # Get assignments the user should have submitted but didn't
    if course_id:
        # Get all assignments for the course
        all_assignments = await Assignment.filter(
            course_id=course_id,
            published=True,
        ).all()
        
        # Get IDs of submitted assignments
        submitted_assignment_ids = [s.assignment_id for s in submissions]
        
        # Count missing assignments
        for assignment in all_assignments:
            if assignment.id not in submitted_assignment_ids:
                if assignment.due_date and assignment.due_date < datetime.utcnow():
                    missing_submissions += 1
    
    # Calculate average score
    average_score = sum(scores) / len(scores) if scores else None
    
    # Calculate completion percentage
    assignments_total = total_submissions + missing_submissions
    assignments_completed = total_submissions
    completion_percentage = (assignments_completed / assignments_total * 100) if assignments_total > 0 else 0
    
    return {
        "total_submissions": total_submissions,
        "on_time_submissions": on_time_submissions,
        "late_submissions": late_submissions,
        "missing_submissions": missing_submissions,
        "average_score": average_score,
        "assignments_completed": assignments_completed,
        "assignments_total": assignments_total,
        "completion_percentage": completion_percentage,
    }