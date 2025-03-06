"""
Password hashing and security utilities
"""
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional
import uuid

from passlib.context import CryptContext
from jose import jwt

from core.config import settings


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash
    
    Args:
        plain_password: Plain-text password
        hashed_password: Hashed password to compare against
        
    Returns:
        True if password matches hash, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password
    
    Args:
        password: Plain-text password to hash
        
    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


def generate_password_reset_token(email: str) -> str:
    """
    Generate a password reset token for a user
    
    Args:
        email: User's email address
        
    Returns:
        JWT token for password reset
    """
    delta = timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_MINUTES / 60)  # Convert minutes to hours
    now = datetime.utcnow()
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now.timestamp(), "sub": email, "type": "reset"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> Optional[str]:
    """
    Verify a password reset token and return the user's email
    
    Args:
        token: JWT token to verify
        
    Returns:
        User's email if token is valid, None otherwise
    """
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if decoded_token["type"] != "reset":
            return None
        return decoded_token["sub"]
    except jwt.JWTError:
        return None


def generate_verification_token(email: str) -> str:
    """
    Generate an email verification token
    
    Args:
        email: User's email address
        
    Returns:
        JWT token for email verification
    """
    delta = timedelta(hours=24)  # Valid for 24 hours
    now = datetime.utcnow()
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now.timestamp(), "sub": email, "type": "verification"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def verify_verification_token(token: str) -> Optional[str]:
    """
    Verify an email verification token and return the user's email
    
    Args:
        token: JWT token to verify
        
    Returns:
        User's email if token is valid, None otherwise
    """
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if decoded_token["type"] != "verification":
            return None
        return decoded_token["sub"]
    except jwt.JWTError:
        return None


def generate_token(length: int = 32) -> str:
    """
    Generate a secure random token
    
    Args:
        length: Length of the token in characters
        
    Returns:
        Secure random token
    """
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def generate_join_code(length: int = 8) -> str:
    """
    Generate a join code for course or group access
    
    Args:
        length: Length of the join code
        
    Returns:
        Join code string
    """
    # Use uppercase letters and numbers, but exclude characters that could be confused
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # No I, O, 0, 1 to avoid confusion
    return ''.join(secrets.choice(chars) for _ in range(length))


def generate_uuid() -> str:
    """
    Generate a UUID string
    
    Returns:
        UUID string
    """
    return str(uuid.uuid4())