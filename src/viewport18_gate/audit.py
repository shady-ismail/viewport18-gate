"""Core 18-viewport geometric, containment, runtime error, and egress auditor."""

from __future__ import annotations

import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .browser import find_chromium_exec, start_local_server, validate_http_target
from .viewports import SHOT_VIEWPORTS, VIEWPORTS

DEFAULT_CONTAINER_SELECTORS: tuple[str, ...] = (
    ".card",
    ".panel",
    ".box",
    ".surface-card",
    ".video-frame-card",
    ".sandbox-toolbar",
    ".pane-card",
    ".metric-tile",
    "tr",
)

DEFAULT_GRID_SELECTORS: tuple[str, ...] = (
    ".two-col-grid",
    ".split-grid",
    ".hero-grid",
    ".video-grid",
    ".workbench-grid",
)

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_URL_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")
_MAX_AUDIT_ERRORS = 200
_MAX_SCAN_NODES = 6000


@dataclass(frozen=True)
class GateConfig:
    """Configuration for an 18-viewport audit run."""

    target: str
    out_dir: Path
    max_mobile_td_height: int = 260
    require_zero_external: bool = False
    allow_private_network: bool = False
    selectors: tuple[str, ...] = field(default_factory=tuple)
    container_selectors: tuple[str, ...] = DEFAULT_CONTAINER_SELECTORS
    grid_selectors: tuple[str, ...] = DEFAULT_GRID_SELECTORS
    chromium_path: str | None = None
    navigation_timeout_ms: int = 25_000
    settle_ms: int = 600
    viewport_settle_ms: int = 120


def sanitize_selector_slug(selector: str) -> str:
    """Turn a CSS selector into a deterministic, traversal-safe filename stem."""
    stripped = selector.lstrip("#.").strip()
    slug = _SAFE_FILENAME_RE.sub("_", stripped).strip("._-")
    return (slug or "section")[:64]


def validate_out_dir(out_dir: Path) -> Path:
    """Validate and create ``out_dir``, rejecting symlink or regular-file targets."""
    if "\x00" in str(out_dir):
        raise ValueError("Output directory path contains null byte")
    if out_dir.is_symlink():
        raise ValueError(f"Output directory must not be a symlink: {out_dir}")
    resolved = out_dir.resolve()
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"Output path exists and is not a directory: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def is_external_request(request_url: str, origin_prefix: str) -> bool:
    """Return True if ``request_url`` is HTTP(S) and differs in scheme/netloc from ``origin_prefix``."""
    parsed_req = urllib.parse.urlsplit(request_url)
    if parsed_req.scheme.lower() not in ("http", "https"):
        return False
    parsed_origin = urllib.parse.urlsplit(origin_prefix)
    return (parsed_req.scheme.lower(), parsed_req.netloc.lower()) != (
        parsed_origin.scheme.lower(),
        parsed_origin.netloc.lower(),
    )


def evaluate_viewport_audit(
    audit: dict[str, Any],
    *,
    width: int,
    max_mobile_td_height: int,
    require_zero_external: bool,
) -> bool:
    """Determine pass/fail for a single viewport audit dictionary."""
    grid_diffs = audit.get("gridDiffs", [])
    max_grid_diff = max((int(g.get("diff", 0)) for g in grid_diffs), default=0)
    mobile_td_ok = (width > 768) or (int(audit.get("maxTdH", 0)) <= max_mobile_td_height)
    ext_ok = (not require_zero_external) or (len(audit.get("extReqs", [])) == 0)
    return (
        not bool(audit.get("horizOverflow"))
        and int(audit.get("viewportOverflowCount", 0)) == 0
        and int(audit.get("parentOverflowCount", 0)) == 0
        and len(audit.get("jsErrors", [])) == 0
        and max_grid_diff <= 2
        and mobile_td_ok
        and ext_ok
    )


