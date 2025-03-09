from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course
from models.users import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.module import (
    Module, ModuleItem, ModuleCompletion, ModuleItemCompletion,
    ModuleType, CompletionRequirement
)
from models.file import File
from schemas.module import (
    ModuleCreate, ModuleUpdate, ModuleResponse, ModuleListResponse,
    ModuleItemCreate, ModuleItemUpdate, ModuleItemResponse, ModuleItemListResponse,
    ModuleCompletionCreate, ModuleCompletionUpdate, ModuleCompletionResponse,
    ModuleItemCompletionCreate, ModuleItemCompletionUpdate, ModuleItemCompletionResponse
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.pagination import get_page_params, paginate_queryset, PageParams
from core.config import settings
from typing import Any, Dict
from datetime import datetime

# Create modules router
router = APIRouter(prefix="/modules", tags=["modules"])


@router.post("", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module(
        module_in: ModuleCreate,
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new module (instructor or admin only)
    """
    # Get course
    course = await Course.get_or_none(id=module_in.course_id)

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Check if user has permission to create modules for this course
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create modules for this course",
            )

    # Get max position for ordering
    max_position = await Module.filter(course=course).count()

    # Create module
    module = await Module.create(
        title=module_in.title,
        description=module_in.description,
        course=course,
        module_type=module_in.module_type,
        position=module_in.position if module_in.position is not None else max_position,
        is_published=module_in.is_published,
        is_hidden=module_in.is_hidden,
        available_from=module_in.available_from,
        available_until=module_in.available_until,
        completion_requirement=module_in.completion_requirement,
        require_sequential_progress=module_in.require_sequential_progress,
        external_url=module_in.external_url,
        external_tool_id=module_in.external_tool_id,
    )

    # Add prerequisite modules if specified
    if module_in.prerequisite_module_ids:
        for prereq_id in module_in.prerequisite_module_ids:
            prereq_module = await Module.get_or_none(id=prereq_id, course=course)
            if prereq_module:
                await module.prerequisite_modules.add(prereq_module)

    # Count items
    module.item_count = 0

    return module


@router.get("", response_model=ModuleListResponse)
async def list_modules(
        page_params: PageParams = Depends(get_page_params),
        course_id: int = Query(..., description="Course ID"),
        include_hidden: bool = Query(False, description="Include hidden modules"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List modules for a course
    """
    # Get course
    course = await Course.get_or_none(id=course_id)

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Check if user can access this course
    if current_user.role != UserRole.ADMIN:
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    # Create base query
    query = Module.filter(course=course)

    # For non-admin/non-instructor users, only show published modules
    is_instructor = False
    if current_user.role != UserRole.ADMIN:
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            query = query.filter(is_published=True)

    # Include hidden modules if requested and user has permission
    if not include_hidden and not is_instructor and current_user.role != UserRole.ADMIN:
        query = query.filter(is_hidden=False)

    # Order by position
    query = query.order_by("position")

    # Get paginated results with prerequisite modules
    modules = await query.prefetch_related("prerequisite_modules").all()

    # Count items in each module
    for module in modules:
        module.item_count = await ModuleItem.filter(module=module).count()

    # Create paginated response manually
    total = len(modules)
    return {
        "total": total,
        "modules": modules,
    }


@router.get("/{module_id}", response_model=ModuleResponse)
async def get_module(
        module_id: int = Path(..., description="The ID of the module"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get module by ID
    """
    # Get module with prerequisites
    module = await Module.get_or_none(id=module_id).prefetch_related(
        "course", "prerequisite_modules"
    )

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    # Check if user can access this module
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=module.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

        # Check if module is published (for non-instructors)
        is_instructor = enrollment.type == EnrollmentType.TEACHER
        if not is_instructor and not module.is_published:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This module is not published",
            )

        # Check if module is hidden (for non-instructors)
        if not is_instructor and module.is_hidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This module is hidden",
            )

    # Count items
    module.item_count = await ModuleItem.filter(module=module).count()

    return module


@router.put("/{module_id}", response_model=ModuleResponse)
async def update_module(
        module_in: ModuleUpdate,
        module_id: int = Path(..., description="The ID of the module"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update a module (instructor or admin only)
    """
    # Get module
    module = await Module.get_or_none(id=module_id).prefetch_related("course", "prerequisite_modules")

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    # Check if user has permission to update this module
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=module.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this module",
            )

    # Update fields
    for field, value in module_in.dict(exclude_unset=True, exclude={"prerequisite_module_ids"}).items():
        setattr(module, field, value)

    # Update prerequisite modules if specified
    if module_in.prerequisite_module_ids is not None:
        # Clear existing prerequisites
        await module.prerequisite_modules.clear()

        # Add new prerequisites
        for prereq_id in module_in.prerequisite_module_ids:
            prereq_module = await Module.get_or_none(id=prereq_id, course=module.course)
            if prereq_module:
                await module.prerequisite_modules.add(prereq_module)

    # Save module
    await module.save()

    # Count items
    module.item_count = await ModuleItem.filter(module=module).count()

    return module


@router.delete("/{module_id}", response_model=Dict[str, Any])
async def delete_module(
        module_id: int = Path(..., description="The ID of the module"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete a module (instructor or admin only)
    """
    # Get module
    module = await Module.get_or_none(id=module_id).prefetch_related("course")

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    # Check if user has permission to delete this module
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=module.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this module",
            )

    # Check if module has items
    items_count = await ModuleItem.filter(module=module).count()

    if items_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete module with {items_count} items. Remove items first.",
        )

    # Delete module
    await module.delete()

    return {"message": "Module deleted successfully"}


@router.post("/{module_id}/items", response_model=ModuleItemResponse, status_code=status.HTTP_201_CREATED)
async def create_module_item(
        item_in: ModuleItemCreate,
        module_id: int = Path(..., description="The ID of the module"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new module item (instructor or admin only)
    """
    # Get module
    module = await Module.get_or_none(id=module_id).prefetch_related("course")

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    # Check if user has permission to add items to this module
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=module.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to add items to this module",
            )

    # Check file if specified
    file = None
    if item_in.file_id:
        file = await File.get_or_none(id=item_in.file_id)

        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

    # Get max position for ordering
    max_position = await ModuleItem.filter(module=module).count()

    # Create module item
    item = await ModuleItem.create(
        title=item_in.title,
        module=module,
        position=item_in.position if item_in.position is not None else max_position,
        content_type=item_in.content_type,
        content_id=item_in.content_id,
        page_content=item_in.page_content,
        external_url=item_in.external_url,
        html_content=item_in.html_content,
        file=file,
        is_published=item_in.is_published,
        indent_level=item_in.indent_level,
        completion_requirement=item_in.completion_requirement,
        min_score=item_in.min_score,
    )

    return item


@router.get("/{module_id}/items", response_model=ModuleItemListResponse)
async def list_module_items(
        module_id: int = Path(..., description="The ID of the module"),
        page_params: PageParams = Depends(get_page_params),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List items in a module
    """
    # Get module
    module = await Module.get_or_none(id=module_id).prefetch_related("course")

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    # Check if user can access this module
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=module.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

        # Check if module is published (for non-instructors)
        is_instructor = enrollment.type == EnrollmentType.TEACHER
        if not is_instructor and not module.is_published:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This module is not published",
            )

        # Check if module is hidden (for non-instructors)
        if not is_instructor and module.is_hidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This module is hidden",
            )

    # Create base query
    query = ModuleItem.filter(module=module)

    # For non-admin/non-instructor users, only show published items
    is_instructor = False
    if current_user.role != UserRole.ADMIN:
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=module.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            query = query.filter(is_published=True)

    # Order by position
    query = query.order_by("position")

    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=ModuleItemResponse,
    )


@router.get("/items/{item_id}", response_model=ModuleItemResponse)
async def get_module_item(
        item_id: int = Path(..., description="The ID of the module item"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get module item by ID
    """
    # Get item
    item = await ModuleItem.get_or_none(id=item_id).prefetch_related("module", "module__course", "file")

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module item not found",
        )

    # Check if user can access this item
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=item.module.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

        # Check if module and item are published (for non-instructors)
        is_instructor = enrollment.type == EnrollmentType.TEACHER
        if not is_instructor:
            if not item.module.is_published:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This module is not published",
                )

            if not item.is_published:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This item is not published",
                )

            if item.module.is_hidden:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This module is hidden",
                )

    # Record view for completion tracking
    if current_user.role != UserRole.ADMIN:
        # Check if there's an existing completion record
        completion = await ModuleItemCompletion.get_or_none(item=item, user=current_user)

        if completion:
            # Update view count and last viewed
            completion.view_count += 1
            completion.last_viewed_at = datetime.utcnow()

            # Mark as completed if view requirement
            if item.completion_requirement == CompletionRequirement.VIEW and not completion.is_completed:
                completion.is_completed = True
                completion.completed_at = datetime.utcnow()

            await completion.save()
        else:
            # Create new completion record
            is_completed = item.completion_requirement == CompletionRequirement.VIEW
            await ModuleItemCompletion.create(
                item=item,
                user=current_user,
                is_completed=is_completed,
                completed_at=datetime.utcnow() if is_completed else None,
                view_count=1,
                last_viewed_at=datetime.utcnow(),
            )

            # Update module completion if all items are completed
            if is_completed:
                await update_module_completion(item.module, current_user)

    return item


@router.put("/items/{item_id}", response_model=ModuleItemResponse)
async def update_module_item(
        item_in: ModuleItemUpdate,
        item_id: int = Path(..., description="The ID of the module item"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update a module item (instructor or admin only)
    """
    # Get item
    item = await ModuleItem.get_or_none(id=item_id).prefetch_related("module", "module__course", "file")

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module item not found",
        )

    # Check if user has permission to update this item
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=item.module.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this item",
            )

    # Check file if specified
    if item_in.file_id is not None:
        if item_in.file_id:
            file = await File.get_or_none(id=item_in.file_id)

            if not file:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found",
                )

            item.file = file
        else:
            item.file = None

    # Update fields
    for field, value in item_in.dict(exclude_unset=True, exclude={"file_id"}).items():
        setattr(item, field, value)

    # Save item
    await item.save()

    return item


@router.delete("/items/{item_id}", response_model=Dict[str, Any])
async def delete_module_item(
        item_id: int = Path(..., description="The ID of the module item"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete a module item (instructor or admin only)
    """
    # Get item
    item = await ModuleItem.get_or_none(id=item_id).prefetch_related("module", "module__course")

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module item not found",
        )

    # Check if user has permission to delete this item
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=item.module.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this item",
            )

    # Delete item
    await item.delete()

    return {"message": "Module item deleted successfully"}


@router.post("/{module_id}/complete", response_model=ModuleCompletionResponse)
async def mark_module_complete(
        module_id: int = Path(..., description="The ID of the module"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Mark a module as completed
    """
    # Get module
    module = await Module.get_or_none(id=module_id).prefetch_related("course")

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    # Check if user can access this module
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=module.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    # Check if module has completion requirements
    if module.completion_requirement:
        # Get all items in the module
        items = await ModuleItem.filter(module=module).all()
        item_ids = [item.id for item in items]

        # Get completed items
        completions = await ModuleItemCompletion.filter(
            item_id__in=item_ids,
            user=current_user,
            is_completed=True,
        ).all()

        completed_item_ids = [completion.item_id for completion in completions]

        # Check if all required items are completed
        if module.completion_requirement != CompletionRequirement.NONE and len(completed_item_ids) < len(item_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot mark module as complete. Not all required items are completed.",
            )

    # Get or create module completion record
    completion, created = await ModuleCompletion.get_or_create(
        module=module,
        user=current_user,
    )

    # Update completion status
    completion.is_completed = True
    completion.completed_at = datetime.utcnow()
    completion.progress_percent = 100.0

    await completion.save()

    return completion


# Helper function to update module completion status
async def update_module_completion(module: Module, user: User) -> None:
    """Update module completion status based on completed items"""
    # Get all items in the module
    items = await ModuleItem.filter(module=module).all()

    if not items:
        return

    item_ids = [item.id for item in items]
    item_count = len(items)

    # Get completed items
    completions = await ModuleItemCompletion.filter(
        item_id__in=item_ids,
        user=user,
        is_completed=True,
    ).all()

    completed_count = len(completions)

    # Calculate progress percentage
    progress_percent = (completed_count / item_count) * 100 if item_count > 0 else 0

    # Determine if module is completed
    is_completed = False
    if module.completion_requirement == CompletionRequirement.VIEW and progress_percent >= 100:
        is_completed = True

    # Update or create module completion record
    completion, created = await ModuleCompletion.get_or_create(
        module=module,
        user=user,
    )

    completion.progress_percent = progress_percent

    if is_completed and not completion.is_completed:
        completion.is_completed = True
        completion.completed_at = datetime.utcnow()

    await completion.save()