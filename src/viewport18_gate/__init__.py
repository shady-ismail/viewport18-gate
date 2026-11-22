"""viewport18-gate: 18-width responsive layout and DOM containment verifier."""

from .audit import (
    DEFAULT_CONTAINER_SELECTORS,
    DEFAULT_GRID_SELECTORS,
    GateConfig,
    evaluate_viewport_audit,
    format_junit_xml,
    is_external_request,
    run_gate,
    sanitize_selector_slug,
    validate_out_dir,
)
from .browser import find_chromium_exec, start_local_server, validate_http_target
from .viewports import SHOT_VIEWPORTS, VIEWPORT_SPECS, VIEWPORTS, ViewportSpec

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_CONTAINER_SELECTORS",
    "DEFAULT_GRID_SELECTORS",
    "GateConfig",
    "SHOT_VIEWPORTS",
    "VIEWPORTS",
    "VIEWPORT_SPECS",
    "ViewportSpec",
    "__version__",
    "evaluate_viewport_audit",
    "find_chromium_exec",
    "format_junit_xml",
    "is_external_request",
    "run_gate",
    "sanitize_selector_slug",
    "start_local_server",
    "validate_http_target",
    "validate_out_dir",
]
