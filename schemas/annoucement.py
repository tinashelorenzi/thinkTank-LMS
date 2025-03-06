from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from models.announcement import AnnouncementRecipientType, AnnouncementPriority


class AnnouncementBase(BaseModel):
    """Base schema for announcement"""
    title: str
    message: str
    course_id: int
    author_id: int
    section_id: Optional[int] = None
    group_id: Optional[int] = None
    recipient_type: AnnouncementRecipientType = AnnouncementRecipientType.COURSE
    priority: AnnouncementPriority = AnnouncementPriority.NORMAL
    is_published: bool = True
    is_pinned: bool = False
    publish_at: Optional[datetime] = None
    send_notification: bool = True
    allow_comments: bool = True
    allow_liking: bool = True


class AnnouncementCreate(AnnouncementBase):
    """Schema for creating an announcement"""
    attachment_ids: Optional[List[int]] = None
    recipient_ids: Optional[List[int]] = None  # For individual recipients


class AnnouncementUpdate(BaseModel):
    """Schema for updating an announcement"""
    title: Optional[str] = None
    message: Optional[str] = None
    section_id: Optional[int] = None
    group_id: Optional[int] = None
    recipient_type: Optional[AnnouncementRecipientType] = None
    priority: Optional[AnnouncementPriority] = None
    is_published: Optional[bool] = None
    is_pinned: Optional[bool] = None
    publish_at: Optional[datetime] = None
    send_notification: Optional[bool] = None
    allow_comments: Optional[bool] = None
    allow_liking: Optional[bool] = None
    attachment_ids: Optional[List[int]] = None
    recipient_ids: Optional[List[int]] = None


class AnnouncementResponse(AnnouncementBase):
    """Response schema for an announcement"""
    id: int
    view_count: int = 0
    created_at: datetime
    updated_at: datetime
    author: Dict[str, Any]
    course: Dict[str, Any]
    section: Optional[Dict[str, Any]] = None
    group: Optional[Dict[str, Any]] = None
    attachments: List[Dict[str, Any]] = []
    comment_count: int = 0
    like_count: int = 0
    is_read: Optional[bool] = None  # Indicates if current user has read it
    
    class Config:
        orm_mode = True


class AnnouncementListResponse(BaseModel):
    """Response schema for list of announcements"""
    total: int
    announcements: List[AnnouncementResponse]

    class Config:
        orm_mode = True


class AnnouncementCommentBase(BaseModel):
    """Base schema for announcement comment"""
    announcement_id: int
    author_id: int
    text: str
    parent_id: Optional[int] = None


class AnnouncementCommentCreate(AnnouncementCommentBase):
    """Schema for creating an announcement comment"""
    pass


class AnnouncementCommentUpdate(BaseModel):
    """Schema for updating an announcement comment"""
    text: Optional[str] = None
    is_hidden: Optional[bool] = None
    hidden_reason: Optional[str] = None


class AnnouncementCommentResponse(AnnouncementCommentBase):
    """Response schema for an announcement comment"""
    id: int
    is_hidden: bool = False
    hidden_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    author: Dict[str, Any]
    replies: Optional[List['AnnouncementCommentResponse']] = []
    
    class Config:
        orm_mode = True


# Resolve forward reference for nested comments
AnnouncementCommentResponse.update_forward_refs()


class AnnouncementCommentListResponse(BaseModel):
    """Response schema for list of announcement comments"""
    total: int
    comments: List[AnnouncementCommentResponse]

    class Config:
        orm_mode = True


class AnnouncementLikeCreate(BaseModel):
    """Schema for liking an announcement"""
    announcement_id: int
    user_id: int


class AnnouncementReadCreate(BaseModel):
    """Schema for marking an announcement as read"""
    announcement_id: int
    user_id: int


class AnnouncementAttachmentCreate(BaseModel):
    """Schema for attaching a file to an announcement"""
    announcement_id: int
    file_id: int
    display_name: Optional[str] = None
    position: int = 0


class AnnouncementRecipientCreate(BaseModel):
    """Schema for adding a recipient to an announcement"""
    announcement_id: int
    user_id: int