"""Application logging without request contents or provider credentials."""

import logging
from functools import wraps
from hashlib import sha256
from inspect import signature
from time import perf_counter


def configure_logging() -> None:
    """Use Uvicorn's configured level and handlers for application events."""
    server = logging.getLogger("uvicorn")
    application = logging.getLogger("intellinotes")
    application.setLevel(logging.getLogger("uvicorn.error").getEffectiveLevel())
    application.handlers = list(server.handlers) or [logging.StreamHandler()]
    application.propagate = False


def log_operation(operation: str):
    """Log async operation boundaries using only safe metadata."""
    def decorate(function):
        logger = logging.getLogger("intellinotes." + function.__module__)
        parameters = signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            metadata = {}
            if logger.isEnabledFor(logging.DEBUG):
                values = parameters.bind(*args, **kwargs).arguments
                for name in ("user_id", "proposal_id", "note_id"):
                    if values.get(name) is not None:
                        metadata[name] = str(values[name])
                for name in ("snippet", "context", "feedback", "content"):
                    if values.get(name) is not None:
                        metadata[name + "_length"] = len(values[name])
                if "key" in values:
                    # Keys contain note titles; log an identifier rather than the filename.
                    metadata["key_hash"] = sha256(values["key"].encode()).hexdigest()[:12]
                owner = values.get("self")
                if owner is not None:
                    metadata["adapter"] = type(owner).__name__
                logger.debug("%s started metadata=%s", operation, metadata)
            started = perf_counter()
            try:
                result = await function(*args, **kwargs)
            except Exception as error:
                logger.debug(
                    "%s failed duration_ms=%.1f error_type=%s metadata=%s",
                    operation, (perf_counter() - started) * 1000,
                    type(error).__name__, metadata,
                )
                raise
            logger.debug(
                "%s completed duration_ms=%.1f metadata=%s",
                operation, (perf_counter() - started) * 1000, metadata,
            )
            return result

        return wrapped
    return decorate
