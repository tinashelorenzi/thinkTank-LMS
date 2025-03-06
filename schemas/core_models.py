from enum import Enum
from tortoise import fields
from tortoise.models import Model

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"

class User(Model):
    username = fields.CharField(max_length=50, unique=True)
    email = fields.CharField(max_length=255, unique=True)
    password_hash = fields.CharField(max_length=128)
    first_name = fields.CharField(max_length=50)
    last_name = fields.CharField(max_length=50)
    role = fields.CharEnumField(UserRole, default=UserRole.USER)
    is_active = fields.BooleanField(default=True)
    is_verified = fields.BooleanField(default=False)