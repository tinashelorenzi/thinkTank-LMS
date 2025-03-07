from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse

from models.course import Course
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.file import (
    File as FileModel, Folder, FileFolder, FileVersion, FilePermission,
    FileType, FileStatus, StorageProvider
)
from schemas.file import (
    FileCreate, FileUpdate, FileResponse, FileListResponse,
    FolderCreate, FolderUpdate, FolderResponse, FolderListResponse,
    FileUploadRequest, FileUploadResponse, FileDownloadResponse
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.files import save_upload_file, get_file_info, delete_file, create_presigned_url
from utils.pagination import get_page_params, paginate_queryset, PageParams
from core.config import settings
from datetime import datetime, timedelta


# Create files router
router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def create_file(
        file: UploadFile = File(...),
        course_id: Optional[int] = Query(None, description="Course ID to associate with the file"),
        assignment_id: Optional[int] = Query(None, description="Assignment ID to associate with the file"),
        folder_id: Optional[int] = Query(None, description="Folder ID to place the file in"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Upload a file
    """
    # Check course if provided
    course = None
    if course_id:
        course = await Course.get_or_none(id=course_id)

        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        # Check if user can upload to this course
        if current_user.role not in [UserRole.ADMIN, UserRole.INSTRUCTOR]:
            # Check enrollment
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course=course,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to upload files to this course",
                )

    # Check folder if provided
    folder = None
    if folder_id:
        folder = await Folder.get_or_none(id=folder_id)

        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )

        # Check if user can upload to this folder
        if current_user.role != UserRole.ADMIN:
            # Check if folder belongs to a course and user has permissions
            if folder.course_id:
                enrollment = await Enrollment.get_or_none(
                    user=current_user,
                    course_id=folder.course_id,
                    state=EnrollmentState.ACTIVE,
                )

                if not enrollment:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have permission to upload files to this folder",
                    )
            # Check if folder belongs to a user
            elif folder.user_id and folder.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to upload files to this folder",
                )

    # Determine upload directory
    upload_dir = "uploads"
    if course_id:
        upload_dir = f"uploads/courses/{course_id}"
        if assignment_id:
            upload_dir = f"{upload_dir}/assignments/{assignment_id}"
    else:
        upload_dir = f"uploads/users/{current_user.id}"

    # Save file
    try:
        # Supported file types
        allowed_extensions = ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt",
                              "jpg", "jpeg", "png", "gif", "zip", "rar", "csv", "json", "md"]

        file_info = await save_upload_file(
            file,
            directory=upload_dir,
            allowed_extensions=allowed_extensions,
            max_size_bytes=50 * 1024 * 1024,  # 50MB limit
        )

        # Determine file type
        file_type = FileType.OTHER
        if file.content_type.startswith("image/"):
            file_type = FileType.IMAGE
        elif file.content_type.startswith("video/"):
            file_type = FileType.VIDEO
        elif file.content_type.startswith("audio/"):
            file_type = FileType.AUDIO
        elif file.content_type in ["application/pdf"]:
            file_type = FileType.DOCUMENT
        elif file.content_type in ["application/zip", "application/x-rar-compressed"]:
            file_type = FileType.ARCHIVE
        elif file.content_type in ["application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
            file_type = FileType.SPREADSHEET
        elif file.content_type in ["application/vnd.ms-powerpoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation"]:
            file_type = FileType.PRESENTATION
        elif file.content_type in ["text/plain", "text/markdown", "text/x-python"]:
            file_type = FileType.SOURCE_CODE

        # Create file record
        db_file = await FileModel.create(
            name=file_info["original_filename"],
            file_type=file_type,
            mime_type=file_info["content_type"],
            size=file_info["size"],
            storage_provider=StorageProvider.LOCAL,
            storage_path=file_info["filepath"],
            status=FileStatus.AVAILABLE,
            original_filename=file_info["original_filename"],
            md5_hash=file_info["md5_hash"],
            sha256_hash=file_info["sha256_hash"],
            metadata=file_info.get("metadata"),
            uploaded_by=current_user,
            course_id=course_id,
            assignment_id=assignment_id,
        )

        # Add to folder if specified
        if folder:
            await FileFolder.create(
                file=db_file,
                folder=folder,
            )

        return db_file

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=FileListResponse)
async def list_files(
        page_params: PageParams = Depends(get_page_params),
        course_id: Optional[int] = Query(None, description="Filter by course ID"),
        assignment_id: Optional[int] = Query(None, description="Filter by assignment ID"),
        folder_id: Optional[int] = Query(None, description="Filter by folder ID"),
        file_type: Optional[FileType] = Query(None, description="Filter by file type"),
        search: Optional[str] = Query(None, description="Search by filename"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List files with various filters
    """
    # Create base query
    query = FileModel.all()

    # Apply course filter
    if course_id:
        query = query.filter(course_id=course_id)

        # Check if user can access this course
        if current_user.role != UserRole.ADMIN:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=course_id,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this course",
                )

    # Apply assignment filter
    if assignment_id:
        query = query.filter(assignment_id=assignment_id)

    # Apply folder filter
    if folder_id:
        folder = await Folder.get_or_none(id=folder_id)

        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )

        # Get files in this folder
        file_ids = await FileFolder.filter(folder=folder).values_list("file_id", flat=True)
        query = query.filter(id__in=file_ids)

        # Check if user can access this folder
        if current_user.role != UserRole.ADMIN:
            if folder.course_id:
                enrollment = await Enrollment.get_or_none(
                    user=current_user,
                    course_id=folder.course_id,
                    state=EnrollmentState.ACTIVE,
                )

                if not enrollment:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have access to this folder",
                    )
            elif folder.user_id and folder.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this folder",
                )

    # If no specific filters, show only files the user has access to
    if not course_id and not folder_id and current_user.role != UserRole.ADMIN:
        # Show files uploaded by the user
        query = query.filter(
            # Files uploaded by user
            (FileModel.uploaded_by == current_user) |
            # Files in courses where user is enrolled
            (FileModel.course_id.in_(
                Enrollment.filter(
                    user=current_user,
                    state=EnrollmentState.ACTIVE
                ).values_list("course_id", flat=True)
            )) |
            # Public files
            (FileModel.is_public == True)
        )

    # Apply file type filter
    if file_type:
        query = query.filter(file_type=file_type)

    # Apply search filter
    if search:
        query = query.filter(
            (FileModel.name.icontains(search)) |
            (FileModel.original_filename.icontains(search))
        )

    # Only show available files
    query = query.filter(status=FileStatus.AVAILABLE)

    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=FileResponse,
    )


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
        file_id: int = Path(..., description="The ID of the file"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get file details by ID
    """
    # Get file
    file = await FileModel.get_or_none(id=file_id).prefetch_related("uploaded_by")

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Check if user can access this file
    if current_user.role != UserRole.ADMIN:
        # User can access their own files
        if file.uploaded_by_id == current_user.id:
            return file

        # Check if file is in a course the user is enrolled in
        if file.course_id:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=file.course_id,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this file",
                )
        # Check if file is public
        elif not file.is_public:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this file",
            )

    # Increment download count
    file.download_count += 1
    await file.save()

    return file


@router.get("/download/{file_id}", response_model=FileDownloadResponse)
async def download_file(
        file_id: int = Path(..., description="The ID of the file"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get download URL for a file
    """
    # Get file
    file = await FileModel.get_or_none(id=file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Check if user can access this file
    if current_user.role != UserRole.ADMIN:
        # User can access their own files
        if file.uploaded_by_id == current_user.id:
            pass
        # Check if file is in a course the user is enrolled in
        elif file.course_id:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=file.course_id,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this file",
                )
        # Check if file is public
        elif not file.is_public:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this file",
            )

    # Generate download URL
    download_url = await create_presigned_url(
        file.storage_path,
        expiration_minutes=60,
        file_type=file.mime_type,
    )

    # Increment download count
    file.download_count += 1
    await file.save()

    return {
        "download_url": download_url,
        "filename": file.name,
        "mime_type": file.mime_type,
        "size": file.size,
        "expires_at": datetime.utcnow() + timedelta(minutes=60),
    }


