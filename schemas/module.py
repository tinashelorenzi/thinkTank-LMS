from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel
from datetime import datetime

from models.module import ModuleType, CompletionRequirement


class ModuleBase(BaseModel):
    """Base schema for module"""
    title: str
    description: Optional[str] = None
    course_id: int
    module_type: ModuleType = ModuleType.STANDARD
    position: int = 0
    is_published: bool = False
    is_hidden: bool = False
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    completion_requirement: Optional[CompletionRequirement] = CompletionRequirement.VIEW
    require_sequential_progress: bool = False
    external_url: Optional[str] = None
    external_tool_id: Optional[str] = None


class ModuleCreate(ModuleBase):
    """Schema for creating a module"""
    prerequisite_module_ids: Optional[List[int]] = None


class ModuleUpdate(BaseModel):
    """Schema for updating a module"""
    title: Optional[str] = None
    description: Optional[str] = None
    module_type: Optional[ModuleType] = None
    position: Optional[int] = None
    is_published: Optional[bool] = None
    is_hidden: Optional[bool] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    completion_requirement: Optional[CompletionRequirement] = None
    require_sequential_progress: Optional[bool] = None
    external_url: Optional[str] = None
    external_tool_id: Optional[str] = None
    prerequisite_module_ids: Optional[List[int]] = None


class ModuleResponse(ModuleBase):
    """Response schema for a module"""
    id: int
    created_at: datetime
    updated_at: datetime
    item_count: int = 0
    prerequisite_modules: List[Dict[str, Any]] = []
    
    class Config:
        orm_mode = True


class ModuleListResponse(BaseModel):
    """Response schema for list of modules"""
    total: int
    modules: List[ModuleResponse]

    class Config:
        orm_mode = True


class ModuleItemBase(BaseModel):
    """Base schema for module item"""
    title: str
    module_id: int
    position: int = 0
    content_type: str
    content_id: Optional[int] = None
    page_content: Optional[str] = None
    external_url: Optional[str] = None
    html_content: Optional[str] = None
    file_id: Optional[int] = None
    is_published: bool = True
    indent_level: int = 0
    completion_requirement: Optional[CompletionRequirement] = None
    min_score: Optional[float] = None


class ModuleItemCreate(ModuleItemBase):
    """Schema for creating a module item"""
    pass


class ModuleItemUpdate(BaseModel):
    """Schema for updating a module item"""
    title: Optional[str] = None
    position: Optional[int] = None
    content_type: Optional[str] = None
    content_id: Optional[int] = None
    page_content: Optional[str] = None
    external_url: Optional[str] = None
    html_content: Optional[str] = None
    file_id: Optional[int] = None
    is_published: Optional[bool] = None
    indent_level: Optional[int] = None
    completion_requirement: Optional[CompletionRequirement] = None
    min_score: Optional[float] = None


class ModuleItemResponse(ModuleItemBase):
    """Response schema for a module item"""
    id: int
    created_at: datetime
    updated_at: datetime
    content: Optional[Dict[str, Any]] = None  # Details about the linked content
    file: Optional[Dict[str, Any]] = None  # File details if this is a file item
    
    class Config:
        orm_mode = True


class ModuleItemListResponse(BaseModel):
    """Response schema for list of module items"""
    total: int
    items: List[ModuleItemResponse]

    class Config:
        orm_mode = True


class ModuleCompletionBase(BaseModel):
    """Base schema for module completion"""
    module_id: int
    user_id: int
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    progress_percent: float = 0.0


class ModuleCompletionCreate(ModuleCompletionBase):
    """Schema for creating a module completion"""
    pass


class ModuleCompletionUpdate(BaseModel):
    """Schema for updating a module completion"""
    is_completed: Optional[bool] = None
    completed_at: Optional[datetime] = None
    progress_percent: Optional[float] = None


class ModuleCompletionResponse(ModuleCompletionBase):
    """Response schema for a module completion"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class ModuleItemCompletionBase(BaseModel):
    """Base schema for module item completion"""
    item_id: int
    user_id: int
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    score: Optional[float] = None
    view_count: int = 0
    last_viewed_at: Optional[datetime] = None


class ModuleItemCompletionCreate(ModuleItemCompletionBase):
    """Schema for creating a module item completion"""
    pass


class ModuleItemCompletionUpdate(BaseModel):
    """Schema for updating a module item completion"""
    is_completed: Optional[bool] = None
    completed_at: Optional[datetime] = None
    score: Optional[float] = None
    view_count: Optional[int] = None
    last_viewed_at: Optional[datetime] = None


class ModuleItemCompletionResponse(ModuleItemCompletionBase):
    """Response schema for a module item completion"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True