def _build_dom_audit_js(container_selectors: tuple[str, ...], grid_selectors: tuple[str, ...]) -> str:
    container_csv = json.dumps(", ".join(container_selectors))
    grid_array = json.dumps(list(grid_selectors))
    return f"""() => {{
        const vw = window.innerWidth;
        const docEl = document.documentElement;
        const docClientW = docEl ? docEl.clientWidth : vw;
        const docScrollW = docEl ? docEl.scrollWidth : vw;
        const bodyScrollW = document.body ? document.body.scrollWidth : docScrollW;
        const dirAttr = (docEl && docEl.getAttribute("dir")) || (docEl ? getComputedStyle(docEl).direction : "ltr");

        const skipTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "LINK", "META", "TITLE", "HEAD"]);
        const collected = [];
        const stack = [];
        if (document.body) {{
            stack.push(document.body);
        }}
        while (stack.length > 0 && collected.length < {_MAX_SCAN_NODES}) {{
            const node = stack.pop();
            if (!node || node.nodeType !== 1) continue;
            if (skipTags.has(node.tagName)) continue;
            collected.push(node);
            if (node.shadowRoot) {{
                const srChildren = node.shadowRoot.children;
                for (let i = srChildren.length - 1; i >= 0; i--) {{
                    stack.push(srChildren[i]);
                }}
            }}
            const children = node.children;
            for (let i = children.length - 1; i >= 0; i--) {{
                stack.push(children[i]);
            }}
        }}
        const nodeCapReached = stack.length > 0;

        const viewportOverflow = [];
        const parentOverflow = [];
        const containerSel = {container_csv};

        function isInsideBoundedScrollContainer(el) {{
            let cur = el.parentElement;
            while (cur && cur !== document.body && cur !== document.documentElement) {{
                const cs = getComputedStyle(cur);
                if (cs.overflowX === "auto" || cs.overflowX === "scroll") {{
                    const cr = cur.getBoundingClientRect();
                    if (cr.right <= vw + 1.5 && cr.left >= -1.5) {{
                        return true;
                    }}
                }}
                cur = cur.parentElement;
            }}
            return false;
        }}

        for (const el of collected) {{
            if (el === document.body) continue;
            const cs = getComputedStyle(el);
            if (cs.display === "none" || cs.visibility === "hidden") continue;
            if (el.offsetParent === null && cs.position !== "fixed" && cs.position !== "sticky") continue;
            if (el.closest && el.closest("thead")) continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;

            if ((r.right > vw + 1.5 || r.left < -1.5) && !isInsideBoundedScrollContainer(el)) {{
                viewportOverflow.push({{
                    tag: el.tagName,
                    id: el.id || "",
                    cls: (el.className || "").toString().slice(0, 40),
                    left: Math.round(r.left),
                    right: Math.round(r.right),
                    vw,
                    text: (el.innerText || "").slice(0, 45)
                }});
            }}

            const box = (containerSel && el.closest) ? el.closest(containerSel) : null;
            if (box && box !== el) {{
                const boxCs = getComputedStyle(box);
                const isHorizontalScroller = (
                    (boxCs.overflowX === "auto" || boxCs.overflowX === "scroll")
                    && box.scrollWidth > box.clientWidth + 1
                );
                if (!isHorizontalScroller) {{
                    const br = box.getBoundingClientRect();
                    if (r.right > br.right + 1.5 || r.left < br.left - 1.5) {{
                        parentOverflow.push({{
                            tag: el.tagName,
                            cls: (el.className || "").toString().slice(0, 35),
                            boxCls: (box.className || box.tagName).toString().slice(0, 30),
                            elLeft: Math.round(r.left),
                            elRight: Math.round(r.right),
                            boxLeft: Math.round(br.left),
                            boxRight: Math.round(br.right),
                            text: (el.innerText || "").slice(0, 45)
                        }});
                    }}
                }}
            }}
        }}

        const gridDiffs = [];
        if (vw > 1024) {{
            for (const sel of {grid_array}) {{
                const g = document.querySelector(sel);
                if (g && g.children.length === 2) {{
                    const r0 = g.children[0].getBoundingClientRect();
                    const r1 = g.children[1].getBoundingClientRect();
                    gridDiffs.push({{sel, diff: Math.abs(Math.round(r0.height - r1.height))}});
                }}
            }}
        }}

        const tds = Array.from(document.querySelectorAll("td"));
        const maxTdH = tds.length ? Math.max(...tds.map(td => Math.round(td.getBoundingClientRect().height))) : 0;
        const hdr = document.querySelector("header");
        const hdrTop = hdr ? Math.round(hdr.getBoundingClientRect().top) : 0;

        return {{
            vw,
            docClientW,
            docScrollW,
            bodyScrollW,
            direction: dirAttr,
            scannedNodes: collected.length,
            nodeCapReached,
            horizOverflow: docScrollW > vw || bodyScrollW > vw || docScrollW > docClientW,
            hdrTop,
            maxTdH,
            viewportOverflowCount: viewportOverflow.length,
            viewportOverflowSample: viewportOverflow.slice(0, 5),
            parentOverflowCount: parentOverflow.length,
            parentOverflowSample: parentOverflow.slice(0, 5),
            gridDiffs
        }};
    }}"""


