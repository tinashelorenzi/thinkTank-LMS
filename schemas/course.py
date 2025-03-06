from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, date

from models.course import CourseVisibility, CourseState, GradingScheme


class CourseBase(BaseModel):
    """Base course schema with common attributes"""
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    visibility: CourseVisibility = CourseVisibility.COURSE
    state: CourseState = CourseState.UNPUBLISHED
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    grading_scheme: GradingScheme = GradingScheme.PERCENTAGE
    allow_self_enrollment: bool = False
    syllabus: Optional[str] = None
    image: Optional[str] = None


class CourseCreate(CourseBase):
    """Course creation schema"""
    pass


class CourseUpdate(BaseModel):
    """Course update schema with optional fields"""
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[CourseVisibility] = None
    state: Optional[CourseState] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    grading_scheme: Optional[GradingScheme] = None
    allow_self_enrollment: Optional[bool] = None
    syllabus: Optional[str] = None
    image: Optional[str] = None


class CourseInDB(CourseBase):
    """Course schema with database fields (for internal use)"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class CourseResponse(CourseInDB):
    """Course response schema"""
    instructor_count: Optional[int] = 0
    student_count: Optional[int] = 0
    section_count: Optional[int] = 0
    assignment_count: Optional[int] = 0
    
    class Config:
        orm_mode = True


class CourseListResponse(BaseModel):
    """Response schema for list of courses"""
    total: int
    courses: List[CourseResponse]

    class Config:
        orm_mode = True


class SectionBase(BaseModel):
    """Base section schema with common attributes"""
    name: str
    max_seats: Optional[int] = 50
    meeting_times: Optional[str] = None
    location: Optional[str] = None
    course_id: int


class SectionCreate(SectionBase):
    """Section creation schema"""
    pass


class SectionUpdate(BaseModel):
    """Section update schema with optional fields"""
    name: Optional[str] = None
    max_seats: Optional[int] = None
    meeting_times: Optional[str] = None
    location: Optional[str] = None


class SectionInDB(SectionBase):
    """Section schema with database fields (for internal use)"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class SectionResponse(SectionInDB):
    """Section response schema"""
    student_count: Optional[int] = 0
    
    class Config:
        orm_mode = True


class SectionListResponse(BaseModel):
    """Response schema for list of sections"""
    total: int
    sections: List[SectionResponse]

    class Config:
        orm_mode = True