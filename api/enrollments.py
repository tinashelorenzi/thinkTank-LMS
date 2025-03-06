from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course, Section
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from schemas.enrollment import (
    EnrollmentCreate, EnrollmentUpdate, EnrollmentResponse, EnrollmentListResponse,
    EnrollmentBulkCreate, UserEnrollmentResponse
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin,
    get_current_admin_user
)
from utils.email import send_email_background
from utils.pagination import get_page_params, paginate_queryset, PageParams
from core.config import settings

# Create enrollments router
router = APIRouter(prefix="/enrollments", tags=["enrollments"])


@router.post("", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def create_enrollment(
    enrollment_in: EnrollmentCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create new enrollment (instructor or admin only)
    """
    # Get course
    course = await Course.get_or_none(id=enrollment_in.course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Get user
    user = await User.get_or_none(id=enrollment_in.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Check if section exists (if provided)
    section = None
    if enrollment_in.section_id:
        section = await Section.get_or_none(
            id=enrollment_in.section_id, 
            course=course
        )
        
        if not section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Section not found",
            )
    
    # Check if user is already enrolled
    existing_enrollment = await Enrollment.get_or_none(
        user=user,
        course=course,
    )
    
    if existing_enrollment:
        # Update existing enrollment
        existing_enrollment.section = section
        existing_enrollment.type = enrollment_in.type
        existing_enrollment.state = enrollment_in.state
        await existing_enrollment.save()
        
        enrollment = existing_enrollment
    else:
        # Create new enrollment
        enrollment = await Enrollment.create(
            user=user,
            course=course,
            section=section,
            type=enrollment_in.type,
            state=enrollment_in.state,
        )
    
    # Send enrollment notification email
    if enrollment.state == EnrollmentState.ACTIVE:
        send_email_background(
            background_tasks=background_tasks,
            email_to=user.email,
            subject=f"You have been enrolled in {course.name}",
            template_name="enrollment_notification",
            template_data={
                "username": user.username,
                "course_name": course.name,
                "course_code": course.code,
                "role": enrollment.type,
                "start_date": course.start_date.isoformat() if course.start_date else "Not specified",
                "course_url": f"{settings.SERVER_HOST}/courses/{course.id}",
            },
        )
    
    return enrollment


@router.post("/bulk", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def bulk_create_enrollments(
    enrollment_in: EnrollmentBulkCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create multiple enrollments at once (instructor or admin only)
    """
    # Get course
    course = await Course.get_or_none(id=enrollment_in.course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if section exists (if provided)
    section = None
    if enrollment_in.section_id:
        section = await Section.get_or_none(
            id=enrollment_in.section_id, 
            course=course
        )
        
        if not section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Section not found",
            )
    
    # Check if current user has permission for this course
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
                detail="You don't have permission to manage enrollments for this course",
            )
    
    # Process enrollments
    created_count = 0
    updated_count = 0
    failed_ids = []
    
    for user_id in enrollment_in.user_ids:
        try:
            # Get user
            user = await User.get_or_none(id=user_id)
            
            if not user:
                failed_ids.append(user_id)
                continue
            
            # Check if user is already enrolled
            existing_enrollment = await Enrollment.get_or_none(
                user=user,
                course=course,
            )
            
            if existing_enrollment:
                # Update existing enrollment
                existing_enrollment.section = section
                existing_enrollment.type = enrollment_in.type
                existing_enrollment.state = EnrollmentState.ACTIVE
                await existing_enrollment.save()
                updated_count += 1
            else:
                # Create new enrollment
                await Enrollment.create(
                    user=user,
                    course=course,
                    section=section,
                    type=enrollment_in.type,
                    state=EnrollmentState.ACTIVE,
                )
                created_count += 1
            
            # Send enrollment notification email
            send_email_background(
                background_tasks=background_tasks,
                email_to=user.email,
                subject=f"You have been enrolled in {course.name}",
                template_name="enrollment_notification",
                template_data={
                    "username": user.username,
                    "course_name": course.name,
                    "course_code": course.code,
                    "role": enrollment_in.type,
                    "start_date": course.start_date.isoformat() if course.start_date else "Not specified",
                    "course_url": f"{settings.SERVER_HOST}/courses/{course.id}",
                },
            )
        
        except Exception as e:
            failed_ids.append(user_id)
    
    return {
        "message": "Bulk enrollment processed",
        "created_count": created_count,
        "updated_count": updated_count,
        "failed_count": len(failed_ids),
        "failed_ids": failed_ids,
    }


@router.post("/join", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def join_course(
    course_code: str,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Join a course using its code
    """
    # Find course by code
    course = await Course.get_or_none(code=course_code)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if course allows self-enrollment
    if not course.allow_self_enrollment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This course does not allow self-enrollment",
        )
    
    # Check if user is already enrolled
    existing_enrollment = await Enrollment.get_or_none(
        user=current_user,
        course=course,
    )
    
    if existing_enrollment:
        # Reactivate enrollment if needed
        if existing_enrollment.state != EnrollmentState.ACTIVE:
            existing_enrollment.state = EnrollmentState.ACTIVE
            await existing_enrollment.save()
        
        return existing_enrollment
    
    # Create new enrollment
    enrollment = await Enrollment.create(
        user=current_user,
        course=course,
        type=EnrollmentType.STUDENT,
        state=EnrollmentState.ACTIVE,
    )
    
    return enrollment


@router.get("", response_model=EnrollmentListResponse)
async def list_enrollments(
    page_params: PageParams = Depends(get_page_params),
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    type: Optional[EnrollmentType] = Query(None, description="Filter by enrollment type"),
    state: Optional[EnrollmentState] = Query(None, description="Filter by enrollment state"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    List enrollments with various filters (instructor or admin only)
    """
    # Create base query
    query = Enrollment.all()
    
    # Apply filters
    if course_id:
        query = query.filter(course_id=course_id)
        
        # Check if current user has permission for this course
        if current_user.role != UserRole.ADMIN:
            # Check if user is the instructor of the course
            instructor_enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=course_id,
                type=EnrollmentType.TEACHER,
                state=EnrollmentState.ACTIVE,
            )
            
            if not instructor_enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view enrollments for this course",
                )
    elif current_user.role != UserRole.ADMIN:
        # Non-admin users can only see enrollments for courses they teach
        query = query.filter(
            course__enrollments__user=current_user,
            course__enrollments__type=EnrollmentType.TEACHER,
            course__enrollments__state=EnrollmentState.ACTIVE,
        )
    
    # Apply additional filters
    if user_id:
        query = query.filter(user_id=user_id)
    
    if type:
        query = query.filter(type=type)
    
    if state:
        query = query.filter(state=state)
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=EnrollmentResponse,
    )


