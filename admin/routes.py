from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_admin.app import app as admin_app
from fastapi_admin.exceptions import as_status_error
from fastapi_admin.template import templates
from fastapi_admin.depends import get_resources

from core.security import create_access_token
from models.user import User, UserRole
from utils.hashing import verify_password

# Create admin router
router = APIRouter(prefix="/admin")


@router.get("/")
async def admin_home():
    """Redirect to the admin dashboard"""
    return RedirectResponse(url="/admin/dashboard")


@router.get("/login")
async def login_page(request):
    """Admin login page"""
    return templates.TemplateResponse(
        "login.html",
        context={
            "request": request,
            "error": "",
        },
    )


@router.post("/login")
async def admin_login(request, form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Admin login endpoint
    """
    # Authenticate user
    user = await User.get_or_none(username=form_data.username)
    
    if not user or not verify_password(form_data.password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            context={
                "request": request,
                "error": "Invalid username or password",
            },
            status_code=400,
        )
    
    # Check admin access
    if user.role != UserRole.ADMIN:
        return templates.TemplateResponse(
            "login.html",
            context={
                "request": request,
                "error": "You do not have permission to access the admin panel",
            },
            status_code=403,
        )
    
    # Create access token
    token = create_access_token(subject=str(user.id))
    
    # Store token in cookies
    response = RedirectResponse(url="/admin/dashboard", status_code=302)
    response.set_cookie(
        key="admin_access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=3600 * 24,
        secure=False,  # Set to True in production with HTTPS
    )
    
    return response


@router.get("/logout")
async def admin_logout():
    """Admin logout endpoint"""
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("admin_access_token")
    return response


@router.get("/dashboard")
@as_status_error
async def dashboard(
    request,
    resources=Depends(get_resources),
):
    """Admin dashboard page"""
    # Get stats for dashboard
    user_count = await User.all().count()
    course_count = await User.all().filter(role=UserRole.INSTRUCTOR).count()
    student_count = await User.all().filter(role=UserRole.STUDENT).count()
    
    return templates.TemplateResponse(
        "dashboard.html",
        context={
            "request": request,
            "resources": resources,
            "resource_label": "Dashboard",
            "page_pre_title": "overview",
            "page_title": "Dashboard",
            "stats": {
                "user_count": user_count,
                "course_count": course_count,
                "student_count": student_count,
            },
        },
    )


# Include the admin app router
router.include_router(admin_app.router)