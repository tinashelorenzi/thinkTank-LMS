from typing import Optional, List
from pydantic import BaseModel, EmailStr, validator
from datetime import datetime

from models.user import UserRole


class UserBase(BaseModel):
    """Base user schema with common attributes"""
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    role: UserRole = UserRole.STUDENT
    is_active: bool = True
    time_zone: Optional[str] = "UTC"
    locale: Optional[str] = "en"
    
    @property
    def full_name(self) -> str:
        """Get full name from first and last name"""
        return f"{self.first_name} {self.last_name}"


class UserCreate(UserBase):
    """User creation schema with password"""
    password: str
    
    @validator('password')
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserUpdate(BaseModel):
    """User update schema with optional fields"""
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    time_zone: Optional[str] = None
    locale: Optional[str] = None


class UserUpdatePassword(BaseModel):
    """Schema for password update"""
    current_password: str
    new_password: str
    
    @validator('new_password')
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserInDB(UserBase):
    """User schema with password hash (for internal use)"""
    id: int
    password_hash: str
    is_verified: bool = False
    avatar: Optional[str] = None
    bio: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        orm_mode = True


class UserResponse(UserBase):
    """User response schema (without sensitive data)"""
    id: int
    is_verified: bool = False
    avatar: Optional[str] = None
    bio: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        orm_mode = True


class UserListResponse(BaseModel):
    """Response schema for list of users"""
    total: int
    users: List[UserResponse]

    class Config:
        orm_mode = True