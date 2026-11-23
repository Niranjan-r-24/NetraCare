import os
import logging
from functools import wraps
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger("netracare.telemetry")

_OPIK_AVAILABLE = False
try:
    import opik
    from opik import track as _opik_track
    from opik.integrations.langchain import OpikTracer
    from opik import opik_context
    _OPIK_AVAILABLE = True
except Exception as e:
    logger.debug(f"Opik library not available or failed to import: {e}")
    _OPIK_AVAILABLE = False
    _opik_track = None
    OpikTracer = None
    opik_context = None


def is_opik_enabled() -> bool:
    """
    Returns True only if opik is installed and an API key or explicit enable flag is present.
    If OPIK_API_KEY is missing or OPIK_ENABLED is 'false'/'0', returns False.
    """
    if not _OPIK_AVAILABLE:
        return False
    
    explicit_flag = os.environ.get("OPIK_ENABLED", "").lower().strip()
    if explicit_flag in ("0", "false", "no", "off"):
        return False

    api_key = os.environ.get("OPIK_API_KEY", "").strip()
    url_override = os.environ.get("OPIK_URL_OVERRIDE", "").strip()
    # Active if either API key or local URL override is configured
    return bool(api_key or url_override)


def get_opik_project(default: str = "netracare-dev") -> str:
    """Returns the active Opik project name, allowing override via OPIK_PROJECT_NAME env var."""
    return os.environ.get("OPIK_PROJECT_NAME", default).strip() or default


def get_opik_tracer(
    project_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Any]:
    """
    Returns an OpikTracer instance for LangChain callbacks if Opik is active.
    Returns None if Opik is inactive or if initialization fails.
    """
    if not is_opik_enabled() or OpikTracer is None:
        return None

    proj = project_name or get_opik_project()
    try:
        return OpikTracer(
            project_name=proj,
            tags=tags or [],
            metadata=metadata or {}
        )
    except Exception as e:
        logger.warning(f"Failed to initialize OpikTracer: {e}. Falling back to untraced mode.")
        return None


def track(
    name: Optional[str] = None,
    type: str = "general",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    project_name: Optional[str] = None,
    capture_input: bool = True,
    capture_output: bool = True
) -> Callable:
    """
    Decorator that tracks a function call in Opik when enabled,
    or behaves as a transparent pass-through when disabled or if an error occurs.
    """
    def decorator(func: Callable) -> Callable:
        if not is_opik_enabled() or _opik_track is None:
            @wraps(func)
            def passthrough_wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return passthrough_wrapper

        proj = project_name or get_opik_project()
        try:
            opik_decorated = _opik_track(
                name=name or func.__name__,
                type=type,
                tags=tags or [],
                metadata=metadata or {},
                project_name=proj,
                capture_input=capture_input,
                capture_output=capture_output
            )(func)

            @wraps(func)
            def safe_opik_wrapper(*args, **kwargs):
                try:
                    return opik_decorated(*args, **kwargs)
                except Exception as ex:
                    # If Opik tracing fails during call (e.g. network/auth error), run raw func
                    logger.warning(f"Opik tracking error in {func.__name__}: {ex}. Executing untraced.")
                    return func(*args, **kwargs)

            return safe_opik_wrapper
        except Exception as e:
            logger.warning(f"Failed to decorate {func.__name__} with Opik: {e}. Using passthrough.")
            @wraps(func)
            def fallback_wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return fallback_wrapper

    return decorator


def update_trace_context(
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    feedback_score: Optional[Dict[str, Any]] = None
) -> None:
    """Safely updates active Opik trace/span metadata and tags if active."""
    if not is_opik_enabled() or opik_context is None:
        return
    try:
        if tags:
            opik_context.update_current_trace(tags=tags)
        if metadata:
            opik_context.update_current_trace(metadata=metadata)
        if feedback_score:
            opik_context.update_current_trace(feedback_scores=[feedback_score])
    except Exception as e:
        logger.debug(f"Could not update Opik trace context: {e}")