@router.get("/my", response_model=UserEnrollmentResponse)
async def list_user_enrollments(
    page_params: PageParams = Depends(get_page_params),
    state: Optional[EnrollmentState] = Query(None, description="Filter by enrollment state"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List current user's enrollments
    """
    # Create base query
    query = Enrollment.filter(user=current_user)
    
    # Apply filters
    if state:
        query = query.filter(state=state)
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=EnrollmentResponse,
    )


@router.get("/{enrollment_id}", response_model=EnrollmentResponse)
async def get_enrollment(
    enrollment_id: int = Path(..., description="The ID of the enrollment"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get enrollment by ID
    """
    # Get enrollment
    enrollment = await Enrollment.get_or_none(id=enrollment_id)
    
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )
    
    # Check if user has permission to view this enrollment
    if current_user.role != UserRole.ADMIN:
        # Users can see their own enrollments
        if enrollment.user_id == current_user.id:
            return enrollment
        
        # Instructors can see enrollments for courses they teach
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=enrollment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this enrollment",
            )
    
    return enrollment


@router.put("/{enrollment_id}", response_model=EnrollmentResponse)
async def update_enrollment(
    enrollment_in: EnrollmentUpdate,
    enrollment_id: int = Path(..., description="The ID of the enrollment"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update enrollment (instructor or admin only)
    """
    # Get enrollment
    enrollment = await Enrollment.get_or_none(id=enrollment_id)
    
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )
    
    # Check if user has permission to update this enrollment
    if current_user.role != UserRole.ADMIN:
        # Instructors can update enrollments for courses they teach
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=enrollment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this enrollment",
            )
    
    # Check if section exists (if provided)
    if enrollment_in.section_id:
        section = await Section.get_or_none(
            id=enrollment_in.section_id, 
            course=enrollment.course
        )
        
        if not section:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Section not found",
            )
        
        enrollment.section = section
    
    # Update fields
    for field, value in enrollment_in.dict(exclude_unset=True, exclude={"section_id"}).items():
        setattr(enrollment, field, value)
    
    # Save enrollment
    await enrollment.save()
    
    return enrollment


@router.delete("/{enrollment_id}", response_model=Dict[str, Any])
async def delete_enrollment(
    enrollment_id: int = Path(..., description="The ID of the enrollment"),
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete enrollment (instructor or admin only)
    """
    # Get enrollment
    enrollment = await Enrollment.get_or_none(id=enrollment_id)
    
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )
    
    # Check if user has permission to delete this enrollment
    if current_user.role != UserRole.ADMIN:
        # Instructors can delete enrollments for courses they teach
        instructor_enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=enrollment.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not instructor_enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this enrollment",
            )
    
    # Instead of deleting, mark as inactive
    enrollment.state = EnrollmentState.INACTIVE
    await enrollment.save()
    
    return {"message": "Enrollment deleted successfully"}