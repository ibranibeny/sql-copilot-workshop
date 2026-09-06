from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
EXPECTED_STEPS = ["overview", "ssms", "use-case", "deploy", "architecture", "demo"]


class ShowcaseParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.section_ids: list[str] = []
        self.step_hrefs: list[str] = []
        self.step_links: list[dict[str, str]] = []
        self.section_headings: dict[str, str] = {}
        self.images: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.svgs: list[dict[str, str]] = []
        self._current_section = ""
        self._current_step_link: dict[str, str] | None = None
        self._inside_step_label = False
        self._inside_section_heading = False
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "section" and values.get("id"):
            self.section_ids.append(values["id"])
            self._current_section = values["id"]
        if tag == "a" and "step-link" in values.get("class", ""):
            self.step_hrefs.append(values.get("href", ""))
            self._current_step_link = {
                "href": values.get("href", ""),
                "label": "",
                "aria-label": values.get("aria-label", ""),
            }
            self.step_links.append(self._current_step_link)
        if tag == "span" and "step-label" in values.get("class", "") and self._current_step_link:
            self._inside_step_label = True
            self._text_parts = []
        if tag == "h2" and self._current_section:
            self._inside_section_heading = True
            self._text_parts = []
        if tag == "img":
            self.images.append(values)
        if tag == "script":
            self.scripts.append(values)
        if tag == "svg":
            self.svgs.append(values)

    def handle_data(self, data: str) -> None:
        if self._inside_step_label or self._inside_section_heading:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._inside_step_label:
            assert self._current_step_link is not None
            self._current_step_link["label"] = "".join(self._text_parts).strip()
            self._inside_step_label = False
            self._text_parts = []
        elif tag == "h2" and self._inside_section_heading:
            self.section_headings[self._current_section] = "".join(self._text_parts).strip()
            self._inside_section_heading = False
            self._text_parts = []
        elif tag == "a" and self._current_step_link:
            self._current_step_link = None
        elif tag == "section":
            self._current_section = ""


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
    def test_workshop_is_a_continuous_l300_narrative(self) -> None:
        page = read_page()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for token in (
            'content="L300"',
            'class="level-chip">L300',
            "A slow report. An unfamiliar schema. One evidence-backed decision.",
            "Meet the Contoso AI database platform team",
            "Contoso AI opens SSMS",
            "Before Contoso AI changes a query",
            "Contoso AI can now explain why",
            "What you will be able to do",
            "Lab detail: deployment commands",
            "Lab detail: baseline and candidate SQL",
        ):
            self.assertIn(token, page)
        self.assertIn("L300", readme)
        self.assertIn("Contoso AI", readme)
        self.assertNotIn("Maya", page)
        self.assertNotIn("Maya", readme)
        self.assertNotIn("L400", page)
        self.assertNotIn("L400", readme)

    def test_primary_story_is_ssms_and_github_copilot_not_sql_mcp(self) -> None:
        page = read_page()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("<title>GitHub Copilot in SSMS Workshop</title>", page)
        self.assertIn("L300 guided workshop · SSMS + GitHub Copilot", page)
        self.assertIn("execution plans and Query Store provide the evidence", page)
        self.assertIn("SSMS + GitHub Copilot", page)
        self.assertIn("MCP servers", page)
        self.assertNotRegex(page, r"(?i)(?:Microsoft\s+|DAB\s+)?SQL\s+MCP")
        self.assertIn("# GitHub Copilot in SSMS Workshop", readme)
        self.assertNotRegex(readme, r"(?i)(?:Microsoft\s+|DAB\s+)?SQL\s+MCP")

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
            ("01", "Meet the Contoso AI database platform team"),
            ("02", "Contoso AI opens SSMS and asks the first question"),
            ("03", "The month-end slowdown becomes the case"),
            ("04", "Before Contoso AI changes a query, the team builds the lab"),
            ("05", "Contoso AI traces where trust begins and ends"),
            ("06", "Contoso AI can now explain why the query is slow"),
        ):
            self.assertIn(f'data-step="{number}"', page)
            self.assertIn(title, page)

    def test_step_rail_labels_follow_narrative_chapter_titles(self) -> None:
        parser = parse_page()
        visible_labels = (
            "Meet Contoso AI",
            "Ask the first question",
            "Month-end case",
            "Build the lab",
            "Trace trust boundaries",
            "Explain the slow query",
        )
        expected = [
            (
                f"#{section_id}",
                visible_label,
                f"Step {position}: {parser.section_headings[section_id]}",
            )
            for position, (section_id, visible_label) in enumerate(
                zip(EXPECTED_STEPS, visible_labels, strict=True),
                start=1,
            )
        ]
        actual = [
            (link["href"], link["label"], link["aria-label"])
            for link in parser.step_links
        ]
        self.assertEqual(actual, expected)

    def test_uses_local_microsoft_and_attached_screenshots(self) -> None:
        parser = parse_page()
        by_src = {image.get("src", ""): image for image in parser.images}
        expected = {
            "assets/github-copilot-ssms-context.drawio.svg": "GitHub Copilot in SSMS context and decision flow",
            "assets/copilot-ssms-workflow.svg": "Original visual guide to starting GitHub Copilot in SSMS",
            "assets/contoso-ai-ssms-azure-architecture.drawio.svg": "Contoso AI Azure architecture for GitHub Copilot in SSMS",
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

    def test_drawio_architecture_assets_are_editable_and_attributed(self) -> None:
        page = read_page()
        for name, labels in (
            (
                "github-copilot-ssms-context.drawio.svg",
                ("Contoso AI intent", "SSMS context", "GitHub Copilot", "DBA review", "Query Store evidence"),
            ),
            (
                "contoso-ai-ssms-azure-architecture.drawio.svg",
                ("Azure Virtual Network", "Administration subnet", "SQL subnet", "SSMS + GitHub Copilot", "SQL Server on Azure VM"),
            ),
        ):
            svg_path = ROOT / "assets" / name
            source_path = svg_path.with_suffix("")
            content = svg_path.read_text(encoding="utf-8")
            source = source_path.read_text(encoding="utf-8")
            self.assertIn("<svg", content)
            self.assertIn("content=", content)
            ET.parse(source_path)
            for label in labels:
                self.assertIn(label, source)
        azure_svg = (ROOT / "assets" / "contoso-ai-ssms-azure-architecture.drawio.svg").read_text(encoding="utf-8")
        self.assertNotIn('xlink:href="data:image/png"', azure_svg)
        self.assertGreaterEqual(azure_svg.count('xlink:href="data:image/png;base64,'), 7)
        self.assertIn("architecture reference discovered through WebIQ", page)
        self.assertIn("Official Azure Architecture Icons", page)
        self.assertIn("https://learn.microsoft.com/en-us/azure/architecture/icons/", page)

    def test_azure_drawio_arrows_target_the_intended_components(self) -> None:
        source = ROOT / "assets" / "contoso-ai-ssms-azure-architecture.drawio"
        document = ET.parse(source)
        cells = {cell.attrib["id"]: cell for cell in document.findall(".//mxCell") if "id" in cell.attrib}
        expected = {
            "a1": ("facilitator", "pip"),
            "a2": ("pip", "adminnsg"),
            "a3": ("adminnsg", "adminvm"),
            "a4": ("adminvm", "sqlnsg"),
            "a5": ("sqlnsg", "sqlvm"),
            "a7": ("adminvm", "dns"),
            "a8": ("adminsubnet", "nat"),
            "a9": ("sqlsubnet", "nat"),
            "a10": ("nat", "outbound"),
        }
        actual = {
            edge_id: (cells[edge_id].attrib.get("source"), cells[edge_id].attrib.get("target"))
            for edge_id in expected
        }
        self.assertEqual(actual, expected)
        self.assertNotIn("a6", cells, "Query Store is contained in SQL Server, not an external arrow target")
        icon_cells = [cell for cell in cells.values() if "data:image/png%3Bbase64," in cell.attrib.get("style", "")]
        self.assertGreaterEqual(len(icon_cells), 7)

    def test_each_chapter_has_at_least_two_narrative_paragraphs(self) -> None:
        page = read_page()
        for section_id in EXPECTED_STEPS:
            section = re.search(
                rf'(?s)<section id="{re.escape(section_id)}".*?</section>',
                page,
            )
            self.assertIsNotNone(section, section_id)
            self.assertGreaterEqual(
                section.group(0).count('class="narrative"'),
                2,
                f"{section_id} needs at least two narrative paragraphs",
            )

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
        self.assertEqual(len(parser.svgs), 0)
        page = read_page()
        self.assertIn('class="architecture-frame" tabindex="0"', page)
        self.assertIn('aria-label="Scrollable colored architecture diagram"', page)
        self.assertIn('assets/contoso-ai-ssms-azure-architecture.drawio.svg', page)
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

    def test_pages_workflow_deploys_exact_static_artifact(self) -> None:
        workflow_path = ROOT / ".github" / "workflows" / "pages.yml"
        self.assertTrue(workflow_path.is_file())
        workflow = workflow_path.read_text(encoding="utf-8")
        for token in (
            "mkdir -p site/assets",
            "cp index.html site/index.html",
            "cp -R assets/. site/assets/",
            "touch site/.nojekyll",
            "actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d",
            "actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9",
            "actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346",
            "path: site",
        ):
            self.assertIn(token, workflow)
        _, build_marker, after_build = workflow.partition("  build:")
        build_job, deploy_marker, _ = after_build.partition("  deploy:")
        self.assertTrue(build_marker, "Pages workflow is missing the build job")
        self.assertTrue(deploy_marker, "Pages workflow is missing the deploy job")
        self.assertIn("permissions:\n      contents: read\n      pages: read", build_job)
        self.assertNotIn("id-token:", build_job)
        action_pins = re.findall(r"uses:\s+[\w-]+/[\w-]+@([^\s]+)", workflow)
        self.assertTrue(action_pins)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", pin) for pin in action_pins))
        self.assertNotIn("actions/jekyll-build-pages", workflow.lower())


if __name__ == "__main__":
    unittest.main()
