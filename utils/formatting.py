"""
Formatting utility functions
"""
import re
import html
from datetime import datetime, date, time
from typing import Union, Optional, Any, Dict, List

import bleach
import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension


def format_date(
    date_obj: Union[datetime, date],
    format_str: str = "%Y-%m-%d"
) -> str:
    """
    Format a date object to string
    
    Args:
        date_obj: Date or datetime object
        format_str: Format string
        
    Returns:
        Formatted date string
    """
    if isinstance(date_obj, datetime):
        return date_obj.strftime(format_str)
    elif isinstance(date_obj, date):
        return date_obj.strftime(format_str)
    return str(date_obj)


def format_time(
    time_obj: Union[datetime, time],
    format_str: str = "%H:%M:%S",
    show_seconds: bool = True
) -> str:
    """
    Format a time object to string
    
    Args:
        time_obj: Time or datetime object
        format_str: Format string
        show_seconds: Whether to include seconds
        
    Returns:
        Formatted time string
    """
    if not show_seconds:
        format_str = format_str.replace(":%S", "")
    
    if isinstance(time_obj, datetime):
        return time_obj.strftime(format_str)
    elif isinstance(time_obj, time):
        return time_obj.strftime(format_str)
    return str(time_obj)


def format_datetime(
    dt: Union[datetime, date],
    format_str: str = "%Y-%m-%d %H:%M:%S",
    timezone: Optional[str] = None
) -> str:
    """
    Format a datetime object to string
    
    Args:
        dt: Datetime object
        format_str: Format string
        timezone: Timezone name (not implemented yet)
        
    Returns:
        Formatted datetime string
    """
    if isinstance(dt, datetime):
        # TODO: Implement timezone conversion if needed
        return dt.strftime(format_str)
    elif isinstance(dt, date):
        # For date objects, use only the date part of the format
        date_format = format_str.split()[0] if " " in format_str else format_str
        return dt.strftime(date_format)
    return str(dt)


def format_number(
    number: Union[int, float],
    decimal_places: int = 2,
    show_thousands_separator: bool = True
) -> str:
    """
    Format a number
    
    Args:
        number: Number to format
        decimal_places: Number of decimal places for floats
        show_thousands_separator: Whether to show thousands separator
        
    Returns:
        Formatted number string
    """
    if isinstance(number, int):
        if show_thousands_separator:
            return f"{number:,}"
        return str(number)
    elif isinstance(number, float):
        if show_thousands_separator:
            return f"{number:,.{decimal_places}f}"
        return f"{number:.{decimal_places}f}"
    return str(number)


def format_percentage(
    value: Union[int, float],
    decimal_places: int = 1,
    include_symbol: bool = True
) -> str:
    """
    Format a number as percentage
    
    Args:
        value: Number to format (0.5 = 50%)
        decimal_places: Number of decimal places
        include_symbol: Whether to include the % symbol
        
    Returns:
        Formatted percentage string
    """
    # Convert to percentage (multiply by 100)
    percentage = value * 100
    formatted = f"{percentage:.{decimal_places}f}"
    
    # Remove trailing zeros after decimal point
    if decimal_places > 0 and "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    
    # Add percentage symbol if requested
    if include_symbol:
        formatted += "%"
    
    return formatted


def format_filesize(
    size_bytes: int,
    binary: bool = True
) -> str:
    """
    Format a filesize
    
    Args:
        size_bytes: Size in bytes
        binary: Whether to use binary (1024) or decimal (1000) units
        
    Returns:
        Formatted filesize string
    """
    if binary:
        base = 1024
        suffixes = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"]
    else:
        base = 1000
        suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    
    # Handle special case for 0 bytes
    if size_bytes == 0:
        return f"0 {suffixes[0]}"
    
    # Calculate the appropriate suffix
    magnitude = int((len(str(size_bytes)) - 1) / 3)
    if magnitude > 8:
        magnitude = 8
    
    # Calculate the value
    value = size_bytes / (base ** magnitude)
    
    # Format the value
    if value < 10:
        formatted_value = f"{value:.2f}"
    elif value < 100:
        formatted_value = f"{value:.1f}"
    else:
        formatted_value = f"{int(value)}"
    
    # Return the formatted string
    return f"{formatted_value} {suffixes[magnitude]}"