def format_junit_xml(report: dict[str, Any]) -> str:
    """Serialize a gate report to JUnit XML for CI systems."""
    devices = report.get("devices", {})
    failures = sum(1 for d in devices.values() if not d.get("passed"))
    suite = ET.Element(
        "testsuite",
        name="viewport18-gate",
        tests=str(len(devices)),
        failures=str(failures),
        errors="0",
    )
    for name, d in devices.items():
        case = ET.SubElement(suite, "testcase", classname="viewport18_gate", name=name)
        if not d.get("passed"):
            msg = (
                f"scrollW={d.get('docScrollW')}/{d.get('vw')} "
                f"vpOvf={d.get('viewportOverflowCount')} "
                f"parOvf={d.get('parentOverflowCount')} "
                f"maxTdH={d.get('maxTdH')}px "
                f"jsErr={len(d.get('jsErrors', []))} "
                f"extReq={len(d.get('extReqs', []))}"
            )
            failure = ET.SubElement(case, "failure", message=msg)
            failure.text = json.dumps(d, sort_keys=True)
    return ET.tostring(suite, encoding="unicode", xml_declaration=True)


def run_gate(config: GateConfig) -> dict[str, Any]:
    """Execute the full 18-viewport audit and write JSON + JPEG artifacts to ``config.out_dir``."""
    out_dir = validate_out_dir(config.out_dir)

    target = config.target
    if "\x00" in target:
        raise ValueError("Target path/URL contains null byte")

    httpd = None
    scheme_match = _URL_SCHEME_RE.match(target)
    if scheme_match and not (len(scheme_match.group(1)) == 1 and target[1:3] in (":\\", ":/")):
        validate_http_target(target, allow_private_network=config.allow_private_network)
        parsed = urllib.parse.urlsplit(target)
        url = target
        origin_prefix = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    else:
        p = Path(target).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Target path does not exist: {target}")
        if p.is_file():
            httpd, port = start_local_server(p.parent)
            url = f"http://127.0.0.1:{port}/{urllib.parse.quote(p.name)}"
        else:
            index_path = p / "index.html"
            if not index_path.is_file():
                raise FileNotFoundError(f"Directory target has no index.html: {p}")
            httpd, port = start_local_server(p)
            url = f"http://127.0.0.1:{port}/index.html"
        origin_prefix = f"http://127.0.0.1:{port}"

    exec_path = find_chromium_exec(config.chromium_path)
    report: dict[str, Any] = {
        "target": target,
        "url": url,
        "viewport_count": len(VIEWPORTS),
        "loadJsErrors": [],
        "loadExtReqs": [],
        "devices": {},
        "all_passed": True,
    }
    dom_audit_js = _build_dom_audit_js(config.container_selectors, config.grid_selectors)

    try:
        with sync_playwright() as pw:
            launch_kw: dict[str, Any] = {"headless": True}
            if exec_path:
                launch_kw["executable_path"] = exec_path
            browser = pw.chromium.launch(**launch_kw)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
            ctx.set_default_timeout(config.navigation_timeout_ms)
            try:
                page = ctx.new_page()
                js_errors: list[str] = []
                ext_reqs: list[str] = []

                def _record_js_error(err: Any) -> None:
                    if len(js_errors) < _MAX_AUDIT_ERRORS:
                        js_errors.append(str(err)[:500])

                def _record_request(req: Any) -> None:
                    if is_external_request(req.url, origin_prefix) and len(ext_reqs) < _MAX_AUDIT_ERRORS:
                        ext_reqs.append(req.url[:500])

                page.on("dialog", lambda d: d.dismiss())
                page.on("pageerror", _record_js_error)
                page.on("request", _record_request)

                ssrf_blocked: list[str] = []
                enforce_ssrf_routes = (httpd is None) and (not config.allow_private_network)
                if config.require_zero_external or enforce_ssrf_routes:
                    def _handle_route(route: Any) -> None:
                        req_url = route.request.url
                        if config.require_zero_external and is_external_request(req_url, origin_prefix):
                            if len(ext_reqs) < _MAX_AUDIT_ERRORS and req_url[:500] not in ext_reqs:
                                ext_reqs.append(req_url[:500])
                            route.abort("blockedbyclient")
                            return
                        if enforce_ssrf_routes:
                            req_scheme = urllib.parse.urlsplit(req_url).scheme.lower()
                            if req_scheme in ("http", "https"):
                                try:
                                    validate_http_target(req_url, allow_private_network=False)
                                except ValueError:
                                    if len(ssrf_blocked) < _MAX_AUDIT_ERRORS and req_url[:500] not in ssrf_blocked:
                                        ssrf_blocked.append(req_url[:500])
                                    route.abort("blockedbyclient")
                                    return
                        route.continue_()

                    page.route("**/*", _handle_route)

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=config.navigation_timeout_ms)
                except PlaywrightTimeoutError as exc:
                    raise TimeoutError(f"Navigation timed out after {config.navigation_timeout_ms}ms: {exc}") from exc
                except PlaywrightError as exc:
                    raise RuntimeError(f"Browser navigation failed: {exc}") from exc
                page.wait_for_timeout(config.settle_ms)

                # Validate --selectors syntax once before looping
                for sel in config.selectors:
                    try:
                        page.evaluate("(s) => { document.querySelector(s); return true; }", sel)
                    except Exception as exc:
                        raise ValueError(f"Invalid CSS selector {sel!r}: {exc}") from exc

                load_js_errors = list(js_errors)
                load_ext_reqs = list(ext_reqs)
                report["loadJsErrors"] = load_js_errors
                report["loadExtReqs"] = load_ext_reqs
                report["ssrfBlocked"] = list(ssrf_blocked)

                for name, w, h in VIEWPORTS:
                    prev_js_len = len(js_errors)
                    prev_ext_len = len(ext_reqs)
                    page.set_viewport_size({"width": w, "height": h})
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(config.viewport_settle_ms)

                    audit = page.evaluate(dom_audit_js)
                    audit["viewportJsErrors"] = js_errors[prev_js_len:]
                    audit["viewportExtReqs"] = ext_reqs[prev_ext_len:]
                    audit["jsErrors"] = list(js_errors)
                    audit["extReqs"] = list(ext_reqs)
                    passed = evaluate_viewport_audit(
                        audit,
                        width=w,
                        max_mobile_td_height=config.max_mobile_td_height,
                        require_zero_external=config.require_zero_external,
                    )
                    audit["passed"] = passed
                    if not passed:
                        report["all_passed"] = False
                    report["devices"][name] = audit

                    if name in SHOT_VIEWPORTS:
                        page.evaluate("window.scrollTo(0, 0)")
                        page.wait_for_timeout(100)
                        page.screenshot(
                            path=str(out_dir / f"{name}_00_top.jpg"),
                            type="jpeg",
                            quality=85,
                        )
                        for idx, sel in enumerate(config.selectors, start=1):
                            found = page.evaluate(
                                "(s) => { const el = document.querySelector(s); "
                                "if (!el) return null; "
                                "return Math.max(0, Math.round(el.getBoundingClientRect().top + window.scrollY - 8)); }",
                                sel,
                            )
                            if found is not None:
                                page.evaluate("(y) => window.scrollTo(0, y)", found)
                                page.wait_for_timeout(100)
                                safe = sanitize_selector_slug(sel)
                                page.screenshot(
                                    path=str(out_dir / f"{name}_{idx:02d}_{safe}.jpg"),
                                    type="jpeg",
                                    quality=85,
                                )
            finally:
                ctx.close()
                browser.close()
    finally:
        if httpd is not None:
            try:
                httpd.shutdown()
            finally:
                httpd.server_close()

    report["ssrfBlocked"] = list(ssrf_blocked)
    (out_dir / "multidevice_gate_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return report
