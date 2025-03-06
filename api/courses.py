from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path

from models.course import Course, Section, CourseVisibility, CourseState
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from schemas.course import (
    CourseCreate, CourseUpdate, CourseResponse, CourseListResponse,
    SectionCreate, SectionUpdate, SectionResponse, SectionListResponse
)
from core.security import (
    get_current_user, 
    get_current_active_user, 
    get_current_instructor_or_admin,
    get_current_admin_user
)
from utils.pagination import get_page_params, paginate_queryset, PageParams

# Create courses router
router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    course_in: CourseCreate,
    current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create new course (instructor or admin only)
    """
    # Create course
    course = await Course.create(
        name=course_in.name,
        code=course_in.code,
        description=course_in.description,
        visibility=course_in.visibility,
        state=course_in.state,
        start_date=course_in.start_date,
        end_date=course_in.end_date,
        grading_scheme=course_in.grading_scheme,
        allow_self_enrollment=course_in.allow_self_enrollment,
        syllabus=course_in.syllabus,
        image=course_in.image,
    )
    
    # Automatically enroll the creator as instructor
    await Enrollment.create(
        user=current_user,
        course=course,
        type=EnrollmentType.TEACHER,
        state=EnrollmentState.ACTIVE,
    )
    
    return course


@router.get("", response_model=CourseListResponse)
async def list_courses(
    page_params: PageParams = Depends(get_page_params),
    state: Optional[CourseState] = Query(None, description="Filter by course state"),
    search: Optional[str] = Query(None, description="Search by name or code"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List courses with various filters
    """
    # Create base query
    query = Course.all()
    
    # If not admin, only show visible courses
    if current_user.role != UserRole.ADMIN:
        # For non-admins, apply visibility filters
        if current_user.role == UserRole.INSTRUCTOR:
            # Instructors can see courses they teach or public courses
            query = query.filter(
                (Course.visibility == CourseVisibility.PUBLIC) |
                Course.enrollments.filter(user=current_user, type=EnrollmentType.TEACHER)
            )
        else:
            # Students and others can only see public courses or courses they're enrolled in
            query = query.filter(
                (Course.visibility == CourseVisibility.PUBLIC) |
                Course.enrollments.filter(user=current_user)
            )
    
    # Apply filters
    if state:
        query = query.filter(state=state)
    
    if search:
        query = query.filter(
            (Course.name.icontains(search)) | 
            (Course.code.icontains(search))
        )
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=CourseResponse,
    )


