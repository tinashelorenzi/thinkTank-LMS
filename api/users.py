from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status, Query

from models.users import User, UserRole
from schemas.user import UserResponse, UserUpdate, UserUpdatePassword, UserListResponse
from core.security import (
    get_current_user, 
    get_current_active_user, 
    get_current_admin_user,
    get_password_hash, 
    verify_password
)
from utils.pagination import get_page_params, paginate_queryset, PageParams

# Create users router
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def read_user_me(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get current user
    """
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_user_me(
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update current user
    """
    # Update user fields
    if user_in.email is not None:
        # Check if email already exists
        existing_user = await User.get_or_none(email=user_in.email)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        current_user.email = user_in.email
    
    if user_in.username is not None:
        # Check if username already exists
        existing_user = await User.get_or_none(username=user_in.username)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )
        current_user.username = user_in.username
    
    # Update other fields
    if user_in.first_name is not None:
        current_user.first_name = user_in.first_name
    
    if user_in.last_name is not None:
        current_user.last_name = user_in.last_name
    
    if user_in.avatar is not None:
        current_user.avatar = user_in.avatar
    
    if user_in.bio is not None:
        current_user.bio = user_in.bio
    
    if user_in.time_zone is not None:
        current_user.time_zone = user_in.time_zone
    
    if user_in.locale is not None:
        current_user.locale = user_in.locale
    
    # Save user
    await current_user.save()
    
    return current_user


@router.put("/me/password", response_model=Dict[str, Any])
async def update_user_password(
    password_in: UserUpdatePassword,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update current user password
    """
    # Verify current password
    if not verify_password(password_in.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )
    
    # Update password
    current_user.password_hash = get_password_hash(password_in.new_password)
    await current_user.save()
    
    return {"message": "Password updated successfully"}


@router.get("", response_model=UserListResponse)
async def list_users(
    page_params: PageParams = Depends(get_page_params),
    role: UserRole = Query(None, description="Filter by user role"),
    search: str = Query(None, description="Search by username or email"),
    is_active: bool = Query(None, description="Filter by active status"),
    admin_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    List users (admin only)
    """
    # Create base query
    query = User.all()
    
    # Apply filters
    if role:
        query = query.filter(role=role)
    
    if is_active is not None:
        query = query.filter(is_active=is_active)
    
    if search:
        query = query.filter(
            (User.username.icontains(search)) | 
            (User.email.icontains(search)) |
            (User.first_name.icontains(search)) |
            (User.last_name.icontains(search))
        )
    
    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=UserResponse,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get user by ID
    """
    # Only allow users to fetch their own data, or admin users to fetch any data
    if current_user.id != user_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    
    # Get user
    user = await User.get_or_none(id=user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    admin_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update user (admin only)
    """
    # Get user
    user = await User.get_or_none(id=user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Update fields
    if user_in.email is not None:
        # Check if email already exists
        existing_user = await User.get_or_none(email=user_in.email)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        user.email = user_in.email
    
    if user_in.username is not None:
        # Check if username already exists
        existing_user = await User.get_or_none(username=user_in.username)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )
        user.username = user_in.username
    
    # Update other fields if provided
    for field, value in user_in.dict(exclude_unset=True).items():
        setattr(user, field, value)
    
    # Save user
    await user.save()
    
    return user


@router.delete("/{user_id}", response_model=Dict[str, Any])
async def delete_user(
    user_id: int,
    admin_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete user (admin only)
    """
    # Get user
    user = await User.get_or_none(id=user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Don't allow deleting the current admin user
    if user_id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )
    
    # Delete user
    await user.delete()
    
    return {"message": "User deleted successfully"}