from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi_admin.depends import get_resources
from fastapi_admin.template import templates

from models import User, Course, Assignment, Submission, Grade
from models.user import UserRole
from utils.csv_export import export_grades_to_csv

# Create custom views router
router = APIRouter()


@router.get("/admin/settings")
async def site_settings(
    request: Request,
    resources=Depends(get_resources),
):
    """Site settings page"""
    return templates.TemplateResponse(
        "settings.html",
        context={
            "request": request,
            "resources": resources,
            "resource_label": "Site Settings",
            "page_pre_title": "settings",
            "page_title": "Site Settings",
        },
    )


@router.get("/admin/logs")
async def system_logs(
    request: Request,
    resources=Depends(get_resources),
):
    """System logs page"""
    return templates.TemplateResponse(
        "logs.html",
        context={
            "request": request,
            "resources": resources,
            "resource_label": "System Logs",
            "page_pre_title": "logs",
            "page_title": "System Logs",
        },
    )


@router.get("/admin/export/grades/{course_id}")
async def export_grades(
    request: Request,
    course_id: int,
):
    """Export grades for a course"""
    try:
        # Validate course
        course = await Course.get_or_none(id=course_id)
        if not course:
            return JSONResponse(
                status_code=404,
                content={"message": f"Course with ID {course_id} not found"},
            )
            
        # Generate CSV
        return await export_grades_to_csv(
            course_id=course_id,
            include_zeros=True,
            include_unsubmitted=True,
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": f"Error exporting grades: {str(e)}"},
        )


@router.get("/admin/stats/users")
async def user_stats():
    """Get user statistics"""
    total_users = await User.all().count()
    active_users = await User.filter(is_active=True).count()
    instructor_count = await User.filter(role=UserRole.INSTRUCTOR).count()
    student_count = await User.filter(role=UserRole.STUDENT).count()
    
    # Get recently added users
    recent_users = await User.all().order_by("-created_at").limit(5)
    recent_user_data = [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
        for user in recent_users
    ]
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "instructor_count": instructor_count,
        "student_count": student_count,
        "recent_users": recent_user_data,
    }


@router.get("/admin/stats/courses")
async def course_stats():
    """Get course statistics"""
    total_courses = await Course.all().count()
    published_courses = await Course.filter(state="published").count()
    active_enrollments = await Course.filter(enrollments__state="active").count()
    
    # Get recently added courses
    recent_courses = await Course.all().order_by("-created_at").limit(5)
    recent_course_data = [
        {
            "id": course.id,
            "name": course.name,
            "code": course.code,
            "state": course.state,
            "created_at": course.created_at.isoformat() if course.created_at else None,
        }
        for course in recent_courses
    ]
    
    return {
        "total_courses": total_courses,
        "published_courses": published_courses,
        "active_enrollments": active_enrollments,
        "recent_courses": recent_course_data,
    }