# viewport18-gate

Deterministic 18-width responsive layout, DOM containment, and zero-egress verification CLI powered by Playwright.

> **Warranty & Support Notice:** Provided **AS-IS** under the Apache License 2.0; **No SLA, No Support Guarantees**. Published as a standalone, non-commercial personal research utility by Shady Ismail (ORCID `0009-0005-3920-2333`), with no paid tiers, SaaS upsells, or commercial support offerings.

## Architecture

```text
  [HTML dir / index.html / http(s) URL]
                   |
                   v
    +------------------------------+
    |  Ephemeral 127.0.0.1 Server  |  (for local files/dirs; dotfile-blocked)
    +------------------------------+
                   |
                   v
    +------------------------------+
    |   Headless Chromium Sweep    |  (18 viewports: 320px -> 1920px, DPR=2)
    +------------------------------+
          |            |           |
          v            v           v
   [DOM Geometry] [JS Errors] [Egress Audit]
   - scrollWidth  - pageerror - 3rd-party HTTP(S)
   - el vs vw
   - el vs parent box
   - mobile <td> height
   - desktop 2-col parity
          |
          v
    [multidevice_gate_report.json + 5-breakpoint JPEG screenshots]
```

## 30-Second Quickstart

```bash
pip install "git+https://github.com/shady-ismail/viewport18-gate.git"
playwright install chromium

# Audit a built static directory (blocks & fails on any 3rd-party HTTP(S) request)
viewport18-gate ./dist --out ./gate-report --require-zero-external

# Audit a single HTML file, local dev server, or public URL
viewport18-gate ./index.html --out ./gate-report
viewport18-gate http://127.0.0.1:3000 --out ./gate-report --allow-private-network
viewport18-gate https://example.com --out ./gate-report --format junit
```

### Security & CI Guardrails

- **Scheme allowlist:** Only local filesystem paths and `http://`/`https://` targets are accepted; `file://`, `javascript:`, and `data:` targets are rejected (`exit 2`).
- **SSRF protection by default:** External `http(s)://` URL targets pointing to loopback, private, or link-local IP ranges (`127.0.0.0/8`, `10.0.0.0/8`, `169.254.0.0/16`, `::1`, etc.) are rejected unless `--allow-private-network` is passed.
- **Active egress blocking:** With `--require-zero-external`, Playwright actively aborts third-party HTTP(S) requests in addition to failing the audit.
- **RTL & Shadow DOM parity:** Scans `body` descendants (including `position: fixed`/`sticky` elements and open Shadow DOM roots) symmetrically on both left and right edges, while skipping intentional `overflow-x: auto|scroll` wrappers.
- **CI output formats:** Supports `--format text` (default), `--format json`, `--format junit`, and `--format github` (`::error` annotations).

Running from source without installing globally:

```bash
PYTHONPATH=src python3 -m viewport18_gate ./dist --out ./gate-report
```

## The 18-Viewport Continuous Spectrum (`320px` to `1920px`)

| # | Viewport Name | Dimensions | Device Class | Screenshot |
|---|---|---|---|---|
| 1 | `ultra_narrow_320x568` | `320x568` | Ultra-narrow phone | Yes |
| 2 | `fold_cover_344x882` | `344x882` | Foldable cover screen | - |
| 3 | `phone_compact_375x812` | `375x812` | Compact phone | - |
| 4 | `iphone_390x844` | `390x844` | Standard phone | Yes |
| 5 | `android_412x915` | `412x915` | Android standard phone | - |
| 6 | `phone_max_430x932` | `430x932` | Large phone | - |
| 7 | `dual_screen_540x720` | `540x720` | Dual-screen / small unfolded | - |
| 8 | `breakpoint_640x800` | `640x800` | SM/MD CSS breakpoint | - |
| 9 | `fold_unfolded_680x840` | `680x840` | Unfolded foldable | Yes |
| 10 | `ipad_mini_744x1133` | `744x1133` | Small tablet portrait | - |
| 11 | `ipad_portrait_768x1024` | `768x1024` | Tablet portrait | - |
| 12 | `tablet_air_820x1180` | `820x1180` | Medium tablet portrait | Yes |
| 13 | `surface_pro_912x1368` | `912x1368` | Large tablet portrait | - |
| 14 | `tablet_land_1024x768` | `1024x768` | Tablet landscape | - |
| 15 | `tablet_wide_1180x820` | `1180x820` | Wide tablet landscape | - |
| 16 | `desktop_1240x900` | `1240x900` | Compact laptop | - |
| 17 | `desktop_1440x900` | `1440x900` | Standard desktop | Yes |
| 18 | `desktop_fhd_1920x1080` | `1920x1080` | Full HD monitor | - |

## Exit Codes

- `0`: All 18 viewports passed every geometric, containment, runtime error, and egress check (`PASSED_ALL_18`).
- `1`: One or more viewports failed (`FAILED`).
- `2`: Invalid CLI target or configuration error.

## Testing

```bash
# Offline unit tests (no Chromium binary required)
pytest tests/test_unit_core.py

# Full test suite including live Playwright HTML fixtures
pytest
```

## License

Licensed under the [Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE) and [DEPENDENCIES.md](DEPENDENCIES.md).
