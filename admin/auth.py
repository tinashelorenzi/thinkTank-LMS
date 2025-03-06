from typing import Optional, Tuple
from jose import jwt, JWTError

from starlette.authentication import (
    AuthenticationBackend,
    AuthCredentials,
    BaseUser,
    UnauthenticatedUser,
)
from starlette.requests import Request

from core.config import settings
from models.user import User, UserRole


class AdminUser(BaseUser):
    """Admin user for authentication"""
    
    def __init__(self, user_id: int, username: str, role: UserRole):
        self.user_id = user_id
        self.username = username
        self.role = role
    
    @property
    def is_authenticated(self) -> bool:
        return True
    
    @property
    def display_name(self) -> str:
        return self.username
    
    @property
    def identity(self) -> str:
        return str(self.user_id)


class AdminAuth(AuthenticationBackend):
    """
    Authentication backend for FastAPI Admin
    """
    
    async def authenticate(
        self, request: Request
    ) -> Tuple[AuthCredentials, BaseUser]:
        # Get token from cookies
        token = request.cookies.get("admin_access_token")
        
        # No token
        if not token:
            return self._unauthenticated()
        
        # Parse token
        if token.startswith("Bearer "):
            token = token[7:]
        
        # Validate token
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
            user_id = payload.get("sub")
            if not user_id:
                return self._unauthenticated()
        except JWTError:
            return self._unauthenticated()
        
        # Get user
        user = await User.get_or_none(id=user_id)
        if not user:
            return self._unauthenticated()
        
        # Ensure user is admin
        if user.role != UserRole.ADMIN:
            return self._unauthenticated()
        
        # Authenticated
        return AuthCredentials(["authenticated"]), AdminUser(
            user_id=user.id,
            username=user.username,
            role=user.role,
        )
    
    def _unauthenticated(self) -> Tuple[AuthCredentials, UnauthenticatedUser]:
        """Return unauthenticated user"""
        return AuthCredentials(), UnauthenticatedUser()