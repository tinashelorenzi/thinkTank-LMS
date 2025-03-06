from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

from models.submission import SubmissionStatus


class SubmissionBase(BaseModel):
    """Base schema for submission"""
    assignment_id: int
    user_id: int
    group_id: Optional[int] = None
    submission_type: str
    body: Optional[str] = None
    url: Optional[str] = None
    status: SubmissionStatus = SubmissionStatus.SUBMITTED
    attempt_number: int = 1


class SubmissionCreate(SubmissionBase):
    """Schema for creating a submission"""
    pass


class SubmissionUpdate(BaseModel):
    """Schema for updating a submission"""
    body: Optional[str] = None
    url: Optional[str] = None
    status: Optional[SubmissionStatus] = None


class GradeBase(BaseModel):
    """Base schema for grade"""
    submission_id: int
    grader_id: Optional[int] = None
    score: Optional[float] = None
    feedback: Optional[str] = None
    is_auto_graded: bool = False
    rubric_assessment: Optional[Dict[str, Any]] = None


class GradeCreate(GradeBase):
    """Schema for creating a grade"""
    pass


class GradeUpdate(BaseModel):
    """Schema for updating a grade"""
    score: Optional[float] = None
    feedback: Optional[str] = None
    rubric_assessment: Optional[Dict[str, Any]] = None


class GradeResponse(GradeBase):
    """Response schema for a grade"""
    id: int
    graded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class CommentBase(BaseModel):
    """Base schema for comment"""
    submission_id: int
    author_id: int
    text: str
    parent_id: Optional[int] = None


class CommentCreate(CommentBase):
    """Schema for creating a comment"""
    pass


class CommentResponse(CommentBase):
    """Response schema for a comment"""
    id: int
    author: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    replies: Optional[List['CommentResponse']] = []
    
    class Config:
        orm_mode = True


# Resolve forward reference for nested comments
CommentResponse.update_forward_refs()


class SubmissionAttachmentBase(BaseModel):
    """Base schema for submission attachment"""
    submission_id: int
    filename: str
    file_path: str
    file_type: str
    file_size: int


class SubmissionAttachmentCreate(SubmissionAttachmentBase):
    """Schema for creating a submission attachment"""
    pass


class SubmissionAttachmentResponse(SubmissionAttachmentBase):
    """Response schema for a submission attachment"""
    id: int
    created_at: datetime
    
    class Config:
        orm_mode = True


class SubmissionInDB(SubmissionBase):
    """Submission schema with database fields (for internal use)"""
    id: int
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class SubmissionResponse(SubmissionInDB):
    """Response schema for a submission"""
    assignment: Dict[str, Any]
    user: Dict[str, Any]
    group: Optional[Dict[str, Any]] = None
    grades: List[GradeResponse] = []
    current_grade: Optional[GradeResponse] = None
    comments: List[CommentResponse] = []
    files: List[SubmissionAttachmentResponse] = []
    is_late: bool
    
    class Config:
        orm_mode = True


class SubmissionListResponse(BaseModel):
    """Response schema for list of submissions"""
    total: int
    submissions: List[SubmissionResponse]

    class Config:
        orm_mode = True


class BulkGradeUpdate(BaseModel):
    """Schema for updating multiple grades at once"""
    submission_ids: List[int]
    score: Optional[float] = None
    feedback: Optional[str] = None
    rubric_assessment: Optional[Dict[str, Any]] = None
    grader_id: Optional[int] = None


class SubmissionAnalytics(BaseModel):
    """Analytics for a user's submissions"""
    total_submissions: int
    on_time_submissions: int
    late_submissions: int
    missing_submissions: int
    average_score: Optional[float] = None
    assignments_completed: int
    assignments_total: int
    completion_percentage: float