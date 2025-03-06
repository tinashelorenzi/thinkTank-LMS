from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from models.file import FileType, FileStatus, StorageProvider


class FileBase(BaseModel):
    """Base schema for file"""
    name: str
    file_type: FileType = FileType.OTHER
    mime_type: str
    size: int
    storage_provider: StorageProvider = StorageProvider.LOCAL
    storage_path: str
    public_url: Optional[str] = None
    status: FileStatus = FileStatus.PENDING
    original_filename: str
    md5_hash: Optional[str] = None
    sha256_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    uploaded_by_id: int
    is_public: bool = False
    course_id: Optional[int] = None
    assignment_id: Optional[int] = None
    submission_id: Optional[int] = None
    expires_at: Optional[datetime] = None


class FileCreate(FileBase):
    """Schema for creating a file"""
    folder_ids: Optional[List[int]] = None


class FileUpdate(BaseModel):
    """Schema for updating a file"""
    name: Optional[str] = None
    file_type: Optional[FileType] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None
    storage_provider: Optional[StorageProvider] = None
    storage_path: Optional[str] = None
    public_url: Optional[str] = None
    status: Optional[FileStatus] = None
    md5_hash: Optional[str] = None
    sha256_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None
    course_id: Optional[int] = None
    assignment_id: Optional[int] = None
    submission_id: Optional[int] = None
    expires_at: Optional[datetime] = None
    folder_ids: Optional[List[int]] = None


class FileResponse(FileBase):
    """Response schema for a file"""
    id: int
    download_count: int = 0
    uploaded_at: datetime
    updated_at: datetime
    uploaded_by: Dict[str, Any]
    folders: List[Dict[str, Any]] = []
    
    class Config:
        orm_mode = True


class FileListResponse(BaseModel):
    """Response schema for list of files"""
    total: int
    files: List[FileResponse]

    class Config:
        orm_mode = True


class FolderBase(BaseModel):
    """Base schema for folder"""
    name: str
    parent_id: Optional[int] = None
    course_id: Optional[int] = None
    user_id: Optional[int] = None
    path: str
    position: int = 0
    is_public: bool = False


class FolderCreate(FolderBase):
    """Schema for creating a folder"""
    pass


class FolderUpdate(BaseModel):
    """Schema for updating a folder"""
    name: Optional[str] = None
    parent_id: Optional[int] = None
    position: Optional[int] = None
    is_public: Optional[bool] = None


class FolderResponse(FolderBase):
    """Response schema for a folder"""
    id: int
    created_at: datetime
    updated_at: datetime
    children: List['FolderResponse'] = []
    files: List[FileResponse] = []
    
    class Config:
        orm_mode = True


# Resolve forward reference for nested folders
FolderResponse.update_forward_refs()


class FolderListResponse(BaseModel):
    """Response schema for list of folders"""
    total: int
    folders: List[FolderResponse]

    class Config:
        orm_mode = True


class FileFolderBase(BaseModel):
    """Base schema for file-folder relationship"""
    file_id: int
    folder_id: int
    position: int = 0


class FileFolderCreate(FileFolderBase):
    """Schema for creating a file-folder relationship"""
    pass


class FileFolderUpdate(BaseModel):
    """Schema for updating a file-folder relationship"""
    position: Optional[int] = None


class FileVersionBase(BaseModel):
    """Base schema for file version"""
    file_id: int
    version_number: int
    storage_path: str
    size: int
    md5_hash: Optional[str] = None
    comment: Optional[str] = None
    created_by_id: int


class FileVersionCreate(FileVersionBase):
    """Schema for creating a file version"""
    pass


class FileVersionResponse(FileVersionBase):
    """Response schema for a file version"""
    id: int
    created_at: datetime
    created_by: Dict[str, Any]
    
    class Config:
        orm_mode = True


class FileVersionListResponse(BaseModel):
    """Response schema for list of file versions"""
    total: int
    versions: List[FileVersionResponse]

    class Config:
        orm_mode = True


class FilePermissionBase(BaseModel):
    """Base schema for file permission"""
    file_id: Optional[int] = None
    folder_id: Optional[int] = None
    user_id: Optional[int] = None
    group_id: Optional[int] = None
    can_view: bool = True
    can_edit: bool = False
    can_delete: bool = False
    can_share: bool = False


class FilePermissionCreate(FilePermissionBase):
    """Schema for creating a file permission"""
    pass


class FilePermissionUpdate(BaseModel):
    """Schema for updating a file permission"""
    can_view: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_share: Optional[bool] = None


class FilePermissionResponse(FilePermissionBase):
    """Response schema for a file permission"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class FilePermissionListResponse(BaseModel):
    """Response schema for list of file permissions"""
    total: int
    permissions: List[FilePermissionResponse]

    class Config:
        orm_mode = True


class FileUploadRequest(BaseModel):
    """Request schema for file upload"""
    filename: str
    content_type: str
    size: int
    course_id: Optional[int] = None
    assignment_id: Optional[int] = None
    submission_id: Optional[int] = None
    folder_id: Optional[int] = None


class FileUploadResponse(BaseModel):
    """Response schema for file upload"""
    file_id: int
    upload_url: str  # Presigned URL for direct upload
    expires_at: datetime


class FileDownloadResponse(BaseModel):
    """Response schema for file download"""
    download_url: str  # Presigned URL for download
    filename: str
    mime_type: str
    size: int
    expires_at: datetime