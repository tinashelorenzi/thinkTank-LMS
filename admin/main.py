from fastapi import FastAPI

from .routes import router as admin_router
from .custom_views import router as custom_views_router
from .setup import setup_admin


async def init_admin(app: FastAPI):
    """
    Initialize admin panel
    
    Args:
        app: FastAPI application
    """
    # Set up admin
    await setup_admin(app)
    
    # Include admin router
    app.include_router(admin_router)
    
    # Include custom views router
    app.include_router(custom_views_router)