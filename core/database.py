from typing import List
import logging
from fastapi import FastAPI
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise

from core.config import settings
from models import MODELS

logger = logging.getLogger(__name__)


# PostgreSQL Configuration (commented out)
"""
TORTOISE_ORM = {
    "connections": {
        "default": str(settings.DATABASE_URL),
    },
    "apps": {
        "models": {
            "models": ["aerich.models"] + [f"models.{model.__module__.split('.')[-1]}" for model in MODELS],
            "default_connection": "default",
        },
    },
    "use_tz": True,
    "timezone": settings.TIME_ZONE,
}
"""

# MySQL Configuration (alternative option)
"""
TORTOISE_ORM = {
    "connections": {
        "default": f"mysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    },
    "apps": {
        "models": {
            "models": ["aerich.models"] + [f"models.{model.__module__.split('.')[-1]}" for model in MODELS],
            "default_connection": "default",
        },
    },
    "use_tz": True,
    "timezone": settings.TIME_ZONE,
}
"""

# SQLite Configuration (active)
TORTOISE_ORM = {
    "connections": {
        "default": "sqlite://db.sqlite3"
    },
    "apps": {
        "models": {
            "models": ["aerich.models"] + [f"models.{model.__module__.split('.')[-1]}" for model in MODELS],
            "default_connection": "default",
        },
    },
    "use_tz": True,
    "timezone": settings.TIME_ZONE,
}


async def init_db(create_schema: bool = False) -> None:
    """
    Initialize database connection
    
    Args:
        create_schema: Whether to create database schema if it doesn't exist
    """
    logger.info("Initializing database connection")
    
    await Tortoise.init(
        db_url="sqlite://db.sqlite3",
        modules={"models": [model.__module__ for model in MODELS]},
    )
    
    if create_schema:
        logger.info("Creating database schema")
        await Tortoise.generate_schemas()
        
        # Create initial admin user if not exists
        from models.user import User, UserRole
        from core.security import get_password_hash
        
        admin_exists = await User.filter(username=settings.ADMIN_USERNAME).exists()
        if not admin_exists:
            logger.info(f"Creating admin user: {settings.ADMIN_USERNAME}")
            await User.create(
                email=settings.ADMIN_EMAIL,
                username=settings.ADMIN_USERNAME,
                password_hash=get_password_hash(settings.ADMIN_PASSWORD),
                first_name="Admin",
                last_name="User",
                role=UserRole.ADMIN,
                is_active=True,
                is_verified=True,
            )


async def close_db() -> None:
    """
    Close database connection
    """
    logger.info("Closing database connection")
    await Tortoise.close_connections()


def init_app(app: FastAPI) -> None:
    """
    Initialize FastAPI application with Tortoise ORM
    
    Args:
        app: FastAPI application instance
    """
    register_tortoise(
        app,
        db_url="sqlite://db.sqlite3",
        modules={"models": ["models"]},
        generate_schemas=settings.DEBUG,
        add_exception_handlers=True,
    )
    
    @app.on_event("startup")
    async def startup_db_client() -> None:
        await init_db(create_schema=settings.DEBUG)
    
    @app.on_event("shutdown")
    async def shutdown_db_client() -> None:
        await close_db()


def get_tortoise_config() -> dict:
    """
    Get Tortoise ORM config for migrations and CLI
    
    Returns:
        Tortoise ORM config dictionary
    """
    return TORTOISE_ORM