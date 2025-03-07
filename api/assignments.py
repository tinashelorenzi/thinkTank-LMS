from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.assignment import (
    Assignment, AssignmentGroup, Rubric, RubricCriterion, RubricRating,
    AssignmentType, SubmissionType, GradingType
)
from models.module import Module
from models.submission import Submission
from schemas.assignment import (
    AssignmentCreate, AssignmentUpdate, AssignmentResponse, AssignmentListResponse,
    AssignmentGroupCreate, AssignmentGroupUpdate, AssignmentGroupResponse,
    RubricCreate, RubricResponse, AssignmentSubmissionStats
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.email import send_email_background
from utils.pagination import get_page_params, paginate_queryset, PageParams
from core.config import settings

# Create assignments router
router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    assignment_in: AssignmentCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create new assignment (instructor or admin only)
    """
    # Get course
    course = await Course.get_or_none(id=assignment_in.course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has permission to create assignments for this course
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create assignments for this course",
            )
    
    # Check if module exists (if provided)
    module = None
    if assignment_in.module_id:
        module = await Module.get_or_none(id=assignment_in.module_id, course=course)
        
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found",
            )
    
    # Check if assignment group exists (if provided)
    assignment_group = None
    if assignment_in.assignment_group_id:
        assignment_group = await AssignmentGroup.get_or_none(
            id=assignment_in.assignment_group_id,
            course=course
        )
        
        if not assignment_group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment group not found",
            )
    
    # Get rubric if provided
    rubric = None
    if assignment_in.rubric_id:
        rubric = await Rubric.get_or_none(id=assignment_in.rubric_id)
        
        if not rubric:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rubric not found",
            )
    
    # Create assignment
    assignment = await Assignment.create(
        title=assignment_in.title,
        description=assignment_in.description,
        assignment_type=assignment_in.assignment_type,
        submission_types=assignment_in.submission_types,
        grading_type=assignment_in.grading_type,
        points_possible=assignment_in.points_possible,
        grading_scheme=assignment_in.grading_scheme,
        due_date=assignment_in.due_date,
        available_from=assignment_in.available_from,
        available_until=assignment_in.available_until,
        published=assignment_in.published,
        allow_late_submissions=assignment_in.allow_late_submissions,
        late_penalty_percent=assignment_in.late_penalty_percent,
        max_attempts=assignment_in.max_attempts,
        is_group_assignment=assignment_in.is_group_assignment,
        course=course,
        module=module,
        assignment_group=assignment_group,
    )
    
    # Send notification to enrolled students if assignment is published
    if assignment.published:
        # Get enrolled students
        students = await User.filter(
            enrollments__course=course,
            enrollments__type=EnrollmentType.STUDENT,
            enrollments__state=EnrollmentState.ACTIVE,
        )
        
        # Format due date
        due_date_str = assignment.due_date.strftime("%Y-%m-%d %H:%M") if assignment.due_date else "No due date"
        
        # Send notification emails
        for student in students:
            send_email_background(
                background_tasks=background_tasks,
                email_to=student.email,
                subject=f"New Assignment: {assignment.title}",
                template_name="new_assignment",
                template_data={
                    "username": student.username,
                    "course_name": course.name,
                    "assignment_title": assignment.title,
                    "due_date": due_date_str,
                    "assignment_url": f"{settings.SERVER_HOST}/courses/{course.id}/assignments/{assignment.id}",
                    "project_name": settings.PROJECT_NAME,
                },
            )
    
    return assignment


@router.get("", response_model=AssignmentListResponse)
async def list_assignments(
    page_params: PageParams = Depends(get_page_params),
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    module_id: Optional[int] = Query(None, description="Filter by module ID"),
    assignment_type: Optional[AssignmentType] = Query(None, description="Filter by assignment type"),
    published: Optional[bool] = Query(None, description="Filter by published status"),
    search: Optional[str] = Query(None, description="Search by title"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List assignments with various filters
    """
    # Create base query
    query = Assignment.all()
    
    # Apply course filter
    if course_id:
        query = query.filter(course_id=course_id)
        
        # If not admin or instructor, only show published assignments for enrolled courses
        if current_user.role not in [UserRole.ADMIN, UserRole.INSTRUCTOR]:
            # Check if user is enrolled in the course
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=course_id,
                state=EnrollmentState.ACTIVE,
            )
            
            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this course",
                )
            
            # Only show published assignments for students
            if enrollment.type == EnrollmentType.STUDENT:
                query = query.filter(published=True)
        
    # Apply other filters
    if module_id:
        query = query.filter(module_id=module_id)
    
    if assignment_type:
        query = query.filter(assignment_type=assignment_type)
    
    if published is not None:
        query = query.filter(published=published)
    
    if search:
        query = query.filter(title__icontains=search)
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=AssignmentResponse,
    )


