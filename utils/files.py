"""
File handling utilities
"""
import os
import io
import uuid
import hashlib
import mimetypes
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, BinaryIO, Tuple, Union

import aiofiles
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from core.config import settings
from .validators import validate_file_extension, validate_mime_type


async def save_upload_file(
    upload_file: UploadFile,
    directory: str,
    filename: Optional[str] = None,
    allowed_extensions: Optional[List[str]] = None,
    allowed_mime_types: Optional[List[str]] = None,
    max_size_bytes: Optional[int] = None
) -> Dict[str, Any]:
    """
    Save an uploaded file to the specified directory
    
    Args:
        upload_file: FastAPI UploadFile object
        directory: Directory to save the file to
        filename: Optional filename (will be generated if not provided)
        allowed_extensions: List of allowed file extensions
        allowed_mime_types: List of allowed MIME types
        max_size_bytes: Maximum allowed file size in bytes
        
    Returns:
        Dictionary with file information
        
    Raises:
        ValueError: If file validation fails
    """
    # Validate file extension
    if allowed_extensions and not validate_file_extension(upload_file.filename, allowed_extensions):
        raise ValueError(f"File extension not allowed. Allowed extensions: {', '.join(allowed_extensions)}")
    
    # Validate MIME type
    if allowed_mime_types and not validate_mime_type(upload_file.content_type, allowed_mime_types):
        raise ValueError(f"File type not allowed. Allowed types: {', '.join(allowed_mime_types)}")
    
    # Create the directory if it doesn't exist
    os.makedirs(directory, exist_ok=True)
    
    # Read file content
    contents = await upload_file.read()
    
    # Validate file size
    if max_size_bytes is not None and len(contents) > max_size_bytes:
        raise ValueError(f"File too large. Maximum size is {max_size_bytes} bytes")
    
    # Calculate file hashes
    md5_hash = hashlib.md5(contents).hexdigest()
    sha256_hash = hashlib.sha256(contents).hexdigest()
    
    # Generate filename if not provided
    if not filename:
        # Extract extension from original filename
        original_extension = os.path.splitext(upload_file.filename)[1].lower()
        # Generate unique filename with the original extension
        filename = f"{uuid.uuid4().hex}{original_extension}"
    
    # Full path to save the file
    filepath = os.path.join(directory, filename)
    
    # Save the file
    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(contents)
    
    # Reset file position for future reads
    await upload_file.seek(0)
    
    # Get file metadata
    file_info = {
        "filename": filename,
        "original_filename": upload_file.filename,
        "content_type": upload_file.content_type,
        "size": len(contents),
        "md5_hash": md5_hash,
        "sha256_hash": sha256_hash,
        "filepath": filepath,
        "uploaded_at": datetime.utcnow(),
    }
    
    # Try to get additional metadata for images
    if upload_file.content_type.startswith('image/'):
        try:
            with Image.open(io.BytesIO(contents)) as img:
                file_info["metadata"] = {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                }
        except UnidentifiedImageError:
            # Not a valid image file or format not recognized
            pass
    
    return file_info


