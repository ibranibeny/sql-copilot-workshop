from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
EXPECTED_STEPS = ["overview", "ssms", "use-case", "deploy", "architecture", "demo"]


class ShowcaseParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.section_ids: list[str] = []
        self.step_hrefs: list[str] = []
        self.images: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.svgs: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "section" and values.get("id"):
            self.section_ids.append(values["id"])
        if tag == "a" and "step-link" in values.get("class", ""):
            self.step_hrefs.append(values.get("href", ""))
        if tag == "img":
            self.images.append(values)
        if tag == "script":
            self.scripts.append(values)
        if tag == "svg":
            self.svgs.append(values)


def read_page() -> str:
    return INDEX.read_text(encoding="utf-8")


def parse_page() -> ShowcaseParser:
    parser = ShowcaseParser()
    parser.feed(read_page())
    return parser


def png_dimensions(path: Path) -> tuple[int, int]:
    content = path.read_bytes()
    if len(content) < 24 or content[:8] != b"\x89PNG\r\n\x1a\n" or content[12:16] != b"IHDR":
        raise AssertionError(f"Not a valid PNG: {path}")
    return struct.unpack(">II", content[16:24])


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class ShowcaseContractTests(unittest.TestCase):
    def test_png_validator_rejects_truncated_files_with_clear_assertion(self) -> None:
        truncated = ROOT / "tests" / "truncated.png"
        truncated.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x00\x00\x01")
        try:
            with self.assertRaisesRegex(AssertionError, "Not a valid PNG"):
                png_dimensions(truncated)
        finally:
            truncated.unlink(missing_ok=True)

    def test_has_exact_guided_six_step_sequence(self) -> None:
        parser = parse_page()
        self.assertEqual(parser.section_ids, EXPECTED_STEPS)
        self.assertEqual(parser.step_hrefs, [f"#{step}" for step in EXPECTED_STEPS])
        page = read_page()
        for number, title in (
            ("01", "GitHub Copilot overview"),
            ("02", "GitHub Copilot in SSMS"),
            ("03", "AI schema exploration and SQL query optimization"),
            ("04", "Deploy the workshop step by step"),
            ("05", "Architecture demo"),
            ("06", "SSMS schema exploration demo"),
        ):
            self.assertIn(f'data-step="{number}"', page)
            self.assertIn(title, page)

    def test_uses_local_microsoft_and_attached_screenshots(self) -> None:
        parser = parse_page()
        by_src = {image.get("src", ""): image for image in parser.images}
        expected = {
            "assets/copilot-ssms-workflow.svg": "Original visual guide to starting GitHub Copilot in SSMS",
            "assets/ssms-copilot-schema-exploration.png": "GitHub Copilot in SSMS reviewing the Sales.Store schema",
        }
        for src, alt in expected.items():
            self.assertIn(src, by_src)
            self.assertEqual(by_src[src].get("alt"), alt)
            self.assertTrue((ROOT / src).is_file())
        page = read_page()
        self.assertIn("Original workshop illustration based on", page)
        self.assertIn("Microsoft Learn guidance", page)
        self.assertIn("discovered through WebIQ", page)
        self.assertIn("Workshop screenshot: GitHub Copilot in SSMS", page)
        self.assertFalse((ROOT / "assets/copilot-ssms-get-started.png").exists())
        self.assertEqual(png_dimensions(ROOT / "assets/ssms-copilot-schema-exploration.png"), (1914, 877))
        workflow_svg = (ROOT / "assets/copilot-ssms-workflow.svg").read_text(encoding="utf-8")
        self.assertIn("<svg", workflow_svg)
        self.assertIn("GitHub Copilot in SSMS", workflow_svg)

    def test_deployment_chapter_is_complete_and_includes_nonoptimized_sql(self) -> None:
        page = read_page()
        for token in (
            "git clone https://github.com/ibranibeny/mcp-sql-query-store-workshop.git",
            "git fetch origin --prune",
            'git cat-file -e "$repositoryCommit^{commit}"',
            "git checkout --detach $repositoryCommit",
            "Connect-AzAccount -Tenant $tenantId -Subscription $subscriptionId",
            "Test-WorkshopPrerequisites.ps1",
            "Deploy-WorkshopEnvironment.ps1",
            "DEPLOY rg-mcp-sql-workshop",
            "CONVERT(date, fs.OrderDate)",
            "INCLUDE (CustomerID, ProductID, OrderQty, UnitPrice, SalesAmount)",
            "Approve-WorkshopCandidate.ps1",
            "APPROVE AdventureWorks2022 candidate",
            "DELETE rg-mcp-sql-workshop",
            "8,000,000",
        ):
            self.assertIn(token, page)
        self.assertNotIn("git fetch origin $repositoryCommit", page)

    def test_architecture_is_inline_accessible_and_has_no_runtime_dependency(self) -> None:
        parser = parse_page()
        self.assertTrue(parser.scripts)
        self.assertTrue(all(not script.get("src") for script in parser.scripts))
        self.assertEqual(len(parser.svgs), 1)
        architecture = parser.svgs[0]
        self.assertEqual(architecture.get("role"), "img")
        self.assertTrue(architecture.get("aria-labelledby"))
        page = read_page()
        self.assertIn("architecture-title", page)
        self.assertIn("architecture-desc", page)
        self.assertIn('class="architecture-frame" tabindex="0"', page)
        self.assertIn('aria-label="Scrollable colored architecture diagram"', page)
        self.assertNotIn("cdn.jsdelivr.net", page)
        self.assertNotIn("mermaid.esm", page)

    def test_uses_mandatory_clawpilot_theme_and_no_component_color_literals(self) -> None:
        page = read_page()
        for token in (
            "--cp-bg: #f7f4ef;",
            "--cp-accent: #b11f4b;",
            "--cp-bg: #3d3b3a;",
            "--cp-accent: #fd8ea1;",
            'font-family: "Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif;',
            'font-family: Consolas, "Courier New", Courier, monospace;',
            'get("scoutTheme")',
            "prefers-color-scheme: dark",
        ):
            self.assertIn(token, page)
        without_vars = re.sub(r"--cp-[\w-]+\s*:\s*[^;]+;", "", page)
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\(", without_vars))

    def test_unsupported_theme_query_is_clamped_after_mandatory_detector(self) -> None:
        page = read_page()
        self.assertIn('if (theme === "light" || theme === "dark") return;', page)
        self.assertIn('document.documentElement.setAttribute("data-theme", fallback);', page)

    def test_secondary_copy_and_focus_meet_wcag_contrast(self) -> None:
        page = read_page()
        self.assertNotIn("color: var(--cp-text-muted)", page)
        self.assertIn(":focus-visible { outline: 3px solid var(--cp-accent)", page)
        for foreground, background, minimum in (
            ("#6f6f6f", "#f7f4ef", 4.5),
            ("#6f6f6f", "#ffffff", 4.5),
            ("#b0b0b0", "#3d3b3a", 4.5),
            ("#b0b0b0", "#292929", 4.5),
            ("#b11f4b", "#f7f4ef", 3.0),
            ("#b11f4b", "#ffffff", 3.0),
            ("#fd8ea1", "#3d3b3a", 3.0),
            ("#fd8ea1", "#292929", 3.0),
        ):
            self.assertGreaterEqual(contrast_ratio(foreground, background), minimum)

    def test_step_rail_tracks_all_section_intersection_ratios(self) -> None:
        page = read_page()
        self.assertIn("const ratios = new Map(sections.map", page)
        self.assertIn("ratios.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0)", page)
        self.assertIn("sections.reduce((best, section)", page)
        self.assertNotIn("entries.filter((entry) => entry.isIntersecting).sort", page)

    def test_guided_rail_is_sticky_responsive_and_accessible(self) -> None:
        page = read_page()
        self.assertIn("position: sticky", page)
        self.assertIn("@media (max-width: 900px)", page)
        self.assertIn("@media (max-width: 640px)", page)
        self.assertIn("@media (prefers-reduced-motion: reduce)", page)
        self.assertIn(":focus-visible", page)
        self.assertIn('aria-label="Workshop steps"', page)
        self.assertIn('class="skip-link"', page)

    def test_mobile_rail_gutter_matches_mobile_page_gutter(self) -> None:
        page = read_page()
        mobile = page.split("@media (max-width: 640px)", 1)[1]
        self.assertIn(".step-rail { margin-inline: -0.75rem; padding-inline: 0.75rem; }", mobile)

    def test_tablet_and_mobile_anchor_targets_clear_sticky_rail(self) -> None:
        page = read_page()
        tablet = page.split("@media (max-width: 900px)", 1)[1].split("@media (max-width: 640px)", 1)[0]
        self.assertIn(".chapter { scroll-margin-top: 5rem; }", tablet)

    def test_links_only_to_expected_first_party_and_repository_hosts(self) -> None:
        hosts = set(re.findall(r'https://([^/"\s]+)', read_page()))
        self.assertEqual(hosts, {"github.com", "learn.microsoft.com"})


if __name__ == "__main__":
    unittest.main()
