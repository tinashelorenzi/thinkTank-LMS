from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from models.enrollment import EnrollmentType, EnrollmentState


class EnrollmentBase(BaseModel):
    """Base enrollment schema with common attributes"""
    user_id: int
    course_id: int
    section_id: Optional[int] = None
    type: EnrollmentType = EnrollmentType.STUDENT
    state: EnrollmentState = EnrollmentState.ACTIVE


class EnrollmentCreate(EnrollmentBase):
    """Enrollment creation schema"""
    pass


class EnrollmentUpdate(BaseModel):
    """Enrollment update schema with optional fields"""
    section_id: Optional[int] = None
    type: Optional[EnrollmentType] = None
    state: Optional[EnrollmentState] = None
    current_grade: Optional[float] = None
    final_grade: Optional[float] = None
    grade_override: Optional[bool] = None


class EnrollmentInDB(EnrollmentBase):
    """Enrollment schema with database fields (for internal use)"""
    id: int
    current_grade: Optional[float] = None
    final_grade: Optional[float] = None
    grade_override: bool = False
    created_at: datetime
    updated_at: datetime
    last_activity_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class EnrollmentResponse(EnrollmentInDB):
    """Enrollment response schema with related data"""
    user: Dict[str, Any] = None  # Simplified user data
    course: Dict[str, Any] = None  # Simplified course data
    section: Optional[Dict[str, Any]] = None  # Simplified section data
    
    class Config:
        orm_mode = True


class EnrollmentListResponse(BaseModel):
    """Response schema for list of enrollments"""
    total: int
    enrollments: List[EnrollmentResponse]

    class Config:
        orm_mode = True


class EnrollmentBulkCreate(BaseModel):
    """Schema for creating multiple enrollments at once"""
    course_id: int
    section_id: Optional[int] = None
    type: EnrollmentType = EnrollmentType.STUDENT
    user_ids: List[int]


class UserEnrollmentResponse(BaseModel):
    """Response schema for a user's enrollments"""
    total: int
    enrollments: List[EnrollmentResponse]

    class Config:
        orm_mode = True