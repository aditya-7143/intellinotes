"""Structured application events with request correlation and safe metadata."""

import asyncio
import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from hashlib import sha256
from inspect import iscoroutinefunction, signature
from time import perf_counter
from uuid import uuid4

request_id: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "request_id": request_id.get(),
                "message": record.getMessage(),
            }
        )


def configure_logging() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    application = logging.getLogger("intellinotes")
    level = settings.LOG_LEVEL or ("DEBUG" if settings.DEBUG else "INFO")
    application.setLevel(level)
    # Own one handler; repeated app creation must not duplicate output.
    if not application.handlers:
        application.addHandler(logging.StreamHandler())
    for handler in application.handlers:
        handler.setFormatter(JsonFormatter())
    application.propagate = False


def log_operation(operation: str):
    """Instrument sync/async boundaries; never log raw arguments or results."""

    def decorate(function):
        logger = logging.getLogger("intellinotes." + function.__module__)
        parameters = signature(function)

        def start(args, kwargs):
            metadata = {}
            if logger.isEnabledFor(logging.DEBUG):
                values = parameters.bind(*args, **kwargs).arguments
                for name in ("user_id", "proposal_id", "note_id"):
                    if values.get(name) is not None:
                        metadata[name] = str(values[name])
                for name in ("snippet", "context", "feedback", "content", "query"):
                    if isinstance(values.get(name), str | bytes):
                        metadata[name + "_length"] = len(values[name])
                for name in ("key", "path", "destination", "folder_path", "prefix"):
                    if isinstance(values.get(name), str):
                        metadata[name + "_hash"] = sha256(values[name].encode()).hexdigest()[:12]
                if isinstance(values.get("texts"), list):
                    metadata["batch_size"] = len(values["texts"])
                    metadata["text_characters"] = sum(len(text) for text in values["texts"])
                owner = values.get("self")
                if owner is not None:
                    metadata["adapter"] = type(owner).__name__
                logger.debug("%s started metadata=%s", operation, metadata)
            return perf_counter(), metadata

        def finish(started, metadata, result=None, error=None):
            duration = (perf_counter() - started) * 1000
            if error is not None:
                logger.debug(
                    "%s failed duration_ms=%.1f error_type=%s metadata=%s",
                    operation,
                    duration,
                    type(error).__name__,
                    metadata,
                )
            else:
                count = len(result) if isinstance(result, list | tuple) else None
                logger.debug(
                    "%s completed duration_ms=%.1f result_count=%s metadata=%s",
                    operation,
                    duration,
                    count,
                    metadata,
                )

        if iscoroutinefunction(function):

            @wraps(function)
            async def async_wrapped(*args, **kwargs):
                started, metadata = start(args, kwargs)
                try:
                    result = await function(*args, **kwargs)
                except (Exception, asyncio.CancelledError) as error:
                    finish(started, metadata, error=error)
                    raise
                finish(started, metadata, result=result)
                return result

            return async_wrapped

        @wraps(function)
        def sync_wrapped(*args, **kwargs):
            started, metadata = start(args, kwargs)
            try:
                result = function(*args, **kwargs)
            except Exception as error:
                finish(started, metadata, error=error)
                raise
            finish(started, metadata, result=result)
            return result

        return sync_wrapped

    return decorate


class RequestLoggingMiddleware:
    """ASGI middleware: log route templates, never raw paths/query strings/bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        identifier = uuid4().hex
        token = request_id.set(identifier)
        started = perf_counter()
        status = 500
        logger = logging.getLogger("intellinotes.http")

        async def send_response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = dict(message)
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ] + [(b"x-request-id", identifier.encode())]
            await send(message)

        try:
            logger.debug("request started method=%s", scope.get("method"))
            await self.app(scope, receive, send_response)
        except (Exception, asyncio.CancelledError) as error:
            logger.debug("request failed error_type=%s", type(error).__name__)
            raise
        finally:
            route = getattr(scope.get("route"), "path", "<unmatched>")
            logger.debug(
                "request completed method=%s route=%s status=%s duration_ms=%.1f",
                scope.get("method"),
                route,
                status,
                (perf_counter() - started) * 1000,
            )
            request_id.reset(token)
