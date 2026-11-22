"""Viewport spectrum definitions for 18-width responsive layout verification."""

from __future__ import annotations

from typing import NamedTuple


class ViewportSpec(NamedTuple):
    """Single viewport width/height specification."""

    name: str
    width: int
    height: int
    category: str


VIEWPORT_SPECS: tuple[ViewportSpec, ...] = (
    ViewportSpec("ultra_narrow_320x568", 320, 568, "Ultra-narrow phone"),
    ViewportSpec("fold_cover_344x882", 344, 882, "Foldable cover screen"),
    ViewportSpec("phone_compact_375x812", 375, 812, "Compact phone"),
    ViewportSpec("iphone_390x844", 390, 844, "Standard phone"),
    ViewportSpec("android_412x915", 412, 915, "Android standard phone"),
    ViewportSpec("phone_max_430x932", 430, 932, "Large phone"),
    ViewportSpec("dual_screen_540x720", 540, 720, "Dual-screen / small unfolded"),
    ViewportSpec("breakpoint_640x800", 640, 800, "SM/MD CSS breakpoint"),
    ViewportSpec("fold_unfolded_680x840", 680, 840, "Unfolded foldable"),
    ViewportSpec("ipad_mini_744x1133", 744, 1133, "Small tablet portrait"),
    ViewportSpec("ipad_portrait_768x1024", 768, 1024, "Tablet portrait"),
    ViewportSpec("tablet_air_820x1180", 820, 1180, "Medium tablet portrait"),
    ViewportSpec("surface_pro_912x1368", 912, 1368, "Large tablet portrait"),
    ViewportSpec("tablet_land_1024x768", 1024, 768, "Tablet landscape"),
    ViewportSpec("tablet_wide_1180x820", 1180, 820, "Wide tablet landscape"),
    ViewportSpec("desktop_1240x900", 1240, 900, "Compact laptop"),
    ViewportSpec("desktop_1440x900", 1440, 900, "Standard desktop"),
    ViewportSpec("desktop_fhd_1920x1080", 1920, 1080, "Full HD monitor"),
)

VIEWPORTS: list[tuple[str, int, int]] = [
    (spec.name, spec.width, spec.height) for spec in VIEWPORT_SPECS
]

SHOT_VIEWPORTS: frozenset[str] = frozenset(
    {
        "ultra_narrow_320x568",
        "iphone_390x844",
        "fold_unfolded_680x840",
        "tablet_air_820x1180",
        "desktop_1440x900",
    }
)
