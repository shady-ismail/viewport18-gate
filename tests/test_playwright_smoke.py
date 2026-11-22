"""Live Playwright smoke and adversarial torture tests for viewport18-gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.playwright

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(target: str, out_dir: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run(
        [sys.executable, "-m", "viewport18_gate", target, "--out", str(out_dir), *extra_args],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def _write_site(base: Path, html: str, css: str = "", js: str = "") -> Path:
    site = base / "site"
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(html, encoding="utf-8")
    if css:
        (site / "styles.css").write_text(css, encoding="utf-8")
    if js:
        (site / "app.js").write_text(js, encoding="utf-8")
    return site


CLEAN_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"{dir_attr}>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clean Fixture</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: sans-serif; line-height: 1.5; }}
    .wrap {{ width: 100%; max-width: 1120px; margin: 0 auto; padding: 16px; }}
    header {{ border-bottom: 1px solid #ccc; }}
    .card {{ border: 1px solid #bbb; padding: 16px; background: #fafafa; }}
    .two-col-grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
    @media (min-width: 1025px) {{
      .two-col-grid {{ grid-template-columns: 1fr 1fr; align-items: stretch; }}
    }}
    table {{ width: 100%; table-layout: fixed; border-collapse: collapse; }}
    td, th {{ padding: 8px; border-bottom: 1px solid #ddd; overflow-wrap: anywhere; }}
    {extra_css}
  </style>
</head>
<body>
  <header class="wrap"><strong>Responsive Fixture</strong></header>
  <main class="wrap">
    <h1>Overview</h1>
    <section id="grid-sec" class="two-col-grid">
      <div class="card"><p>Column A balanced summary content.</p></div>
      <div class="card"><p>Column B balanced summary content.</p></div>
    </section>
    <section id="table-sec" class="card">
      <table>
        <thead><tr><th>Item</th><th>Value</th></tr></thead>
        <tbody><tr><td>Row-1</td><td>100</td></tr></tbody>
      </table>
    </section>
    {extra_body}
  </main>
  <footer class="wrap"><small>Local fixture</small></footer>
  {extra_scripts}
</body>
</html>
"""


