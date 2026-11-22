"""Command-line interface for viewport18-gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .audit import GateConfig, format_junit_xml, run_gate

AS_IS_NOTICE = (
    "Provided AS-IS under Apache-2.0; No SLA, No Support Guarantees. "
    "Non-commercial personal research utility."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="viewport18-gate",
        description=(
            "18-Width Continuous-Spectrum Responsive Layout, DOM Containment, "
            "and Zero-Egress Verification Gate (320px to 1920px)."
        ),
        epilog=AS_IS_NOTICE,
    )
    parser.add_argument(
        "target",
        help="Local HTML file, local directory containing index.html, or live http(s):// URL",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for multi-device screenshots and multidevice_gate_report.json",
    )
    parser.add_argument(
        "--max-mobile-td-height",
        type=int,
        default=260,
        help="Maximum allowed <td> height (px) on viewports <= 768px (default: 260)",
    )
    parser.add_argument(
        "--require-zero-external",
        action="store_true",
        help="Block and fail if any third-party HTTP(S) network request occurs",
    )
    parser.add_argument(
        "--allow-private-network",
        action="store_true",
        help="Allow http(s):// targets pointing to loopback or private/link-local IP ranges",
    )
    parser.add_argument(
        "--selectors",
        default="",
        help="Comma-separated CSS selectors for extra scroll-position screenshots",
    )
    parser.add_argument(
        "--chromium-path",
        default=None,
        help="Optional explicit path to Chromium or chrome-headless-shell executable",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=25_000,
        help="Navigation and Playwright action timeout in milliseconds (default: 25000)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "junit", "github"),
        default="text",
        help="Stdout output format (default: text)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.timeout_ms <= 0:
        print("ERROR: --timeout-ms must be positive", file=sys.stderr)
        return 2
    if args.max_mobile_td_height <= 0:
        print("ERROR: --max-mobile-td-height must be positive", file=sys.stderr)
        return 2

    selectors = tuple(s.strip() for s in args.selectors.split(",") if s.strip())
    config = GateConfig(
        target=args.target,
        out_dir=Path(args.out),
        max_mobile_td_height=args.max_mobile_td_height,
        require_zero_external=args.require_zero_external,
        allow_private_network=args.allow_private_network,
        selectors=selectors,
        chromium_path=args.chromium_path,
        navigation_timeout_ms=args.timeout_ms,
    )

    try:
        report = run_gate(config)
    except (FileNotFoundError, ValueError, TimeoutError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, indent=2))
    elif args.format == "junit":
        print(format_junit_xml(report))
    elif args.format == "github":
        for name, d in report["devices"].items():
            if not d["passed"]:
                print(
                    f"::error title=viewport18-gate {name}::"
                    f"scrollW={d['docScrollW']}/{d['vw']} "
                    f"vpOvf={d['viewportOverflowCount']} "
                    f"parOvf={d['parentOverflowCount']} "
                    f"maxTdH={d['maxTdH']}px "
                    f"jsErr={len(d['jsErrors'])} "
                    f"extReq={len(d['extReqs'])}"
                )
        print(f"OVERALL_18WIDTH_SPECTRUM_GATE: {'PASSED_ALL_18' if report['all_passed'] else 'FAILED'}")
    else:
        for name, d in report["devices"].items():
            status = "PASS" if d["passed"] else "FAIL"
            print(
                f"[{status}] {name:24s} | scrollW={d['docScrollW']}/{d['vw']} | "
                f"vpOvf={d['viewportOverflowCount']} | parOvf={d['parentOverflowCount']} | "
                f"maxTdH={d['maxTdH']}px | jsErr={len(d['jsErrors'])} | extReq={len(d['extReqs'])}"
            )
        print(f"OVERALL_18WIDTH_SPECTRUM_GATE: {'PASSED_ALL_18' if report['all_passed'] else 'FAILED'}")

    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
