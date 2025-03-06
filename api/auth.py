from datetime import timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.security import OAuth2PasswordRequestForm

from models.user import User, UserRole
from schemas.token import Token
from schemas.user import UserCreate, UserResponse
from core.config import settings
from core.security import get_password_hash, verify_password, create_access_token
from utils.email import send_verification_email
from utils.hashing import generate_verification_token

# Create auth router
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Dict[str, Any]:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # Authenticate user
    user = await User.get_or_none(username=form_data.username)
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
    )
    
    # Update last login timestamp
    user.last_login = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    await user.save()
    
    # Return token
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "role": user.role.value,
    }


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate, 
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Register a new user
    """
    # Check if username already exists
    existing_username = await User.get_or_none(username=user_in.username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    
    # Check if email already exists
    existing_email = await User.get_or_none(email=user_in.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Create new user
    user = await User.create(
        email=user_in.email,
        username=user_in.username,
        password_hash=get_password_hash(user_in.password),
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        role=user_in.role,
        is_active=True,
        is_verified=False,
    )
    
    # Generate verification token
    token = generate_verification_token(user.email)
    
    # Send verification email in background
    background_tasks.add_task(
        send_verification_email,
        email_to=user.email,
        token=token,
        username=user.username,
    )
    
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.get("/verify", status_code=status.HTTP_200_OK)
async def verify_email(token: str) -> Dict[str, Any]:
    """
    Verify user email
    """
    # Verify token
    from utils.hashing import verify_verification_token
    email = verify_verification_token(token)
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )
    
    # Update user
    user = await User.get_or_none(email=email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Mark as verified
    user.is_verified = True
    await user.save()
    
    return {"message": "Email verified successfully"}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password_request(
    email: str, 
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Request password reset
    """
    # Find user
    user = await User.get_or_none(email=email)
    
    # Always return success, even if user not found, to prevent enumeration
    if not user:
        return {"message": "If the email is registered, a password reset link has been sent"}
    
    # Generate reset token
    from utils.hashing import generate_password_reset_token
    token = generate_password_reset_token(email)
    
    # Send reset email in background
    from utils.email import send_reset_password_email
    background_tasks.add_task(
        send_reset_password_email,
        email_to=user.email,
        token=token,
        username=user.username,
    )
    
    return {"message": "If the email is registered, a password reset link has been sent"}


@router.post("/reset-password/{token}", status_code=status.HTTP_200_OK)
async def reset_password(token: str, new_password: str) -> Dict[str, Any]:
    """
    Reset password with token
    """
    # Verify token
    from utils.hashing import verify_password_reset_token
    email = verify_password_reset_token(token)
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        )
    
    # Update user
    user = await User.get_or_none(email=email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Update password
    user.password_hash = get_password_hash(new_password)
    await user.save()
    
    return {"message": "Password reset successfully"}