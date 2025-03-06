from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class FileType(str, Enum):
    DOCUMENT = "document"  # Text documents, PDFs, etc.
    IMAGE = "image"  # Image files
    VIDEO = "video"  # Video files
    AUDIO = "audio"  # Audio files
    ARCHIVE = "archive"  # Archive files (zip, tar, etc.)
    SPREADSHEET = "spreadsheet"  # Spreadsheet files
    PRESENTATION = "presentation"  # Presentation files
    SOURCE_CODE = "source_code"  # Source code files
    OTHER = "other"  # Other file types


class FileStatus(str, Enum):
    PENDING = "pending"  # File is being processed
    AVAILABLE = "available"  # File is available for use
    PROCESSING = "processing"  # File is being processed (e.g., video encoding)
    ERROR = "error"  # Error occurred during processing
    DELETED = "deleted"  # File has been deleted (soft delete)


class StorageProvider(str, Enum):
    LOCAL = "local"  # Local file storage
    S3 = "s3"  # Amazon S3
    AZURE = "azure"  # Azure Blob Storage
    GCP = "gcp"  # Google Cloud Storage
    OTHER = "other"  # Other storage providers


class File(models.Model):
    """
    File model for storing metadata about uploaded files
    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)

    # File metadata
    file_type = fields.CharEnumField(FileType, default=FileType.OTHER)
    mime_type = fields.CharField(max_length=255)
    size = fields.BigIntField()  # Size in bytes

    # Storage information
    storage_provider = fields.CharEnumField(StorageProvider, default=StorageProvider.LOCAL)
    storage_path = fields.CharField(max_length=1024)  # Path or key in the storage system
    public_url = fields.CharField(max_length=2048, null=True)  # Public URL if available

    # File status
    status = fields.CharEnumField(FileStatus, default=FileStatus.PENDING)

    # Original filename before processing
    original_filename = fields.CharField(max_length=255)

    # For security and content verification
    md5_hash = fields.CharField(max_length=32, null=True)
    sha256_hash = fields.CharField(max_length=64, null=True)

    # Extra file metadata (could include dimensions for images, duration for videos, etc.)
    metadata = fields.JSONField(null=True)

    # Uploader
    uploaded_by = fields.ForeignKeyField("models.User", related_name="uploaded_files")

    # File usage tracking
    download_count = fields.IntField(default=0)

    # For expiring files
    expires_at = fields.DatetimeField(null=True)

    # For access control
    is_public = fields.BooleanField(default=False)

    # Relationships - can be associated with various entities
    course = fields.ForeignKeyField("models.Course", related_name="files", null=True)
    assignment = fields.ForeignKeyField("models.Assignment", related_name="files", null=True)
    submission = fields.ForeignKeyField("models.Submission", related_name="files", null=True)

    # Timestamps
    uploaded_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "files"

    def __str__(self):
        return f"{self.name} ({self.file_type})"


class Folder(models.Model):
    """
    Folder model for organizing files in a hierarchical structure
    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)

    # Hierarchical structure
    parent = fields.ForeignKeyField("models.Folder", related_name="children", null=True)

    # Relationships - can be associated with various entities
    course = fields.ForeignKeyField("models.Course", related_name="folders", null=True)
    user = fields.ForeignKeyField("models.User", related_name="folders", null=True)

    # Path for efficient retrieval
    path = fields.CharField(max_length=1024)  # e.g., "/course/123/module/456/"

    # For sorting
    position = fields.IntField(default=0)

    # For access control
    is_public = fields.BooleanField(default=False)

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "folders"
        unique_together = (("name", "parent", "course", "user"),)

    def __str__(self):
        return f"{self.name} ({self.path})"


class FileFolder(models.Model):
    """
    Many-to-many relationship between files and folders
    A file can exist in multiple folders
    """

    id = fields.IntField(pk=True)

    # Relationships
    file = fields.ForeignKeyField("models.File", related_name="folder_links")
    folder = fields.ForeignKeyField("models.Folder", related_name="file_links")

    # For sorting
    position = fields.IntField(default=0)

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "file_folders"
        unique_together = (("file", "folder"),)

    def __str__(self):
        return f"{self.file.name} in {self.folder.name}"


class FileVersion(models.Model):
    """
    Track versions of a file over time
    """

    id = fields.IntField(pk=True)

    # Relationships
    file = fields.ForeignKeyField("models.File", related_name="versions")

    # Version metadata
    version_number = fields.IntField()
    storage_path = fields.CharField(max_length=1024)  # Path or key in the storage system
    size = fields.BigIntField()  # Size in bytes

    # For security and content verification
    md5_hash = fields.CharField(max_length=32, null=True)

    # Version comment
    comment = fields.TextField(null=True)

    # Uploader
    created_by = fields.ForeignKeyField("models.User", related_name="file_versions")

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "file_versions"
        unique_together = (("file", "version_number"),)

    def __str__(self):
        return f"{self.file.name} v{self.version_number}"


class FilePermission(models.Model):
    """
    Fine-grained permissions for files
    """

    id = fields.IntField(pk=True)

    # Target file or folder
    file = fields.ForeignKeyField("models.File", related_name="permissions", null=True)
    folder = fields.ForeignKeyField("models.Folder", related_name="permissions", null=True)

    # Entity that has permission
    user = fields.ForeignKeyField("models.User", related_name="file_permissions", null=True)
    group = fields.ForeignKeyField("models.Group", related_name="file_permissions", null=True)

    # Permission level
    can_view = fields.BooleanField(default=True)
    can_edit = fields.BooleanField(default=False)
    can_delete = fields.BooleanField(default=False)
    can_share = fields.BooleanField(default=False)

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "file_permissions"

    def __str__(self):
        target = self.file.name if self.file else self.folder.name
        entity = self.user.username if self.user else self.group.name
        return f"Permission for {entity} on {target}"


class FileUsage(models.Model):
    """
    Track where and how files are used
    """

    id = fields.IntField(pk=True)

    # Relationships
    file = fields.ForeignKeyField("models.File", related_name="usages")

    # Usage context
    context_type = fields.CharField(max_length=50)  # e.g., "assignment", "course", "submission"
    context_id = fields.IntField()  # ID of the related entity

    # Usage details
    usage_type = fields.CharField(max_length=50)  # e.g., "attachment", "inline", "reference"

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "file_usages"

    def __str__(self):
        return f"{self.file.name} used in {self.context_type} {self.context_id}"


# Pydantic models for validation and serialization
File_Pydantic = pydantic_model_creator(File, name="File")
FileCreate_Pydantic = pydantic_model_creator(
    File, name="FileCreate", exclude=("id", "uploaded_at", "updated_at", "download_count")
)

Folder_Pydantic = pydantic_model_creator(Folder, name="Folder")
FolderCreate_Pydantic = pydantic_model_creator(
    Folder, name="FolderCreate", exclude=("id", "created_at", "updated_at")
)

FileVersion_Pydantic = pydantic_model_creator(FileVersion, name="FileVersion")
FilePermission_Pydantic = pydantic_model_creator(FilePermission, name="FilePermission")