@router.get("/my-courses", response_model=CourseListResponse)
async def list_user_courses(
    page_params: PageParams = Depends(get_page_params),
    role: Optional[EnrollmentType] = Query(None, description="Filter by enrollment role"),
    state: Optional[CourseState] = Query(None, description="Filter by course state"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List courses the user is enrolled in
    """
    # Create base query for user's enrolled courses
    query = Course.filter(
        enrollments__user=current_user,
        enrollments__state=EnrollmentState.ACTIVE,
    )
    
    # Apply filters
    if role:
        query = query.filter(enrollments__type=role)
    
    if state:
        query = query.filter(state=state)
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=CourseResponse,
    )


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: int = Path(..., description="The ID of the course"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get course by ID
    """
    # Get course
    course = await Course.get_or_none(id=course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has access to the course
    if current_user.role != UserRole.ADMIN:
        # Non-admins need to check visibility permissions
        
        # If course is not public, check if user is enrolled
        if course.visibility != CourseVisibility.PUBLIC:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=course,
                state=EnrollmentState.ACTIVE,
            )
            
            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this course",
                )
    
    return course


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_in: CourseUpdate,
    course_id: int = Path(..., description="The ID of the course"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update course
    """
    # Get course
    course = await Course.get_or_none(id=course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has permission to update the course
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this course",
            )
    
    # Update fields
    for field, value in course_in.dict(exclude_unset=True).items():
        setattr(course, field, value)
    
    # Save course
    await course.save()
    
    return course


@router.delete("/{course_id}", response_model=Dict[str, Any])
async def delete_course(
    course_id: int = Path(..., description="The ID of the course"),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete course (admin only)
    """
    # Get course
    course = await Course.get_or_none(id=course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Delete course
    await course.delete()
    
    return {"message": "Course deleted successfully"}


# Section endpoints

@router.post("/{course_id}/sections", response_model=SectionResponse, status_code=status.HTTP_201_CREATED)
async def create_section(
    section_in: SectionCreate,
    course_id: int = Path(..., description="The ID of the course"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create new section for a course
    """
    # Get course
    course = await Course.get_or_none(id=course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has permission to create sections
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create sections for this course",
            )
    
    # Create section
    section = await Section.create(
        name=section_in.name,
        course=course,
        max_seats=section_in.max_seats,
        meeting_times=section_in.meeting_times,
        location=section_in.location,
    )
    
    return section


@router.get("/{course_id}/sections", response_model=SectionListResponse)
async def list_sections(
    course_id: int = Path(..., description="The ID of the course"),
    page_params: PageParams = Depends(get_page_params),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List sections for a course
    """
    # Get course
    course = await Course.get_or_none(id=course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has access to the course
    if current_user.role != UserRole.ADMIN:
        # Non-admins need to check visibility permissions
        
        # If course is not public, check if user is enrolled
        if course.visibility != CourseVisibility.PUBLIC:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=course,
                state=EnrollmentState.ACTIVE,
            )
            
            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this course",
                )
    
    # Get sections for the course
    query = Section.filter(course=course)
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=SectionResponse,
    )


@router.get("/{course_id}/sections/{section_id}", response_model=SectionResponse)
async def get_section(
    course_id: int = Path(..., description="The ID of the course"),
    section_id: int = Path(..., description="The ID of the section"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get section by ID
    """
    # Get course
    course = await Course.get_or_none(id=course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has access to the course
    if current_user.role != UserRole.ADMIN:
        # Non-admins need to check visibility permissions
        
        # If course is not public, check if user is enrolled
        if course.visibility != CourseVisibility.PUBLIC:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=course,
                state=EnrollmentState.ACTIVE,
            )
            
            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this course",
                )
    
    # Get section
    section = await Section.get_or_none(id=section_id, course=course)
    
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found",
        )
    
    return section


@router.put("/{course_id}/sections/{section_id}", response_model=SectionResponse)
async def update_section(
    section_in: SectionUpdate,
    course_id: int = Path(..., description="The ID of the course"),
    section_id: int = Path(..., description="The ID of the section"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update section
    """
    # Get course
    course = await Course.get_or_none(id=course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has permission to update sections
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update sections for this course",
            )
    
    # Get section
    section = await Section.get_or_none(id=section_id, course=course)
    
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found",
        )
    
    # Update fields
    for field, value in section_in.dict(exclude_unset=True).items():
        setattr(section, field, value)
    
    # Save section
    await section.save()
    
    return section


@router.delete("/{course_id}/sections/{section_id}", response_model=Dict[str, Any])
async def delete_section(
    course_id: int = Path(..., description="The ID of the course"),
    section_id: int = Path(..., description="The ID of the section"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete section
    """
    # Get course
    course = await Course.get_or_none(id=course_id)
    
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    # Check if user has permission to delete sections
    if current_user.role != UserRole.ADMIN:
        # Check if user is the instructor of the course
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        )
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete sections for this course",
            )
    
    # Get section
    section = await Section.get_or_none(id=section_id, course=course)
    
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found",
        )
    
    # Check if section has enrollments
    has_enrollments = await Enrollment.filter(section=section).exists()
    
    if has_enrollments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete section with active enrollments",
        )
    
    # Delete section
    await section.delete()
    
    return {"message": "Section deleted successfully"}