"""
Validation utility functions
"""
import re
from typing import Optional, List, Dict, Any, Union, Tuple

from fastapi import HTTPException
from pydantic import EmailStr, validator


def validate_email(email: str) -> bool:
    """
    Validate email format
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email is valid, False otherwise
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """
    Validate username format
    
    Args:
        username: Username to validate
        
    Returns:
        (True, None) if username is valid, (False, error_message) otherwise
    """
    # Check length
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    
    if len(username) > 50:
        return False, "Username must be at most 50 characters long"
    
    # Check format
    if not re.match(r"^[a-zA-Z0-9._-]+$", username):
        return False, "Username can only contain letters, numbers, periods, underscores, and hyphens"
    
    # Check if username starts with a letter
    if not username[0].isalpha():
        return False, "Username must start with a letter"
    
    return True, None


def validate_password(password: str) -> Tuple[bool, Optional[str]]:
    """
    Validate password strength
    
    Args:
        password: Password to validate
        
    Returns:
        (True, None) if password is valid, (False, error_message) otherwise
    """
    # Check length
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    # Check if password has at least one uppercase letter
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    # Check if password has at least one lowercase letter
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    # Check if password has at least one digit
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    
    # Check if password has at least one special character
    if not any(c in "!@#$%^&*()-_=+[]{}|;:'\",.<>/?`~" for c in password):
        return False, "Password must contain at least one special character"
    
    return True, None


def validate_url(url: str) -> bool:
    """
    Validate URL format
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL is valid, False otherwise
    """
    pattern = r"^(https?|ftp)://[^\s/$.?#].[^\s]*$"
    return bool(re.match(pattern, url))


def validate_file_extension(
    filename: str,
    allowed_extensions: List[str]
) -> bool:
    """
    Validate file extension
    
    Args:
        filename: Filename to validate
        allowed_extensions: List of allowed extensions (without dot)
        
    Returns:
        True if file extension is allowed, False otherwise
    """
    if "." not in filename:
        return False
    
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in (ext.lower() for ext in allowed_extensions)


def validate_mime_type(
    mime_type: str,
    allowed_mime_types: List[str]
) -> bool:
    """
    Validate MIME type
    
    Args:
        mime_type: MIME type to validate
        allowed_mime_types: List of allowed MIME types
        
    Returns:
        True if MIME type is allowed, False otherwise
    """
    return mime_type.lower() in (m.lower() for m in allowed_mime_types)


def validate_date_format(date_str: str, format_str: str = "%Y-%m-%d") -> bool:
    """
    Validate date format
    
    Args:
        date_str: Date string to validate
        format_str: Expected date format
        
    Returns:
        True if date string matches expected format, False otherwise
    """
    # TODO: Implement date format validation
    # This can be more complex depending on requirements
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", date_str))


def validate_phone_number(phone_number: str) -> bool:
    """
    Validate phone number format (simple validation, not country-specific)
    
    Args:
        phone_number: Phone number to validate
        
    Returns:
        True if phone number is valid, False otherwise
    """
    # Remove common phone number formatting characters
    stripped = re.sub(r"[\s\-\(\)\+]", "", phone_number)
    
    # Check if the result is a valid phone number (digits only, reasonable length)
    return stripped.isdigit() and 7 <= len(stripped) <= 15


def validate_required_fields(
    data: Dict[str, Any],
    required_fields: List[str]
) -> Tuple[bool, Optional[str]]:
    """
    Validate that required fields are present and not empty
    
    Args:
        data: Data dictionary
        required_fields: List of required field names
        
    Returns:
        (True, None) if all required fields are present and not empty,
        (False, error_message) otherwise
    """
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
        
        if data[field] is None or (isinstance(data[field], str) and not data[field].strip()):
            return False, f"Required field cannot be empty: {field}"
    
    return True, None


def validate_image_dimensions(
    width: int,
    height: int,
    min_width: Optional[int] = None,
    max_width: Optional[int] = None,
    min_height: Optional[int] = None,
    max_height: Optional[int] = None,
    min_aspect_ratio: Optional[float] = None,
    max_aspect_ratio: Optional[float] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate image dimensions
    
    Args:
        width: Image width
        height: Image height
        min_width: Minimum allowed width
        max_width: Maximum allowed width
        min_height: Minimum allowed height
        max_height: Maximum allowed height
        min_aspect_ratio: Minimum allowed aspect ratio (width/height)
        max_aspect_ratio: Maximum allowed aspect ratio (width/height)
        
    Returns:
        (True, None) if image dimensions are valid, (False, error_message) otherwise
    """
    if min_width is not None and width < min_width:
        return False, f"Image width is less than minimum allowed width ({width} < {min_width})"
    
    if max_width is not None and width > max_width:
        return False, f"Image width is greater than maximum allowed width ({width} > {max_width})"
    
    if min_height is not None and height < min_height:
        return False, f"Image height is less than minimum allowed height ({height} < {min_height})"
    
    if max_height is not None and height > max_height:
        return False, f"Image height is greater than maximum allowed height ({height} > {max_height})"
    
    if height > 0:  # Avoid division by zero
        aspect_ratio = width / height
        
        if min_aspect_ratio is not None and aspect_ratio < min_aspect_ratio:
            return False, f"Image aspect ratio is less than minimum allowed aspect ratio ({aspect_ratio:.2f} < {min_aspect_ratio:.2f})"
        
        if max_aspect_ratio is not None and aspect_ratio > max_aspect_ratio:
            return False, f"Image aspect ratio is greater than maximum allowed aspect ratio ({aspect_ratio:.2f} > {max_aspect_ratio:.2f})"
    
    return True, None


def validate_enum_value(value: Any, enum_class: Any) -> bool:
    """
    Validate that a value is a valid enum value
    
    Args:
        value: Value to validate
        enum_class: Enum class to check against
        
    Returns:
        True if value is a valid enum value, False otherwise
    """
    try:
        return value in enum_class.__members__.values()
    except (AttributeError, TypeError):
        return False


def validate_and_raise(condition: bool, status_code: int, message: str) -> None:
    """
    Validate a condition and raise HTTPException if it's not met
    
    Args:
        condition: Condition to validate
        status_code: HTTP status code for the exception
        message: Error message for the exception
        
    Raises:
        HTTPException: If condition is not met
    """
    if not condition:
        raise HTTPException(status_code=status_code, detail=message)