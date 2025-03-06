"""
Logging utilities for the application
"""
import logging
import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional

from core.config import settings


class JsonFormatter(logging.Formatter):
    """
    Formatter for JSON-structured logs
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, "extra"):
            log_record.update(record.extra)
        
        return json.dumps(log_record)


def setup_logging(
    log_level: str = None,
    log_file: str = None,
    json_format: bool = False
) -> None:
    """
    Set up logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file
        json_format: Whether to use JSON format for logs
    """
    # Determine log level
    if log_level is None:
        log_level = "DEBUG" if settings.DEBUG else "INFO"
    
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    
    # Create logs directory if it doesn't exist
    if log_file and not os.path.exists(os.path.dirname(log_file)):
        os.makedirs(os.path.dirname(log_file))
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create handlers
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    handlers.append(console_handler)
    
    # File handler if log_file is specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)
    
    # Set formatter
    if json_format:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Add handlers to root logger
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    
    # Set logs for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("tortoise").setLevel(logging.WARNING)
    
    # Log startup message
    logging.info(f"Logging configured. Level: {log_level}, JSON: {json_format}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter for adding context to log messages
    """
    def process(self, msg, kwargs):
        # Add extra context to all log records
        kwargs.setdefault('extra', {}).update(self.extra)
        return msg, kwargs


def get_context_logger(name: str, context: Dict[str, Any]) -> logging.LoggerAdapter:
    """
    Get a logger with context data
    
    Args:
        name: Logger name
        context: Context data to add to all log messages
        
    Returns:
        LoggerAdapter instance
    """
    logger = get_logger(name)
    return LoggerAdapter(logger, {'extra': context})


def log_request(request_data: Dict[str, Any], user_id: Optional[int] = None) -> None:
    """
    Log API request data
    
    Args:
        request_data: Request data to log
        user_id: ID of the user making the request
    """
    logger = get_logger("api.request")
    extra = {"request": request_data}
    
    if user_id:
        extra["user_id"] = user_id
    
    logger.info(f"API request", extra=extra)


def log_response(
    status_code: int,
    response_data: Dict[str, Any],
    request_time_ms: int,
    user_id: Optional[int] = None
) -> None:
    """
    Log API response data
    
    Args:
        status_code: HTTP status code
        response_data: Response data to log
        request_time_ms: Request processing time in milliseconds
        user_id: ID of the user making the request
    """
    logger = get_logger("api.response")
    extra = {
        "status_code": status_code,
        "response": response_data,
        "request_time_ms": request_time_ms
    }
    
    if user_id:
        extra["user_id"] = user_id
    
    logger.info(f"API response - Status: {status_code}, Time: {request_time_ms}ms", extra=extra)