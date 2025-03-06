from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class UserRole(str, Enum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    TEACHING_ASSISTANT = "teaching_assistant"
    OBSERVER = "observer"
    ADMIN = "admin"


class User(models.Model):
    """User model representing all types of users in the LMS system"""
    
    id = fields.IntField(pk=True)
    email = fields.CharField(max_length=255, unique=True)
    username = fields.CharField(max_length=50, unique=True)
    password_hash = fields.CharField(max_length=128)
    first_name = fields.CharField(max_length=50)
    last_name = fields.CharField(max_length=50)
    role = fields.CharEnumField(UserRole, default=UserRole.STUDENT)
    
    is_active = fields.BooleanField(default=True)
    is_verified = fields.BooleanField(default=False)
    
    # Profile fields
    avatar = fields.CharField(max_length=255, null=True)
    bio = fields.TextField(null=True)
    time_zone = fields.CharField(max_length=50, default="UTC")
    locale = fields.CharField(max_length=10, default="en")
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_login = fields.DatetimeField(null=True)
    
    # Relationships - these will be referenced by other models
    # courses: ReverseRelation[Course] - Through enrollment
    # submissions: ReverseRelation[Submission]
    
    class Meta:
        table = "users"
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.username})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


# Pydantic models for validation and serialization
User_Pydantic = pydantic_model_creator(User, name="User")
UserCreate_Pydantic = pydantic_model_creator(
    User, name="UserCreate", exclude=("id", "created_at", "updated_at", "last_login")
)
UserUpdate_Pydantic = pydantic_model_creator(
    User, name="UserUpdate", exclude_readonly=True, optional=True
)