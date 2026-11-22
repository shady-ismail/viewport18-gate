"""Offline unit tests for viewport18-gate (no Chromium binary required)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from viewport18_gate import (
    SHOT_VIEWPORTS,
    VIEWPORTS,
    VIEWPORT_SPECS,
    evaluate_viewport_audit,
    find_chromium_exec,
    format_junit_xml,
    is_external_request,
    sanitize_selector_slug,
    start_local_server,
    validate_http_target,
    validate_out_dir,
)


def _make_exec(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_18_viewports_spectrum_completeness() -> None:
    assert len(VIEWPORTS) == 18
    assert len(VIEWPORT_SPECS) == 18
    names = [name for name, _, _ in VIEWPORTS]
    widths = [w for _, w, _ in VIEWPORTS]
    assert len(set(names)) == 18
    assert widths[0] == 320
    assert widths[-1] == 1920
    assert widths == sorted(widths)
    assert SHOT_VIEWPORTS.issubset(set(names))
    assert len(SHOT_VIEWPORTS) == 5


def test_find_chromium_exec_explicit_env_and_executable_bit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    non_exec = tmp_path / "not-executable"
    non_exec.write_text("dummy", encoding="utf-8")
    non_exec.chmod(0o644)

    fake_bin = _make_exec(tmp_path / "chrome-headless-shell")

    assert find_chromium_exec(str(non_exec)) != str(non_exec)
    assert find_chromium_exec(str(fake_bin)) == str(fake_bin)

    monkeypatch.setenv("VIEWPORT18_CHROMIUM_PATH", str(fake_bin))
    assert find_chromium_exec(None) == str(fake_bin)


def test_find_chromium_exec_numeric_revision_sort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VIEWPORT18_CHROMIUM_PATH", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    old_bin = _make_exec(
        tmp_path
        / ".cache"
        / "ms-playwright"
        / "chromium_headless_shell-999"
        / "chrome-headless-shell-linux64"
        / "chrome-headless-shell"
    )
    new_bin = _make_exec(
        tmp_path
        / ".cache"
        / "ms-playwright"
        / "chromium_headless_shell-1000"
        / "chrome-headless-shell-linux64"
        / "chrome-headless-shell"
    )
    assert old_bin.is_file()
    assert find_chromium_exec() == str(new_bin)


def test_origin_matching_rejects_port_prefix_spoof() -> None:
    origin = "http://127.0.0.1:8000"
    assert is_external_request("http://127.0.0.1:8000/app.js", origin) is False
    assert is_external_request("http://127.0.0.1:80001/evil.js", origin) is True
    assert is_external_request("https://cdn.example.net/lib.js", origin) is True
    assert is_external_request("data:image/png;base64,AAAA", origin) is False
    assert is_external_request("blob:http://127.0.0.1:8000/123", origin) is False


def test_local_http_server_serves_cleanly_and_blocks_post(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    httpd, port = start_local_server(tmp_path)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as resp:
            assert resp.status == 200
            assert resp.read().decode("utf-8") == "<h1>ok</h1>"

        req = urllib.request.Request(f"http://127.0.0.1:{port}/index.html", method="POST", data=b"x")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 405
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_local_http_server_blocks_dotfiles_and_symlinks(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET", encoding="utf-8")
    webroot = tmp_path / "webroot"
    webroot.mkdir()
    (webroot / ".env").write_text("SECRET=1", encoding="utf-8")
    (webroot / "index.html").write_text("ok", encoding="utf-8")
    (webroot / "escape.txt").symlink_to(outside)

    httpd, port = start_local_server(webroot)
    try:
        for path in ("/.env", "/escape.txt"):
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5)
            assert exc_info.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_ssrf_and_scheme_validation() -> None:
    for bad in (
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
        "ftp://example.com/a",
        "http://127.0.0.1:8080/",
        "http://localhost:3000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/admin",
        "http://[::1]:8000/",
    ):
        with pytest.raises(ValueError):
            validate_http_target(bad, allow_private_network=False)

    parsed = validate_http_target("http://127.0.0.1:8080/", allow_private_network=True)
    assert parsed.hostname == "127.0.0.1"
    parsed_pub = validate_http_target("https://93.184.216.34/", allow_private_network=False)
    assert parsed_pub.scheme == "https"


def test_validate_out_dir_rejects_symlink_and_file(tmp_path: Path) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link_dir = tmp_path / "link_out"
    link_dir.symlink_to(real_dir)
    with pytest.raises(ValueError):
        validate_out_dir(link_dir)

    reg_file = tmp_path / "file.txt"
    reg_file.write_text("not a dir", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_out_dir(reg_file)


def test_evaluate_viewport_audit_thresholds() -> None:
    base = {
        "horizOverflow": False,
        "viewportOverflowCount": 0,
        "parentOverflowCount": 0,
        "jsErrors": [],
        "extReqs": [],
        "gridDiffs": [{"sel": ".two-col-grid", "diff": 2}],
        "maxTdH": 260,
    }
    assert evaluate_viewport_audit(base, width=390, max_mobile_td_height=260, require_zero_external=True) is True

    too_tall_mobile = dict(base, maxTdH=261)
    assert evaluate_viewport_audit(too_tall_mobile, width=768, max_mobile_td_height=260, require_zero_external=True) is False
    assert evaluate_viewport_audit(too_tall_mobile, width=820, max_mobile_td_height=260, require_zero_external=True) is True

    bad_grid = dict(base, gridDiffs=[{"sel": ".two-col-grid", "diff": 3}])
    assert evaluate_viewport_audit(bad_grid, width=1440, max_mobile_td_height=260, require_zero_external=True) is False


def test_evaluate_viewport_audit_external_toggle() -> None:
    audit = {
        "horizOverflow": False,
        "viewportOverflowCount": 0,
        "parentOverflowCount": 0,
        "jsErrors": [],
        "extReqs": ["https://example.net/pixel.js"],
        "gridDiffs": [],
        "maxTdH": 40,
    }
    assert evaluate_viewport_audit(audit, width=1440, max_mobile_td_height=260, require_zero_external=False) is True
    assert evaluate_viewport_audit(audit, width=1440, max_mobile_td_height=260, require_zero_external=True) is False


def test_cli_help_includes_as_is_no_sla_notice() -> None:
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    proc = subprocess.run(
        [sys.executable, "-m", "viewport18_gate", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0
    assert "AS-IS" in proc.stdout
    assert "No SLA" in proc.stdout


def test_cli_missing_target_and_bad_schemes_exit_2(tmp_path: Path) -> None:
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    for bad_target in (
        str(tmp_path / "missing.html"),
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://169.254.169.254/latest/meta-data/",
    ):
        proc = subprocess.run(
            [sys.executable, "-m", "viewport18_gate", bad_target, "--out", str(tmp_path / "out")],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        assert proc.returncode == 2, f"Expected exit 2 for {bad_target}, got {proc.returncode}"
        assert "ERROR:" in proc.stderr


def test_selector_sanitization_and_junit_xml() -> None:
    assert sanitize_selector_slug("#hero-section") == "hero-section"
    assert sanitize_selector_slug("../../etc/passwd") == "etc_passwd"
    assert sanitize_selector_slug("...") == "section"

    report = {
        "devices": {
            name: {
                "vw": w,
                "docScrollW": w if i > 0 else w + 50,
                "viewportOverflowCount": 0 if i > 0 else 1,
                "parentOverflowCount": 0,
                "maxTdH": 40,
                "jsErrors": [],
                "extReqs": [],
                "passed": i > 0,
            }
            for i, (name, w, _) in enumerate(VIEWPORTS)
        }
    }
    xml_str = format_junit_xml(report)
    root = ET.fromstring(xml_str)
    assert root.attrib["tests"] == "18"
    assert root.attrib["failures"] == "1"
    encoded = json.dumps(report)
    assert len(json.loads(encoded)["devices"]) == 18
