from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
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


class ShowcaseContractTests(unittest.TestCase):
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
            "assets/copilot-ssms-get-started.png": "Microsoft Learn page showing how to get started with GitHub Copilot in SSMS",
            "assets/ssms-copilot-schema-exploration.png": "GitHub Copilot in SSMS reviewing the Sales.Store schema",
        }
        for src, alt in expected.items():
            self.assertIn(src, by_src)
            self.assertEqual(by_src[src].get("alt"), alt)
            self.assertTrue((ROOT / src).is_file())
        self.assertIn("Image source: Microsoft", read_page())
        self.assertIn("Workshop screenshot: GitHub Copilot in SSMS", read_page())

    def test_deployment_chapter_is_complete_and_includes_nonoptimized_sql(self) -> None:
        page = read_page()
        for token in (
            "git clone https://github.com/ibranibeny/mcp-sql-query-store-workshop.git",
            "Test-WorkshopPrerequisites.ps1",
            "Deploy-WorkshopEnvironment.ps1",
            "DEPLOY rg-mcp-sql-workshop",
            "YEAR(fs.OrderDate)",
            "MONTH(fs.OrderDate)",
            "DROP INDEX IX_FactSales_OrderDate_Territory ON lab.FactSales",
            "8,000,000",
        ):
            self.assertIn(token, page)

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

    def test_links_only_to_expected_first_party_and_repository_hosts(self) -> None:
        hosts = set(re.findall(r'https://([^/"\s]+)', read_page()))
        self.assertEqual(hosts, {"github.com", "learn.microsoft.com", "www.microsoft.com"})


if __name__ == "__main__":
    unittest.main()
