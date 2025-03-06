from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

from models.assignment import AssignmentType, SubmissionType, GradingType


class RubricCriterionBase(BaseModel):
    """Base schema for rubric criterion"""
    description: str
    points: float
    position: int = 0


class RubricCriterionCreate(RubricCriterionBase):
    """Schema for creating a rubric criterion"""
    pass


class RubricCriterionResponse(RubricCriterionBase):
    """Response schema for a rubric criterion"""
    id: int
    
    class Config:
        orm_mode = True


class RubricRatingBase(BaseModel):
    """Base schema for rubric rating"""
    description: str
    points: float
    position: int = 0
    criterion_id: int


class RubricRatingCreate(RubricRatingBase):
    """Schema for creating a rubric rating"""
    pass


class RubricRatingResponse(RubricRatingBase):
    """Response schema for a rubric rating"""
    id: int
    
    class Config:
        orm_mode = True


class RubricBase(BaseModel):
    """Base schema for rubric"""
    title: str
    course_id: Optional[int] = None


class RubricCreate(RubricBase):
    """Schema for creating a rubric"""
    criteria: Optional[List[RubricCriterionCreate]] = None


class RubricResponse(RubricBase):
    """Response schema for a rubric"""
    id: int
    criteria: List[RubricCriterionResponse] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class AssignmentGroupBase(BaseModel):
    """Base schema for assignment group"""
    name: str
    weight: float = 0.0
    course_id: int
    drop_lowest: int = 0


class AssignmentGroupCreate(AssignmentGroupBase):
    """Schema for creating an assignment group"""
    pass


class AssignmentGroupUpdate(BaseModel):
    """Schema for updating an assignment group"""
    name: Optional[str] = None
    weight: Optional[float] = None
    drop_lowest: Optional[int] = None


class AssignmentGroupResponse(AssignmentGroupBase):
    """Response schema for an assignment group"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class AssignmentBase(BaseModel):
    """Base schema for assignment"""
    title: str
    description: Optional[str] = None
    assignment_type: AssignmentType = AssignmentType.ASSIGNMENT
    submission_types: List[SubmissionType] = [SubmissionType.ONLINE_TEXT]
    grading_type: GradingType = GradingType.POINTS
    points_possible: float = 100.0
    grading_scheme: Optional[Dict[str, Any]] = None
    due_date: Optional[datetime] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    published: bool = False
    allow_late_submissions: bool = True
    late_penalty_percent: float = 0.0
    max_attempts: int = 1
    is_group_assignment: bool = False
    course_id: int
    module_id: Optional[int] = None
    assignment_group_id: Optional[int] = None


class AssignmentCreate(AssignmentBase):
    """Schema for creating an assignment"""
    rubric_id: Optional[int] = None


class AssignmentUpdate(BaseModel):
    """Schema for updating an assignment"""
    title: Optional[str] = None
    description: Optional[str] = None
    assignment_type: Optional[AssignmentType] = None
    submission_types: Optional[List[SubmissionType]] = None
    grading_type: Optional[GradingType] = None
    points_possible: Optional[float] = None
    grading_scheme: Optional[Dict[str, Any]] = None
    due_date: Optional[datetime] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    published: Optional[bool] = None
    allow_late_submissions: Optional[bool] = None
    late_penalty_percent: Optional[float] = None
    max_attempts: Optional[int] = None
    is_group_assignment: Optional[bool] = None
    module_id: Optional[int] = None
    assignment_group_id: Optional[int] = None
    rubric_id: Optional[int] = None


class AssignmentInDB(AssignmentBase):
    """Assignment schema with database fields (for internal use)"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class AssignmentResponse(AssignmentInDB):
    """Response schema for an assignment"""
    course: Optional[Dict[str, Any]] = None
    module: Optional[Dict[str, Any]] = None
    assignment_group: Optional[AssignmentGroupResponse] = None
    rubric: Optional[RubricResponse] = None
    submission_count: Optional[int] = 0
    
    class Config:
        orm_mode = True


class AssignmentListResponse(BaseModel):
    """Response schema for list of assignments"""
    total: int
    assignments: List[AssignmentResponse]

    class Config:
        orm_mode = True


class AssignmentSubmissionStats(BaseModel):
    """Statistics for assignment submissions"""
    assignment_id: int
    total_submissions: int
    graded_submissions: int
    ungraded_submissions: int
    on_time_submissions: int
    late_submissions: int
    average_score: Optional[float] = None
    median_score: Optional[float] = None
    highest_score: Optional[float] = None
    lowest_score: Optional[float] = None