def truncate_text(
    text: str,
    max_length: int = 100,
    suffix: str = "...",
    preserve_words: bool = True
) -> str:
    """
    Truncate text to a maximum length
    
    Args:
        text: Text to truncate
        max_length: Maximum length of the resulting text
        suffix: String to append if text is truncated
        preserve_words: Whether to preserve whole words
        
    Returns:
        Truncated text
    """
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    if preserve_words:
        # Truncate to the last space before max_length
        truncated = text[:max_length].rsplit(' ', 1)[0]
    else:
        # Simple truncation
        truncated = text[:max_length - len(suffix)]
    
    return truncated + suffix


def markdown_to_html(
    markdown_text: str,
    safe: bool = True,
    strip: bool = False,
    allowed_tags: Optional[List[str]] = None,
    allowed_attrs: Optional[Dict[str, List[str]]] = None
) -> str:
    """
    Convert markdown to HTML
    
    Args:
        markdown_text: Markdown text to convert
        safe: Whether to sanitize the output HTML
        strip: Whether to strip all HTML tags
        allowed_tags: List of allowed HTML tags
        allowed_attrs: Dictionary of allowed HTML attributes per tag
        
    Returns:
        HTML string
    """
    # Set default allowed tags and attributes if not provided
    if allowed_tags is None:
        allowed_tags = bleach.sanitizer.ALLOWED_TAGS + [
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img', 'hr', 'br',
            'pre', 'code', 'div', 'span', 'table', 'thead', 'tbody',
            'tr', 'th', 'td', 'dl', 'dt', 'dd', 'blockquote', 'sup', 'sub'
        ]
    
    if allowed_attrs is None:
        allowed_attrs = dict(bleach.sanitizer.ALLOWED_ATTRIBUTES)
        allowed_attrs.update({
            'img': ['src', 'alt', 'title', 'width', 'height', 'class'],
            'a': ['href', 'alt', 'title', 'rel', 'target', 'class'],
            'th': ['scope', 'class'],
            'td': ['class'],
            'div': ['class'],
            'span': ['class'],
            'code': ['class'],
            'pre': ['class']
        })
    
    # Configure Markdown extensions
    extensions = [
        'markdown.extensions.smarty',
        'markdown.extensions.tables',
        FencedCodeExtension(),
        CodeHiliteExtension(css_class='highlight'),
        TableExtension()
    ]
    
    # Convert Markdown to HTML
    html_text = markdown.markdown(markdown_text, extensions=extensions)
    
    # Sanitize HTML if required
    if safe:
        if strip:
            # Strip all HTML tags
            return bleach.clean(html_text, tags=[], strip=True)
        else:
            # Clean HTML with allowed tags and attributes
            return bleach.clean(html_text, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    
    return html_text


def strip_html(html_text: str) -> str:
    """
    Strip all HTML tags from text
    
    Args:
        html_text: HTML text to strip
        
    Returns:
        Text without HTML tags
    """
    return bleach.clean(html_text, tags=[], strip=True)


def slugify(text: str) -> str:
    """
    Convert text to slug (lowercase, replace spaces with hyphens, remove non-alphanumeric)
    
    Args:
        text: Text to convert
        
    Returns:
        Slug string
    """
    # Convert to lowercase
    text = text.lower()
    
    # Replace spaces with hyphens
    text = re.sub(r'\s+', '-', text)
    
    # Remove non-alphanumeric characters (except hyphens)
    text = re.sub(r'[^a-z0-9\-]', '', text)
    
    # Remove consecutive hyphens
    text = re.sub(r'-+', '-', text)
    
    # Remove leading/trailing hyphens
    text = text.strip('-')
    
    return text


def html_to_text(html_text: str) -> str:
    """
    Convert HTML to plain text
    
    Args:
        html_text: HTML text to convert
        
    Returns:
        Plain text
    """
    # Remove all HTML tags
    text = strip_html(html_text)
    
    # Decode HTML entities
    text = html.unescape(text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def format_duration(seconds: int) -> str:
    """
    Format a duration in seconds to a human-readable string
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string (e.g. "2h 30m")
    """
    if seconds < 60:
        # Less than a minute
        return f"{seconds}s"
    
    minutes, seconds = divmod(seconds, 60)
    
    if minutes < 60:
        # Less than an hour
        if seconds == 0:
            return f"{minutes}m"
        return f"{minutes}m {seconds}s"
    
    hours, minutes = divmod(minutes, 60)
    
    if hours < 24:
        # Less than a day
        if minutes == 0:
            return f"{hours}h"
        return f"{hours}h {minutes}m"
    
    days, hours = divmod(hours, 24)
    
    if hours == 0:
        return f"{days}d"
    return f"{days}d {hours}h"