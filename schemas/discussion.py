from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from models.discussion import DiscussionVisibility, DiscussionType


class DiscussionForumBase(BaseModel):
    """Base schema for discussion forum"""
    title: str
    description: Optional[str] = None
    course_id: int
    module_id: Optional[int] = None
    is_pinned: bool = False
    position: int = 0
    allow_anonymous_posts: bool = False
    require_initial_post: bool = False
    assignment_id: Optional[int] = None


class DiscussionForumCreate(DiscussionForumBase):
    """Schema for creating a discussion forum"""
    pass


class DiscussionForumUpdate(BaseModel):
    """Schema for updating a discussion forum"""
    title: Optional[str] = None
    description: Optional[str] = None
    module_id: Optional[int] = None
    is_pinned: Optional[bool] = None
    position: Optional[int] = None
    allow_anonymous_posts: Optional[bool] = None
    require_initial_post: Optional[bool] = None
    assignment_id: Optional[int] = None


class DiscussionForumResponse(DiscussionForumBase):
    """Response schema for a discussion forum"""
    id: int
    topic_count: int = 0
    reply_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class DiscussionTopicBase(BaseModel):
    """Base schema for discussion topic"""
    title: str
    message: str
    forum_id: int
    author_id: int
    type: DiscussionType = DiscussionType.THREADED
    visibility: DiscussionVisibility = DiscussionVisibility.EVERYONE
    is_announcement: bool = False
    is_pinned: bool = False
    allow_liking: bool = True
    is_closed: bool = False
    section_id: Optional[int] = None
    visible_to_user_ids: Optional[List[int]] = None
    visible_to_group_ids: Optional[List[int]] = None


class DiscussionTopicCreate(DiscussionTopicBase):
    """Schema for creating a discussion topic"""
    pass


class DiscussionTopicUpdate(BaseModel):
    """Schema for updating a discussion topic"""
    title: Optional[str] = None
    message: Optional[str] = None
    type: Optional[DiscussionType] = None
    visibility: Optional[DiscussionVisibility] = None
    is_announcement: Optional[bool] = None
    is_pinned: Optional[bool] = None
    allow_liking: Optional[bool] = None
    is_closed: Optional[bool] = None
    section_id: Optional[int] = None
    visible_to_user_ids: Optional[List[int]] = None
    visible_to_group_ids: Optional[List[int]] = None


class DiscussionTopicResponse(DiscussionTopicBase):
    """Response schema for a discussion topic"""
    id: int
    view_count: int = 0
    created_at: datetime
    updated_at: datetime
    forum: Dict[str, Any]
    author: Dict[str, Any]
    reply_count: int = 0
    
    class Config:
        orm_mode = True


class DiscussionTopicListResponse(BaseModel):
    """Response schema for list of discussion topics"""
    total: int
    topics: List[DiscussionTopicResponse]

    class Config:
        orm_mode = True


class DiscussionReplyBase(BaseModel):
    """Base schema for discussion reply"""
    message: str
    topic_id: int
    author_id: int
    parent_reply_id: Optional[int] = None


class DiscussionReplyCreate(DiscussionReplyBase):
    """Schema for creating a discussion reply"""
    pass


class DiscussionReplyUpdate(BaseModel):
    """Schema for updating a discussion reply"""
    message: Optional[str] = None


class DiscussionReplyResponse(DiscussionReplyBase):
    """Response schema for a discussion reply"""
    id: int
    is_edited: bool = False
    edited_at: Optional[datetime] = None
    is_endorsed: bool = False
    endorsed_by: Optional[Dict[str, Any]] = None
    endorsed_at: Optional[datetime] = None
    like_count: int = 0
    created_at: datetime
    updated_at: datetime
    author: Dict[str, Any]
    child_replies: Optional[List['DiscussionReplyResponse']] = []
    
    class Config:
        orm_mode = True


# Resolve forward reference for nested replies
DiscussionReplyResponse.update_forward_refs()


class DiscussionReplyListResponse(BaseModel):
    """Response schema for list of discussion replies"""
    total: int
    replies: List[DiscussionReplyResponse]

    class Config:
        orm_mode = True


class DiscussionReplyLikeCreate(BaseModel):
    """Schema for liking a discussion reply"""
    reply_id: int
    user_id: int


class DiscussionTopicSubscriptionCreate(BaseModel):
    """Schema for subscribing to a discussion topic"""
    topic_id: int
    user_id: int
    send_email: bool = True


class DiscussionSubscriptionUpdate(BaseModel):
    """Schema for updating a discussion subscription"""
    send_email: Optional[bool] = None