@router.delete("/{file_id}", response_model=Dict[str, Any])
async def delete_file_api(
        file_id: int = Path(..., description="The ID of the file"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete a file
    """
    # Get file
    file = await FileModel.get_or_none(id=file_id)

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Check if user can delete this file
    if current_user.role != UserRole.ADMIN:
        # User can delete their own files
        if file.uploaded_by_id != current_user.id:
            # Check if user is instructor of the course
            if file.course_id:
                is_instructor = await Enrollment.filter(
                    user=current_user,
                    course_id=file.course_id,
                    type=EnrollmentType.TEACHER,
                    state=EnrollmentState.ACTIVE,
                ).exists()

                if not is_instructor:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have permission to delete this file",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to delete this file",
                )

    # Delete file from storage
    await delete_file(file.storage_path)

    # Mark file as deleted in database
    file.status = FileStatus.DELETED
    await file.save()

    return {"message": "File deleted successfully"}


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
        folder_in: FolderCreate,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create a new folder
    """
    # Check parent folder if provided
    if folder_in.parent_id:
        parent_folder = await Folder.get_or_none(id=folder_in.parent_id)

        if not parent_folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent folder not found",
            )

        # Check if user can create folders in this parent
        if current_user.role != UserRole.ADMIN:
            if parent_folder.course_id:
                is_instructor = await Enrollment.filter(
                    user=current_user,
                    course_id=parent_folder.course_id,
                    type=EnrollmentType.TEACHER,
                    state=EnrollmentState.ACTIVE,
                ).exists()

                if not is_instructor and not (folder_in.user_id and folder_in.user_id == current_user.id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have permission to create folders here",
                    )
            elif parent_folder.user_id and parent_folder.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to create folders here",
                )

        # Build path from parent
        path = f"{parent_folder.path}/{folder_in.name}"
    else:
        # Root path depends on context
        if folder_in.course_id:
            path = f"/courses/{folder_in.course_id}/{folder_in.name}"

            # Check if course exists
            course = await Course.get_or_none(id=folder_in.course_id)

            if not course:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )

            # Check if user can create folders in this course
            if current_user.role != UserRole.ADMIN:
                is_instructor = await Enrollment.filter(
                    user=current_user,
                    course=course,
                    type=EnrollmentType.TEACHER,
                    state=EnrollmentState.ACTIVE,
                ).exists()

                if not is_instructor:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have permission to create folders in this course",
                    )
        elif folder_in.user_id:
            path = f"/users/{folder_in.user_id}/{folder_in.name}"

            # Users can only create folders for themselves unless admin
            if current_user.role != UserRole.ADMIN and folder_in.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only create folders for yourself",
                )
        else:
            # If neither course nor user is specified, default to user's folder
            path = f"/users/{current_user.id}/{folder_in.name}"
            folder_in.user_id = current_user.id

    # Create folder
    folder = await Folder.create(
        name=folder_in.name,
        parent_id=folder_in.parent_id,
        course_id=folder_in.course_id,
        user_id=folder_in.user_id if folder_in.user_id else current_user.id,
        path=path,
        position=folder_in.position,
        is_public=folder_in.is_public,
    )

    return folder


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
        page_params: PageParams = Depends(get_page_params),
        course_id: Optional[int] = Query(None, description="Filter by course ID"),
        user_id: Optional[int] = Query(None, description="Filter by user ID"),
        parent_id: Optional[int] = Query(None, description="Filter by parent folder ID"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List folders with various filters
    """
    # Create base query
    query = Folder.all()

    # Apply course filter
    if course_id:
        query = query.filter(course_id=course_id)

        # Check if user can access this course
        if current_user.role != UserRole.ADMIN:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=course_id,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this course",
                )

    # Apply user filter
    if user_id:
        query = query.filter(user_id=user_id)

        # Users can only see their own folders unless admin
        if current_user.role != UserRole.ADMIN and user_id != current_user.id:
            # Allow if folders are public
            query = query.filter(is_public=True)

    # Apply parent filter
    if parent_id:
        query = query.filter(parent_id=parent_id)

    # If no specific filters, show only folders the user has access to
    if not course_id and not user_id and not parent_id and current_user.role != UserRole.ADMIN:
        query = query.filter(
            # User's own folders
            (Folder.user_id == current_user.id) |
            # Folders in courses where user is enrolled
            (Folder.course_id.in_(
                Enrollment.filter(
                    user=current_user,
                    state=EnrollmentState.ACTIVE
                ).values_list("course_id", flat=True)
            )) |
            # Public folders
            (Folder.is_public == True)
        )

    # Get paginated results
    return await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=FolderResponse,
    )


@router.get("/folders/{folder_id}", response_model=FolderResponse)
async def get_folder(
        folder_id: int = Path(..., description="The ID of the folder"),
        include_files: bool = Query(False, description="Include files in the folder"),
        include_children: bool = Query(False, description="Include child folders"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get folder details by ID
    """
    # Get folder
    folder = await Folder.get_or_none(id=folder_id)

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
        )

    # Check if user can access this folder
    if current_user.role != UserRole.ADMIN:
        # User can access their own folders
        if folder.user_id == current_user.id:
            pass
        # Check if folder is in a course the user is enrolled in
        elif folder.course_id:
            enrollment = await Enrollment.get_or_none(
                user=current_user,
                course_id=folder.course_id,
                state=EnrollmentState.ACTIVE,
            )

            if not enrollment:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this folder",
                )
        # Check if folder is public
        elif not folder.is_public:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this folder",
            )

    # Include files if requested
    if include_files:
        # Get files in this folder
        file_folders = await FileFolder.filter(folder=folder).prefetch_related("file")
        folder.files = [ff.file for ff in file_folders]

    # Include child folders if requested
    if include_children:
        children = await Folder.filter(parent=folder).all()
        folder.children = children

    return folder


