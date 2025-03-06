# API routes package
from fastapi import APIRouter

from .auth import router as auth_router
from .users import router as users_router
from .courses import router as courses_router
from .enrollments import router as enrollments_router
from .assignments import router as assignments_router
from .submissions import router as submissions_router
from .discussions import router as discussions_router
from .files import router as files_router
from .modules import router as modules_router
from .quizzes import router as quizzes_router
from .calendar import router as calendar_router
from .announcements import router as announcements_router
from .groups import router as groups_router

# Create API router
router = APIRouter(prefix="/api/v1")

# Include all routers
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(courses_router)
router.include_router(enrollments_router)
router.include_router(assignments_router)
router.include_router(submissions_router)
router.include_router(discussions_router)
router.include_router(files_router)
router.include_router(modules_router)
router.include_router(quizzes_router)
router.include_router(calendar_router)
router.include_router(announcements_router)
router.include_router(groups_router)