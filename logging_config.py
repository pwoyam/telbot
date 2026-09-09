"""
Structured logging configuration for production.

Features:
- JSON format for log aggregators (ELK, CloudWatch, etc.)
- Request ID tracking for distributed tracing
- Context-aware logging (user_id, chat_id, etc.)
- Different formatters for development vs production
"""
import contextvars
import logging
import logging.config
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

# contextvars are per-asyncio-task, so concurrent requests (e.g. two users
# messaging the bot at the same time) each keep their own request_id
# instead of clobbering a single shared global.
_request_id_var: contextvars.ContextVar = contextvars.ContextVar(
    "request_id", default=None
)


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add request ID if present
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        
        # Add user context if present
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'chat_id'):
            log_data['chat_id'] = record.chat_id
        if hasattr(record, 'username'):
            log_data['username'] = record.username
        
        # Add duration if present
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        
        # Add exception info
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add any extra fields
        for key in ['action', 'provider', 'status', 'error_type', 'usage_count']:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
        
        return json.dumps(log_data, ensure_ascii=False)


class DevFormatter(logging.Formatter):
    """Colorful formatter for development."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[41m',  # Red background
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, '')
        
        # Base format
        fmt = f"{color}[{record.levelname:8}]{self.RESET} "
        fmt += f"{record.name}: {record.getMessage()}"
        
        # Add context
        context = []
        if hasattr(record, 'user_id'):
            context.append(f"user={record.user_id}")
        if hasattr(record, 'request_id'):
            context.append(f"req={record.request_id[:8]}")
        if hasattr(record, 'duration_ms'):
            context.append(f"{record.duration_ms}ms")
        
        if context:
            fmt += f" ({', '.join(context)})"
        
        if record.exc_info:
            fmt += f"\n{self.formatException(record.exc_info)}"
        
        return fmt


class ContextFilter(logging.Filter):
    """Filter that adds a per-task request_id to all log records."""

    def set_request_id(self, request_id: str):
        _request_id_var.set(request_id)

    def generate_request_id(self) -> str:
        """Generate a new request ID, scoped to the current asyncio task."""
        request_id = str(uuid.uuid4())
        _request_id_var.set(request_id)
        return request_id

    def filter(self, record: logging.LogRecord) -> bool:
        current = _request_id_var.get()
        if current:
            record.request_id = current
        return True


# Global context filter
_context_filter = ContextFilter()


def setup_logging(structured: bool = False) -> None:
    """
    Setup logging configuration.
    
    Args:
        structured: Use JSON format for production. Use colorful format for dev.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler()
    
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = DevFormatter()
    
    handler.setFormatter(formatter)
    handler.addFilter(_context_filter)
    
    root_logger.addHandler(handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)
    logging.getLogger('anthropic').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)


def get_context_filter() -> ContextFilter:
    """Get the global context filter for setting request context."""
    return _context_filter


class ContextLogger:
    """
    Logger wrapper that automatically adds context to log records.
    
    Usage:
        logger = ContextLogger(__name__)
        logger.bind(user_id=123).info("Processing message", action="chat")
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._extra: Dict[str, Any] = {}
    
    def bind(self, **kwargs) -> 'ContextLogger':
        """Create a new logger with additional context."""
        new_logger = ContextLogger(self.logger.name)
        new_logger._extra = {**self._extra, **kwargs}
        return new_logger
    
    def _log(self, level: int, msg: str, *args, **kwargs):
        extra = kwargs.pop('extra', {})
        extra.update(self._extra)
        self.logger.log(level, msg, *args, extra=extra, **kwargs)
    
    def debug(self, msg: str, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        kwargs['exc_info'] = True
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        self._log(logging.CRITICAL, msg, *args, **kwargs)