async def get_file_info(filepath: str) -> Dict[str, Any]:
    """
    Get information about a file
    
    Args:
        filepath: Path to the file
        
    Returns:
        Dictionary with file information
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    
    filename = os.path.basename(filepath)
    
    # Read file content
    async with aiofiles.open(filepath, 'rb') as f:
        contents = await f.read()
    
    # Determine content type
    content_type, _ = mimetypes.guess_type(filepath)
    if content_type is None:
        content_type = 'application/octet-stream'
    
    # Calculate file hashes
    md5_hash = hashlib.md5(contents).hexdigest()
    sha256_hash = hashlib.sha256(contents).hexdigest()
    
    # Get file stats
    stats = os.stat(filepath)
    
    file_info = {
        "filename": filename,
        "content_type": content_type,
        "size": stats.st_size,
        "md5_hash": md5_hash,
        "sha256_hash": sha256_hash,
        "filepath": filepath,
        "created_at": datetime.fromtimestamp(stats.st_ctime),
        "modified_at": datetime.fromtimestamp(stats.st_mtime),
    }
    
    # Try to get additional metadata for images
    if content_type.startswith('image/'):
        try:
            with Image.open(io.BytesIO(contents)) as img:
                file_info["metadata"] = {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                }
        except UnidentifiedImageError:
            # Not a valid image file or format not recognized
            pass
    
    return file_info


async def delete_file(filepath: str) -> bool:
    """
    Delete a file
    
    Args:
        filepath: Path to the file
        
    Returns:
        True if the file was deleted, False otherwise
    """
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
            return True
    except Exception:
        pass
    
    return False


async def create_presigned_url(
    filepath: str,
    expiration_minutes: int = 60,
    file_type: Optional[str] = None
) -> str:
    """
    Create a presigned URL for file upload/download
    
    This is a mock implementation since the actual implementation depends on the storage backend
    For S3, you would use boto3's generate_presigned_url method
    
    Args:
        filepath: Storage path for the file
        expiration_minutes: URL expiration time in minutes
        file_type: File content type
        
    Returns:
        Presigned URL
    """
    # This is a mock implementation that just returns a dummy URL
    # In a real application, this would be replaced with actual presigned URL generation
    expiration = datetime.utcnow() + timedelta(minutes=expiration_minutes)
    expiration_str = expiration.strftime("%Y%m%d%H%M%S")
    
    # For local development, return a URL to a local endpoint
    if settings.STORAGE_TYPE == "local":
        if filepath.startswith("/"):
            filepath = filepath[1:]
        return f"{settings.SERVER_HOST}/api/v1/files/download/{filepath}?expires={expiration_str}"
    
    # For S3 storage, you would use boto3's generate_presigned_url method
    elif settings.STORAGE_TYPE == "s3":
        # Mock implementation
        return f"https://{settings.S3_BUCKET}.s3.amazonaws.com/{filepath}?expiration={expiration_str}"
    
    # For other storage types
    else:
        return f"{settings.SERVER_HOST}/api/v1/files/download/{filepath}?expires={expiration_str}"


def generate_thumbnail(
    image_data: bytes,
    width: int = 200,
    height: int = 200,
    format: str = "JPEG",
    quality: int = 85
) -> bytes:
    """
    Generate a thumbnail from image data
    
    Args:
        image_data: Original image data
        width: Thumbnail width
        height: Thumbnail height
        format: Output format (JPEG, PNG, etc.)
        quality: Output quality (1-100, JPEG only)
        
    Returns:
        Thumbnail image data
        
    Raises:
        ValueError: If the image data is invalid
    """
    try:
        with Image.open(io.BytesIO(image_data)) as img:
            # Create a thumbnail that fits within the specified dimensions
            img.thumbnail((width, height))
            
            # Convert to RGB if needed
            if img.mode != "RGB" and format == "JPEG":
                img = img.convert("RGB")
            
            # Save to bytes
            output = io.BytesIO()
            img.save(output, format=format, quality=quality)
            return output.getvalue()
    
    except Exception as e:
        raise ValueError(f"Failed to generate thumbnail: {str(e)}")


def detect_file_type(file_data: bytes) -> Optional[str]:
    """
    Detect file type from content
    
    Args:
        file_data: File data
        
    Returns:
        MIME type or None if detection failed
    """
    # Try to determine file type from content
    # This is a simple implementation that checks for common file signatures
    
    # Check for common image formats
    if file_data.startswith(b'\xFF\xD8\xFF'):
        return 'image/jpeg'
    elif file_data.startswith(b'\x89PNG\r\n\x1A\n'):
        return 'image/png'
    elif file_data.startswith(b'GIF87a') or file_data.startswith(b'GIF89a'):
        return 'image/gif'
    elif file_data.startswith(b'\x42\x4D'):
        return 'image/bmp'
    
    # Check for PDF
    elif file_data.startswith(b'%PDF'):
        return 'application/pdf'
    
    # Check for ZIP
    elif file_data.startswith(b'PK\x03\x04'):
        return 'application/zip'
    
    # Check for Office documents
    elif file_data.startswith(b'\x50\x4B\x03\x04\x14\x00\x06\x00'):
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'  # docx
    
    # Return generic binary if detection failed
    return 'application/octet-stream'