@router.get("/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(
    assignment_id: int = Path(..., description="The ID of the assignment"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get assignment by ID
    """
    # Get assignment with related models
    assignment = await Assignment.get_or_none(id=assignment_id).prefetch_related(
        "course", "module", "assignment_group", "rubric"
    )
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
    
    # Check if user has access to the assignment
    if current_user.role != UserRole.ADMIN:
        # Check if user is enrolled in the course
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this assignment",
            )
        
        # Students can only see published assignments
        if enrollment.type == EnrollmentType.STUDENT and not assignment.published:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This assignment is not published",
            )
    
    return assignment


@router.put("/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_in: AssignmentUpdate,
    background_tasks: BackgroundTasks,
    assignment_id: int = Path(..., description="The ID of the assignment"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update assignment (instructor or admin only)
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=assignment_id).prefetch_related("course")
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
    
    # Check if user has permission to update this assignment
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this assignment",
            )
    
    # Check module if provided
    if assignment_in.module_id:
        module = await Module.get_or_none(
            id=assignment_in.module_id,
            course=assignment.course
        )
        
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Module not found",
            )
        
        assignment.module = module
    
    # Check assignment group if provided
    if assignment_in.assignment_group_id:
        assignment_group = await AssignmentGroup.get_or_none(
            id=assignment_in.assignment_group_id,
            course=assignment.course
        )
        
        if not assignment_group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment group not found",
            )
        
        assignment.assignment_group = assignment_group
    
    # Check rubric if provided
    if assignment_in.rubric_id:
        rubric = await Rubric.get_or_none(id=assignment_in.rubric_id)
        
        if not rubric:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rubric not found",
            )
        
        assignment.rubric = rubric
    
    # Check if assignment is being published
    was_published = assignment.published
    
    # Update fields
    for field, value in assignment_in.dict(exclude_unset=True, exclude={"module_id", "assignment_group_id", "rubric_id"}).items():
        setattr(assignment, field, value)
    
    # Save assignment
    await assignment.save()
    
    # Send notification if assignment is newly published
    if assignment.published and not was_published:
        # Get enrolled students
        students = await User.filter(
            enrollments__course=assignment.course,
            enrollments__type=EnrollmentType.STUDENT,
            enrollments__state=EnrollmentState.ACTIVE,
        )
        
        # Format due date
        due_date_str = assignment.due_date.strftime("%Y-%m-%d %H:%M") if assignment.due_date else "No due date"
        
        # Send notification emails
        for student in students:
            send_email_background(
                background_tasks=background_tasks,
                email_to=student.email,
                subject=f"New Assignment: {assignment.title}",
                template_name="new_assignment",
                template_data={
                    "username": student.username,
                    "course_name": assignment.course.name,
                    "assignment_title": assignment.title,
                    "due_date": due_date_str,
                    "assignment_url": f"{settings.SERVER_HOST}/courses/{assignment.course.id}/assignments/{assignment.id}",
                    "project_name": settings.PROJECT_NAME,
                },
            )
    
    return assignment


@router.delete("/{assignment_id}", response_model=Dict[str, Any])
async def delete_assignment(
    assignment_id: int = Path(..., description="The ID of the assignment"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete assignment (instructor or admin only)
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=assignment_id).prefetch_related("course")
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
    
    # Check if user has permission to delete this assignment
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this assignment",
            )
    
    # Check if assignment has submissions
    submission_count = await Submission.filter(assignment=assignment).count()
    
    if submission_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete assignment with submissions (found {submission_count})",
        )
    
    # Delete assignment
    await assignment.delete()
    
    return {"message": "Assignment deleted successfully"}


@router.get("/{assignment_id}/stats", response_model=AssignmentSubmissionStats)
async def get_assignment_stats(
    assignment_id: int = Path(..., description="The ID of the assignment"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Get submission statistics for an assignment (instructor or admin only)
    """
    # Get assignment
    assignment = await Assignment.get_or_none(id=assignment_id).prefetch_related("course")
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
    
    # Check if user has permission to view stats for this assignment
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=assignment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view stats for this assignment",
            )
    
    # Get submission statistics
    total_submissions = await Submission.filter(assignment=assignment).count()
    graded_submissions = await Submission.filter(assignment=assignment, grades__isnull=False).count()
    ungraded_submissions = total_submissions - graded_submissions
    
    on_time_submissions = await Submission.filter(assignment=assignment).filter(
        lambda x: x.submitted_at <= assignment.due_date if assignment.due_date else True
    ).count()
    
    late_submissions = total_submissions - on_time_submissions
    
    # Get score statistics
    scores = [
        grade.score
        for grade in await Submission.filter(assignment=assignment).prefetch_related("grades")
        if grade.score is not None
    ]
    
    average_score = sum(scores) / len(scores) if scores else None
    
    if scores:
        scores.sort()
        if len(scores) % 2 == 0:
            median_score = (scores[len(scores) // 2 - 1] + scores[len(scores) // 2]) / 2
        else:
            median_score = scores[len(scores) // 2]
    else:
        median_score = None
    
    highest_score = max(scores) if scores else None
    lowest_score = min(scores) if scores else None
    
    return {
        "assignment_id": assignment.id,
        "total_submissions": total_submissions,
        "graded_submissions": graded_submissions,
        "ungraded_submissions": ungraded_submissions,
        "on_time_submissions": on_time_submissions,
        "late_submissions": late_submissions,
        "average_score": average_score,
        "median_score": median_score,
        "highest_score": highest_score,
        "lowest_score": lowest_score,
    }


# Assignment group endpoints

@router.post("/groups", response_model=AssignmentGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment_group(
    group_in: AssignmentGroupCreate,
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create new assignment group (instructor or admin only)
    """
    # Get course
    course = await Course.get_or_none(id=group_in.course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has permission to create assignment groups for this course
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create assignment groups for this course",
            )
    
    # Create assignment group
    group = await AssignmentGroup.create(
        name=group_in.name,
        weight=group_in.weight,
        course=course,
        drop_lowest=group_in.drop_lowest,
    )
    
    return group


@router.get("/groups/{group_id}", response_model=AssignmentGroupResponse)
async def get_assignment_group(
    group_id: int = Path(..., description="The ID of the assignment group"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get assignment group by ID
    """
    # Get assignment group
    group = await AssignmentGroup.get_or_none(id=group_id).prefetch_related("course")
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment group not found",
        )
    
    # Check if user has access to the assignment group
    if current_user.role != UserRole.ADMIN:
        # Check if user is enrolled in the course
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=group.course,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this assignment group",
            )
    
    return group


@router.put("/groups/{group_id}", response_model=AssignmentGroupResponse)
async def update_assignment_group(
    group_in: AssignmentGroupUpdate,
    group_id: int = Path(..., description="The ID of the assignment group"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update assignment group (instructor or admin only)
    """
    # Get assignment group
    group = await AssignmentGroup.get_or_none(id=group_id).prefetch_related("course")
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment group not found",
        )
    
    # Check if user has permission to update this assignment group
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=group.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this assignment group",
            )
    
    # Update fields
    for field, value in group_in.dict(exclude_unset=True).items():
        setattr(group, field, value)
    
    # Save assignment group
    await group.save()
    
    return group


@router.delete("/groups/{group_id}", response_model=Dict[str, Any])
async def delete_assignment_group(
    group_id: int = Path(..., description="The ID of the assignment group"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete assignment group (instructor or admin only)
    """
    # Get assignment group
    group = await AssignmentGroup.get_or_none(id=group_id).prefetch_related("course")
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment group not found",
        )
    
    # Check if user has permission to delete this assignment group
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=group.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this assignment group",
            )
    
    # Check if group has assignments
    has_assignments = await Assignment.filter(assignment_group=group).exists()
    
    if has_assignments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete assignment group with assignments",
        )
    
    # Delete assignment group
    await group.delete()
    
    return {"message": "Assignment group deleted successfully"}


# Rubric endpoints

@router.post("/rubrics", response_model=RubricResponse, status_code=status.HTTP_201_CREATED)
async def create_rubric(
    rubric_in: RubricCreate,
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create new rubric (instructor or admin only)
    """
    # Check if course exists (if provided)
    if rubric_in.course_id:
        course = await Course.get_or_none(id=rubric_in.course_id)
        
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        
        # Check if user has permission to create rubrics for this course
        if current_user.role != UserRole.ADMIN:
            # Check if user is the instructor of the course
            instructor_enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=course,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            )
            
            if not instructor_enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to create rubrics for this course",
                )
    
    # Create rubric
    rubric = await Rubric.create(
        title=rubric_in.title,
        course_id=rubric_in.course_id,
    )
    
    # Create criteria if provided
    if rubric_in.criteria:
        for criterion_in in rubric_in.criteria:
            await RubricCriterion.create(
                rubric=rubric,
                description=criterion_in.description,
                points=criterion_in.points,
                position=criterion_in.position,
            )
    
    # Refresh to get related objects
    await rubric.refresh_from_db()
    
    return rubric