@router.put("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
        folder_in: FolderUpdate,
        folder_id: int = Path(..., description="The ID of the folder"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update folder details
    """
    # Get folder
    folder = await Folder.get_or_none(id=folder_id)

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
        )

    # Check if user can update this folder
    if current_user.role != UserRole.ADMIN:
        # User can update their own folders
        if folder.user_id != current_user.id:
            # Check if user is instructor of the course
            if folder.course_id:
                is_instructor = await Enrollment.filter(
                    user=current_user,
                    course_id=folder.course_id,
                    type=EnrollmentType.TEACHER,
                    state=EnrollmentState.ACTIVE,
                ).exists()

                if not is_instructor:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have permission to update this folder",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to update this folder",
                )

    # Update fields
    if folder_in.name:
        folder.name = folder_in.name
        # Update path
        if folder.parent_id:
            parent = await Folder.get(id=folder.parent_id)
            folder.path = f"{parent.path}/{folder.name}"
        else:
            if folder.course_id:
                folder.path = f"/courses/{folder.course_id}/{folder.name}"
            else:
                folder.path = f"/users/{folder.user_id}/{folder.name}"

    if folder_in.parent_id is not None:
        folder.parent_id = folder_in.parent_id

        if folder_in.parent_id:
            parent = await Folder.get(id=folder_in.parent_id)
            folder.path = f"{parent.path}/{folder.name}"
        else:
            if folder.course_id:
                folder.path = f"/courses/{folder.course_id}/{folder.name}"
            else:
                folder.path = f"/users/{folder.user_id}/{folder.name}"

    if folder_in.position is not None:
        folder.position = folder_in.position

    if folder_in.is_public is not None:
        folder.is_public = folder_in.is_public

    # Save folder
    await folder.save()

    return folder


@router.delete("/folders/{folder_id}", response_model=Dict[str, Any])
async def delete_folder(
        folder_id: int = Path(..., description="The ID of the folder"),
        recursive: bool = Query(False, description="Delete all children recursively"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete a folder
    """
    # Get folder
    folder = await Folder.get_or_none(id=folder_id)

    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
        )

    # Check if user can delete this folder
    if current_user.role != UserRole.ADMIN:
        # User can delete their own folders
        if folder.user_id != current_user.id:
            # Check if user is instructor of the course
            if folder.course_id:
                is_instructor = await Enrollment.filter(
                    user=current_user,
                    course_id=folder.course_id,
                    type=EnrollmentType.TEACHER,
                    state=EnrollmentState.ACTIVE,
                ).exists()

                if not is_instructor:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have permission to delete this folder",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to delete this folder",
                )

    # Check for child folders
    child_folders = await Folder.filter(parent=folder).count()

    if child_folders > 0 and not recursive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder contains child folders. Use recursive=true to delete them as well.",
        )

    # Check for files
    file_count = await FileFolder.filter(folder=folder).count()

    if file_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Folder contains {file_count} files. Remove files before deleting folder.",
        )

    # If recursive, delete all child folders
    if recursive and child_folders > 0:
        # Get all descendant folders recursively
        async def get_descendants(parent_id):
            children = await Folder.filter(parent_id=parent_id).all()
            descendant_ids = [child.id for child in children]

            for child in children:
                child_descendants = await get_descendants(child.id)
                descendant_ids.extend(child_descendants)

            return descendant_ids

        descendant_ids = await get_descendants(folder.id)

        # Check if any descendants have files
        descendant_file_count = await FileFolder.filter(folder_id__in=descendant_ids).count()

        if descendant_file_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Folder tree contains {descendant_file_count} files. Remove files before deleting folders.",
            )

        # Delete all descendants (from bottom up)
        for descendant_id in reversed(descendant_ids):
            await Folder.filter(id=descendant_id).delete()

    # Delete folder
    await folder.delete()

    return {"message": "Folder deleted successfully"}