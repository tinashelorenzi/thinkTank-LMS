from fastapi import FastAPI, Depends
from fastapi_admin.app import app as admin_app
from fastapi_admin.providers.login import UsernamePasswordProvider
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.staticfiles import StaticFiles

from core.config import settings
from .resources import resources, navigation
from .auth import AdminAuth


async def setup_admin(app: FastAPI):
    """
    Set up FastAPI Admin
    
    Args:
        app: FastAPI application
    """
    # Mount static files
    app.mount(
        "/admin/static",
        StaticFiles(directory="static"),
        name="static",
    )
    
    # Set up admin
    await admin_app.configure(
        logo_url="/admin/static/logo.png",
        template_folders=["templates"],
        favicon_url="/admin/static/favicon.ico",
        title="LMS Admin",
        login_provider=UsernamePasswordProvider(
            login_logo_url="/admin/static/logo.png",
            admin_model=None,
        ),
        # Exclude specific routes from admin
        exclude_routes=[
            "/admin/login",
            "/admin/logout",
        ],
        resources=resources,
        navigation=navigation,
    )
    
    # Add authentication middleware
    admin_app.add_middleware(
        AuthenticationMiddleware, 
        backend=AdminAuth()
    )