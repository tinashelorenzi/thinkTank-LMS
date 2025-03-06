from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from models.group import GroupType


class GroupBase(BaseModel):
    """Base schema for group"""
    name: str
    description: Optional[str] = None
    course_id: Optional[int] = None
    group_set_id: Optional[int] = None
    max_members: Optional[int] = None
    is_active: bool = True
    join_code: Optional[str] = None
    allow_self_signup: bool = False
    leader_id: Optional[int] = None


class GroupCreate(GroupBase):
    """Schema for creating a group"""
    member_ids: Optional[List[int]] = None  # Initial members to add


class GroupUpdate(BaseModel):
    """Schema for updating a group"""
    name: Optional[str] = None
    description: Optional[str] = None
    max_members: Optional[int] = None
    is_active: Optional[bool] = None
    join_code: Optional[str] = None
    allow_self_signup: Optional[bool] = None
    leader_id: Optional[int] = None
    member_ids: Optional[List[int]] = None


class GroupResponse(GroupBase):
    """Response schema for a group"""
    id: int
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    members: List[Dict[str, Any]] = []
    course: Optional[Dict[str, Any]] = None
    group_set: Optional[Dict[str, Any]] = None
    leader: Optional[Dict[str, Any]] = None
    
    class Config:
        orm_mode = True


class GroupListResponse(BaseModel):
    """Response schema for list of groups"""
    total: int
    groups: List[GroupResponse]

    class Config:
        orm_mode = True


class GroupSetBase(BaseModel):
    """Base schema for group set"""
    name: str
    description: Optional[str] = None
    course_id: int
    group_type: GroupType = GroupType.MANUAL
    allow_self_signup: bool = False
    self_signup_deadline: Optional[datetime] = None
    create_group_count: Optional[int] = None
    members_per_group: Optional[int] = None
    is_active: bool = True


class GroupSetCreate(GroupSetBase):
    """Schema for creating a group set"""
    pass


class GroupSetUpdate(BaseModel):
    """Schema for updating a group set"""
    name: Optional[str] = None
    description: Optional[str] = None
    group_type: Optional[GroupType] = None
    allow_self_signup: Optional[bool] = None
    self_signup_deadline: Optional[datetime] = None
    create_group_count: Optional[int] = None
    members_per_group: Optional[int] = None
    is_active: Optional[bool] = None


class GroupSetResponse(GroupSetBase):
    """Response schema for a group set"""
    id: int
    created_at: datetime
    updated_at: datetime
    group_count: int = 0
    groups: Optional[List[GroupResponse]] = None
    
    class Config:
        orm_mode = True


class GroupSetListResponse(BaseModel):
    """Response schema for list of group sets"""
    total: int
    group_sets: List[GroupSetResponse]

    class Config:
        orm_mode = True


class GroupMembershipBase(BaseModel):
    """Base schema for group membership"""
    group_id: int
    user_id: int
    is_active: bool = True
    role: str = "member"


class GroupMembershipCreate(GroupMembershipBase):
    """Schema for creating a group membership"""
    pass


class GroupMembershipUpdate(BaseModel):
    """Schema for updating a group membership"""
    is_active: Optional[bool] = None
    role: Optional[str] = None
    left_at: Optional[datetime] = None


class GroupMembershipResponse(GroupMembershipBase):
    """Response schema for a group membership"""
    id: int
    joined_at: datetime
    left_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    user: Dict[str, Any]
    group: Dict[str, Any]
    
    class Config:
        orm_mode = True


class GroupMembershipListResponse(BaseModel):
    """Response schema for list of group memberships"""
    total: int
    memberships: List[GroupMembershipResponse]

    class Config:
        orm_mode = True


class GroupAssignmentBase(BaseModel):
    """Base schema for group assignment"""
    assignment_id: int
    group_set_id: int
    require_all_members: bool = False
    grade_individually: bool = False


class GroupAssignmentCreate(GroupAssignmentBase):
    """Schema for creating a group assignment"""
    pass


class GroupAssignmentUpdate(BaseModel):
    """Schema for updating a group assignment"""
    require_all_members: Optional[bool] = None
    grade_individually: Optional[bool] = None


class GroupAssignmentResponse(GroupAssignmentBase):
    """Response schema for a group assignment"""
    id: int
    created_at: datetime
    updated_at: datetime
    assignment: Dict[str, Any]
    group_set: Dict[str, Any]
    
    class Config:
        orm_mode = True


class GroupAssignmentListResponse(BaseModel):
    """Response schema for list of group assignments"""
    total: int
    group_assignments: List[GroupAssignmentResponse]

    class Config:
        orm_mode = True


class PeerReviewBase(BaseModel):
    """Base schema for peer review"""
    assignment_id: int
    reviewer_id: int
    reviewee_id: int
    submission_id: Optional[int] = None
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    comments: Optional[str] = None
    rating: Optional[float] = None
    rubric_assessment: Optional[Dict[str, Any]] = None


class PeerReviewCreate(PeerReviewBase):
    """Schema for creating a peer review"""
    pass


class PeerReviewUpdate(BaseModel):
    """Schema for updating a peer review"""
    is_completed: Optional[bool] = None
    completed_at: Optional[datetime] = None
    comments: Optional[str] = None
    rating: Optional[float] = None
    rubric_assessment: Optional[Dict[str, Any]] = None


class PeerReviewResponse(PeerReviewBase):
    """Response schema for a peer review"""
    id: int
    created_at: datetime
    updated_at: datetime
    assignment: Dict[str, Any]
    reviewer: Dict[str, Any]
    reviewee: Dict[str, Any]
    submission: Optional[Dict[str, Any]] = None
    
    class Config:
        orm_mode = True


class PeerReviewListResponse(BaseModel):
    """Response schema for list of peer reviews"""
    total: int
    peer_reviews: List[PeerReviewResponse]

    class Config:
        orm_mode = True


class GroupInvitationBase(BaseModel):
    """Base schema for group invitation"""
    group_id: int
    user_id: int
    inviter_id: int
    status: str = "pending"
    message: Optional[str] = None
    expires_at: Optional[datetime] = None


class GroupInvitationCreate(GroupInvitationBase):
    """Schema for creating a group invitation"""
    pass


class GroupInvitationUpdate(BaseModel):
    """Schema for updating a group invitation"""
    status: Optional[str] = None
    responded_at: Optional[datetime] = None


class GroupInvitationResponse(GroupInvitationBase):
    """Response schema for a group invitation"""
    id: int
    responded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    group: Dict[str, Any]
    user: Dict[str, Any]
    inviter: Dict[str, Any]
    
    class Config:
        orm_mode = True


class GroupInvitationListResponse(BaseModel):
    """Response schema for list of group invitations"""
    total: int
    invitations: List[GroupInvitationResponse]

    class Config:
        orm_mode = True


class RandomizeGroupsRequest(BaseModel):
    """Request schema for randomizing groups in a group set"""
    group_set_id: int
    count: int  # Number of groups to create
    members_per_group: Optional[int] = None  # If specified, will override group set setting
    include_existing_members: bool = True  # Whether to include users already in groups