def test_live_clean_ltr_fixture_passes_all_18_and_creates_screenshots(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(dir_attr="", extra_css="", extra_body="", extra_scripts="")
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_clean"

    proc = _run_cli(str(site), out, "--require-zero-external", "--selectors", "#grid-sec")
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "OVERALL_18WIDTH_SPECTRUM_GATE: PASSED_ALL_18" in proc.stdout

    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    assert report["viewport_count"] == 18
    assert report["all_passed"] is True
    for shot_vp in (
        "ultra_narrow_320x568",
        "iphone_390x844",
        "fold_unfolded_680x840",
        "tablet_air_820x1180",
        "desktop_1440x900",
    ):
        top_jpg = out / f"{shot_vp}_00_top.jpg"
        sec_jpg = out / f"{shot_vp}_01_grid-sec.jpg"
        assert top_jpg.is_file() and top_jpg.stat().st_size > 1000
        assert sec_jpg.is_file() and sec_jpg.stat().st_size > 1000


def test_live_clean_rtl_fixture_passes_all_18(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(dir_attr=' dir="rtl"', extra_css="", extra_body="", extra_scripts="")
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_rtl_clean"

    proc = _run_cli(str(site), out, "--require-zero-external")
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    assert report["devices"]["iphone_390x844"]["direction"] == "rtl"
    assert report["all_passed"] is True


def test_live_horizontal_overflow_caught(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr="",
        extra_css=".wide-box { width: 1200px; height: 40px; background: #eee; }",
        extra_body='<div class="wide-box">Overflowing block</div>',
        extra_scripts="",
    )
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_ovf"

    proc = _run_cli(str(site), out)
    assert proc.returncode == 1
    assert "OVERALL_18WIDTH_SPECTRUM_GATE: FAILED" in proc.stdout

    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    assert report["all_passed"] is False
    assert report["devices"]["ultra_narrow_320x568"]["horizOverflow"] is True
    assert report["devices"]["ultra_narrow_320x568"]["viewportOverflowCount"] > 0
    assert report["devices"]["desktop_1440x900"]["passed"] is True


def test_live_rtl_left_edge_overflow_caught(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr=' dir="rtl"',
        extra_css=".rtl-spill { width: 900px; height: 24px; }",
        extra_body='<div class="rtl-spill">RTL spill element</div>',
        extra_scripts="",
    )
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_rtl_ovf"

    proc = _run_cli(str(site), out)
    assert proc.returncode == 1
    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    mobile = report["devices"]["iphone_390x844"]
    assert mobile["passed"] is False
    assert mobile["viewportOverflowCount"] > 0
    assert any(item["left"] < 0 for item in mobile["viewportOverflowSample"])


def test_live_child_outside_parent_overflow_caught(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr="",
        extra_css=(
            ".narrow-card { width: 220px; overflow: visible; } "
            ".poke-out { display: inline-block; width: 310px; white-space: nowrap; }"
        ),
        extra_body='<div class="card narrow-card"><span class="poke-out">Unwrapped child spilling out</span></div>',
        extra_scripts="",
    )
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_parent_ovf"

    proc = _run_cli(str(site), out)
    assert proc.returncode == 1
    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    assert report["devices"]["desktop_1440x900"]["parentOverflowCount"] > 0
    assert report["devices"]["desktop_1440x900"]["passed"] is False


def test_live_fixed_element_and_shadow_dom_overflow_caught(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr="",
        extra_css=".fixed-bad { position: fixed; top: 0; left: 0; width: 500px; height: 20px; }",
        extra_body='<div class="fixed-bad">Fixed banner</div><x-widget></x-widget>',
        extra_scripts=(
            "<script>"
            "const host = document.querySelector('x-widget');"
            "const sr = host.attachShadow({mode: 'open'});"
            "sr.innerHTML = '<div style=\"width:600px;height:20px\">Shadow spill</div>';"
            "</script>"
        ),
    )
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_shadow_fixed"

    proc = _run_cli(str(site), out)
    assert proc.returncode == 1
    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    mobile = report["devices"]["iphone_390x844"]
    assert mobile["viewportOverflowCount"] >= 2
    tags = {item["tag"] for item in mobile["viewportOverflowSample"]}
    assert "DIV" in tags


def test_live_mobile_table_height_explosion_caught(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr="",
        extra_css="@media (max-width: 768px) { td.tall { height: 340px; } }",
        extra_body='<table><tbody><tr><td class="tall">Tall cell</td></tr></tbody></table>',
        extra_scripts="",
    )
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_td"

    proc = _run_cli(str(site), out, "--max-mobile-td-height", "260")
    assert proc.returncode == 1
    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    assert report["devices"]["iphone_390x844"]["maxTdH"] >= 340
    assert report["devices"]["iphone_390x844"]["passed"] is False
    assert report["devices"]["desktop_1440x900"]["passed"] is True


def test_live_js_error_and_blocking_dialog_handled(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr="",
        extra_css="",
        extra_body="",
        extra_scripts='<script>alert("xss-sentinel"); throw new Error("runtime-boom");</script>',
    )
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_jserr"

    proc = _run_cli(str(site), out)
    assert proc.returncode == 1
    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    assert any("runtime-boom" in err for err in report["loadJsErrors"])
    assert report["devices"]["desktop_1440x900"]["passed"] is False


def test_live_external_request_blocked_and_failed(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr="",
        extra_css="",
        extra_body="",
        extra_scripts='<script src="https://example.invalid/tracker.js"></script>',
    )
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_ext"

    proc = _run_cli(str(site), out, "--require-zero-external")
    assert proc.returncode == 1
    report = json.loads((out / "multidevice_gate_report.json").read_text(encoding="utf-8"))
    assert "https://example.invalid/tracker.js" in report["loadExtReqs"]
    assert report["devices"]["desktop_1440x900"]["passed"] is False


def test_live_malformed_css_selector_rejected_cleanly(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(dir_attr="", extra_css="", extra_body="", extra_scripts="")
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_badsel"

    proc = _run_cli(str(site), out, "--selectors", "#bad[[[")
    assert proc.returncode == 2
    assert "Invalid CSS selector" in proc.stderr


def test_live_scrollable_table_wrapper_does_not_false_positive_parent_overflow(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr="",
        extra_css=(
            ".scroll-card { overflow-x: auto; max-width: 100%; } "
            ".scroll-card table { width: 700px; table-layout: auto; }"
        ),
        extra_body=(
            '<div class="card scroll-card">'
            "<table><tbody><tr><td>Col1</td><td>Col2</td><td>Col3</td><td>Col4</td></tr></tbody></table>"
            "</div>"
        ),
        extra_scripts="",
    )
    site = _write_site(tmp_path, html)
    out = tmp_path / "out_scroll_ok"

    proc = _run_cli(str(site), out)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr


def test_live_ci_output_formats_json_junit_github(tmp_path: Path) -> None:
    html = CLEAN_HTML_TEMPLATE.format(
        dir_attr="",
        extra_css=".wide-box { width: 900px; height: 20px; }",
        extra_body='<div class="wide-box">Overflow</div>',
        extra_scripts="",
    )
    site = _write_site(tmp_path, html)

    proc_gh = _run_cli(str(site), tmp_path / "out_gh", "--format", "github")
    assert proc_gh.returncode == 1
    assert "::error title=viewport18-gate " in proc_gh.stdout

    proc_junit = _run_cli(str(site), tmp_path / "out_junit", "--format", "junit")
    assert proc_junit.returncode == 1
    assert '<testsuite name="viewport18-gate" tests="18"' in proc_junit.stdout


def test_live_slow_server_timeout_resilience(tmp_path: Path) -> None:
    import http.server
    import threading
    import time

    class SlowHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            time.sleep(2.5)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html><body>late</body></html>")

        def log_message(self, *args) -> None:
            return

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        proc = _run_cli(
            f"http://127.0.0.1:{port}/",
            tmp_path / "out_timeout",
            "--allow-private-network",
            "--timeout-ms",
            "400",
        )
        assert proc.returncode == 2
        assert "ERROR:" in proc.stderr
    finally:
        httpd.shutdown()
        httpd.server_close()
