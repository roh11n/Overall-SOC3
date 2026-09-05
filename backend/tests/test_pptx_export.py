"""PPTX export verification tests.

Verifies the /api/export/pptx endpoint produces a native PPTX with:
  1. Zero embedded images (ppt/media/ empty)
  2. Zero <p:pic> elements in any slide XML
  3. Native chart XML files (ppt/charts/chart*.xml) with Excel embeddings
  4. Native tables (a:tbl elements) in appropriate slides
  5. Consistent slide anatomy across the deck
  6. pptx_export.py source has zero matplotlib / add_picture references
"""
import io
import os
import re
import zipfile

import pytest
import requests
from lxml import etree

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    from dotenv import load_dotenv
    load_dotenv("/app/frontend/.env")
    BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@mssp-soc.io"
ADMIN_PASSWORD = "Admin@2026!"

PPTX_EXPORT_PATH = "/app/backend/pptx_export.py"

# XML namespaces used in PPTX
NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}

VARIANTS = [
    ("weekly", "all"),
    ("monthly", "acme-corp"),
    ("quarterly", "globalbank"),
]


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def pptx_files(token):
    """Download all three PPTX variants and cache the raw bytes."""
    out = {}
    for period, tenant_id in VARIANTS:
        r = requests.get(
            f"{API}/export/pptx",
            params={"period": period, "tenant_id": tenant_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,  # AI recs enrichment may be slow
        )
        assert r.status_code == 200, (
            f"export failed for {period}/{tenant_id}: "
            f"{r.status_code} {r.text[:400]}"
        )
        assert r.headers.get("content-type", "").startswith(
            "application/vnd.openxmlformats-officedocument.presentationml"
        )
        out[(period, tenant_id)] = r.content
    return out


# ---------- Source-code assertions ----------
class TestSourceCode:
    """Static assertions on /app/backend/pptx_export.py."""

    def test_source_has_no_matplotlib(self):
        with open(PPTX_EXPORT_PATH, "r") as f:
            src = f.read()
        # Look for any matplotlib usage
        assert "matplotlib" not in src, "pptx_export.py still references matplotlib"
        assert "pyplot" not in src, "pptx_export.py still references pyplot"
        assert "savefig" not in src, "pptx_export.py still references savefig"

    def test_source_has_no_picture_insert(self):
        with open(PPTX_EXPORT_PATH, "r") as f:
            src = f.read()
        assert "add_picture" not in src, "pptx_export.py uses shape.add_picture"
        # No PNG / JPEG rasterization helpers
        assert "from PIL" not in src, "pptx_export.py imports PIL (raster path)"
        for helper in ("_fig_to_png", "render_line(", "render_bar(", "render_pie("):
            assert helper not in src, f"raster helper {helper} still present"

    def test_source_uses_native_chart_api(self):
        with open(PPTX_EXPORT_PATH, "r") as f:
            src = f.read()
        # Must use native python-pptx chart / table APIs
        assert "add_chart" in src, "no native add_chart calls"
        assert "add_table" in src, "no native add_table calls"
        assert "CategoryChartData" in src, "no CategoryChartData usage"

    def test_source_dead_loop_removed(self):
        """Regression: the dead loop over chart.legend.font.__dict__ was flagged
        in iteration_2. It must not reappear."""
        with open(PPTX_EXPORT_PATH, "r") as f:
            src = f.read()
        assert "chart.legend.font.__dict__" not in src, (
            "Dead loop over chart.legend.font.__dict__ still present"
        )

    def test_source_total_slide_count_is_15(self):
        """Regression: footer total must be 15 to match actual deck size,
        not the previous stale value of 12."""
        with open(PPTX_EXPORT_PATH, "r") as f:
            src = f.read()
        assert ("total = 15" in src) or ("total=15" in src), (
            "build_pptx()/_slide_chrome should declare total=15 (matches slide count)"
        )
        assert "total = 12" not in src and "total=12" not in src, (
            "Stale total = 12 must be removed"
        )

    def test_source_no_dashboard_style_imports(self):
        """Regression: consulting deck must not import screenshot / raster libs."""
        with open(PPTX_EXPORT_PATH, "r") as f:
            src = f.read()
        for banned in ("playwright", "selenium", "cairosvg", "wkhtmltopdf",
                       "imageio", "matplotlib.pyplot"):
            assert banned not in src, f"pptx_export.py contains banned import {banned}"


# ---------- PPTX archive assertions ----------
class TestPptxArchive:
    """Inspect each generated .pptx as a ZIP archive."""

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_endpoint_returns_valid_pptx(self, pptx_files, variant):
        data = pptx_files[variant]
        assert data.startswith(b"PK"), "Not a valid ZIP/PPTX"
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert "[Content_Types].xml" in z.namelist()

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_zero_images_in_ppt_media(self, pptx_files, variant):
        data = pptx_files[variant]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            media = [n for n in z.namelist() if n.startswith("ppt/media/")]
        assert media == [], (
            f"Found embedded images in ppt/media/ for {variant}: {media}. "
            "Native deck must contain zero screenshots."
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_zero_pic_elements_in_slides(self, pptx_files, variant):
        data = pptx_files[variant]
        offenders = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = [n for n in z.namelist()
                      if re.match(r"ppt/slides/slide\d+\.xml$", n)]
            assert slides, "No slides found in deck"
            for name in slides:
                xml = z.read(name)
                root = etree.fromstring(xml)
                # Any <p:pic> means an inserted image
                pics = root.findall(".//p:pic", NS)
                if pics:
                    offenders.append((name, len(pics)))
        assert not offenders, (
            f"Found <p:pic> elements (embedded pictures) in {variant}: {offenders}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_native_chart_xml_files_present(self, pptx_files, variant):
        data = pptx_files[variant]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            charts = [n for n in z.namelist()
                      if re.match(r"ppt/charts/chart\d+\.xml$", n)]
        assert len(charts) >= 5, (
            f"Expected >= 5 native chart XML files, got {len(charts)} for {variant}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_chart_type_diversity(self, pptx_files, variant):
        """At least 3 distinct native chart types should exist across the deck."""
        data = pptx_files[variant]
        seen_types = set()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if not re.match(r"ppt/charts/chart\d+\.xml$", name):
                    continue
                root = etree.fromstring(z.read(name))
                for tag in ("doughnutChart", "lineChart", "barChart",
                            "pieChart", "pie3DChart"):
                    if root.find(f".//c:{tag}", NS) is not None:
                        seen_types.add(tag)
        assert len(seen_types) >= 3, (
            f"Only {len(seen_types)} chart types found in {variant}: {seen_types}"
        )
        # Assert the key expected types
        assert "doughnutChart" in seen_types, "no doughnut gauge chart"
        # lineChart or barChart or pieChart is expected
        assert seen_types & {"lineChart", "barChart", "pieChart"}, (
            f"Expected lineChart/barChart/pieChart, got {seen_types}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_native_tables_present(self, pptx_files, variant):
        data = pptx_files[variant]
        table_count = 0
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if not re.match(r"ppt/slides/slide\d+\.xml$", name):
                    continue
                root = etree.fromstring(z.read(name))
                # a:tbl is the native drawingml table element
                table_count += len(root.findall(".//a:tbl", NS))
        assert table_count >= 2, (
            f"Expected >= 2 native <a:tbl> tables in deck, got {table_count} "
            f"for {variant}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_excel_embeddings_present(self, pptx_files, variant):
        """Every native chart backs its data with an embedded xlsx."""
        data = pptx_files[variant]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            charts = [n for n in z.namelist()
                      if re.match(r"ppt/charts/chart\d+\.xml$", n)]
            embeds = [n for n in z.namelist()
                      if n.startswith("ppt/embeddings/")
                      and n.endswith(".xlsx")]
        assert embeds, (
            f"No embedded .xlsx files found for {variant} — charts are not "
            "editable / not truly native"
        )
        # Each chart should have an accompanying spreadsheet
        assert len(embeds) >= len(charts), (
            f"Expected >= {len(charts)} embeddings, got {len(embeds)} for {variant}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_slide_count_and_anatomy(self, pptx_files, variant):
        data = pptx_files[variant]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = sorted(
                n for n in z.namelist()
                if re.match(r"ppt/slides/slide\d+\.xml$", n)
            )
        assert len(slides) >= 12, (
            f"Deck must have >= 12 slides, got {len(slides)} for {variant}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_slides_have_textboxes(self, pptx_files, variant):
        """Consistent theme: content slides each contain multiple text boxes
        (proxy for title-bar + footer + body). We check that every slide has
        at least 2 <p:sp> shapes with a text body."""
        data = pptx_files[variant]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = sorted(
                n for n in z.namelist()
                if re.match(r"ppt/slides/slide\d+\.xml$", n)
            )
            insufficient = []
            for name in slides:
                root = etree.fromstring(z.read(name))
                sps = root.findall(".//p:sp", NS)
                # count shapes containing text
                text_shapes = 0
                for sp in sps:
                    if sp.find(".//a:t", NS) is not None:
                        text_shapes += 1
                if text_shapes < 2:
                    insufficient.append((name, text_shapes))
        # Allow the closing / cover slide to be simple; but total offenders
        # must stay small.
        assert len(insufficient) <= 2, (
            f"Too many slides missing text anatomy in {variant}: {insufficient}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_footer_page_indicators(self, pptx_files, variant):
        """Every '<N> / <M>' footer pill must have M equal to the deck's
        actual slide count, and numerators must be a subset of the
        expected footered-page set. Regression guard for the '/12' bug."""
        data = pptx_files[variant]
        pat = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
        numerators = []
        denominators = set()
        raw_strings = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = sorted(
                n for n in z.namelist()
                if re.match(r"ppt/slides/slide\d+\.xml$", n)
            )
            slide_count = len(slides)
            for name in slides:
                root = etree.fromstring(z.read(name))
                # Every <a:t> text node
                for t in root.findall(".//a:t", NS):
                    txt = (t.text or "").strip()
                    m = pat.match(txt)
                    if m:
                        raw_strings.append(txt)
                        numerators.append(int(m.group(1)))
                        denominators.add(int(m.group(2)))

        # Must have found at least one footer indicator
        assert numerators, (
            f"No 'N / M' footer indicators found in {variant} — "
            "footer may have been dropped"
        )
        # No '/12' anywhere
        assert 12 not in denominators, (
            f"Found '/12' denominator (stale bug) in {variant}. "
            f"Raw strings: {raw_strings}"
        )
        # Exactly one denominator, matching actual slide count
        assert len(denominators) == 1, (
            f"Inconsistent denominators in {variant}: {denominators}, "
            f"raw: {raw_strings}"
        )
        denom = next(iter(denominators))
        assert denom == slide_count, (
            f"Footer denominator {denom} != actual slide count {slide_count} "
            f"in {variant}"
        )
        # Numerators must be subset of expected footered-page set
        # New consulting deck footers pages 2..14 (cover=1 and thank-you=15 unfootered)
        expected_numerators = set(range(2, 15))
        actual_nums = set(numerators)
        assert actual_nums.issubset(expected_numerators), (
            f"Unexpected footer numerators in {variant}: "
            f"{actual_nums - expected_numerators} (raw: {raw_strings})"
        )
        # Every numerator must be < denom (no '13/12'-style errors)
        for n in numerators:
            assert n <= denom, (
                f"Numerator {n} exceeds denominator {denom} in {variant} "
                f"(raw: {raw_strings})"
            )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_deck_size_reasonable(self, pptx_files, variant):
        data = pptx_files[variant]
        size_kb = len(data) / 1024.0
        # Image-heavy decks would blow past 300KB. Native decks stay small.
        assert size_kb < 300, (
            f"Deck too large ({size_kb:.1f} KB) for {variant} — likely embeds images"
        )
        # Sanity floor
        assert size_kb > 20, f"Deck suspiciously small ({size_kb:.1f} KB) for {variant}"


# ---------- Consulting-grade design overhaul assertions ----------
# These verify the deck rewrite (Deloitte/EY/PwC-style storytelling deck)
# and prove — via XML inspection — that the export is NOT a dashboard mirror.

CONTENT_SLIDE_INDICES_1BASED = list(range(3, 13)) + [14]  # slides 3-12 and 14


def _slide_shape_xmls(z, slide_name):
    """Return the parsed XML root for a slide inside the zip."""
    return etree.fromstring(z.read(slide_name))


def _extract_slide_text(root):
    """Return joined text content of every <a:t> in a slide."""
    return "\n".join((t.text or "") for t in root.findall(".//a:t", NS))


class TestConsultingDesignOverhaul:
    """XML-level proof that the deck is a fully designed consulting deck
    (not a dashboard mirror). Covers all bullets in the review request."""

    # ---- 1. Exactly 15 slides ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_exactly_15_slides(self, pptx_files, variant):
        data = pptx_files[variant]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = sorted(
                n for n in z.namelist()
                if re.match(r"ppt/slides/slide\d+\.xml$", n)
            )
        assert len(slides) == 15, (
            f"Expected exactly 15 slides in {variant}, got {len(slides)}"
        )

    # ---- 2. AI EXECUTIVE INSIGHT on every content slide ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_ai_executive_insight_on_content_slides(self, pptx_files, variant):
        data = pptx_files[variant]
        hits = 0
        missing = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = sorted(
                n for n in z.namelist()
                if re.match(r"ppt/slides/slide\d+\.xml$", n)
            )
            # slide file names sort as slide1.xml, slide10.xml, ...  so do
            # a natural-order sort by number:
            slides.sort(key=lambda n: int(re.search(r"slide(\d+)\.xml$", n).group(1)))
            for idx_1based, name in enumerate(slides, start=1):
                if idx_1based not in CONTENT_SLIDE_INDICES_1BASED:
                    continue
                text = _extract_slide_text(_slide_shape_xmls(z, name))
                if "AI EXECUTIVE INSIGHT" in text.upper():
                    hits += 1
                else:
                    missing.append((idx_1based, name))
        assert hits >= 10, (
            f"Expected >= 10 content slides with 'AI EXECUTIVE INSIGHT' in "
            f"{variant}, got {hits}. Missing on: {missing}"
        )

    # ---- 3. NN / 15 footer on every content slide (no cut-off) ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_footer_shows_slash_15_and_no_cutoff(self, pptx_files, variant):
        data = pptx_files[variant]
        pat = re.compile(r"^\s*\d{1,2}\s*/\s*15\s*$")
        found = 0
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = [n for n in z.namelist()
                      if re.match(r"ppt/slides/slide\d+\.xml$", n)]
            for name in slides:
                root = _slide_shape_xmls(z, name)
                for t in root.findall(".//a:t", NS):
                    if pat.match((t.text or "").strip()):
                        found += 1
                        break
        # 13 content/appendix slides (2..14) should each carry a footer pill
        assert found >= 12, (
            f"Expected >= 12 'NN / 15' footer pills in {variant}, got {found}"
        )

    # ---- 4. Insight callout does NOT overlap footer (positional proof) ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_insight_callout_above_footer(self, pptx_files, variant):
        """The insight callout is anchored at y=6.25 in with height 0.72 in
        → bottom edge = 6.97 in ≈ 6379200 EMU, which is < 6420000 EMU
        (the y=7.0 in line just above the footer at y=7.05 in).
        We prove this by scanning every slide for a shape at y=6.25 in
        (5715000 EMU) with height 0.72 in (658368 EMU-ish).
        """
        data = pptx_files[variant]
        # 0.9 in from left = 823012 EMU; y=6.25 in = 5715000 EMU
        # PPTX EMU: 914400 per inch
        expected_y_emu = int(6.25 * 914400)
        expected_h_emu = int(0.72 * 914400)
        max_bottom_allowed = 6420000  # y=7.02 in ≈ just above footer strip
        offenders = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = sorted(
                n for n in z.namelist()
                if re.match(r"ppt/slides/slide\d+\.xml$", n)
            )
            slides.sort(key=lambda n: int(re.search(r"slide(\d+)\.xml$", n).group(1)))
            for idx_1based, name in enumerate(slides, start=1):
                if idx_1based not in CONTENT_SLIDE_INDICES_1BASED:
                    continue
                root = _slide_shape_xmls(z, name)
                # find rounded-rect / rect shapes whose y ~= expected_y_emu
                # (the insight-bar rectangle) and check bottom
                for sp in root.findall(".//p:sp", NS):
                    off = sp.find(".//a:off", NS)
                    ext = sp.find(".//a:ext", NS)
                    if off is None or ext is None:
                        continue
                    y = int(off.get("y", "0"))
                    h = int(ext.get("cy", "0"))
                    # tolerate +/- 40000 EMU jitter
                    if abs(y - expected_y_emu) <= 40000 and abs(h - expected_h_emu) <= 40000:
                        bottom = y + h
                        if bottom > max_bottom_allowed:
                            offenders.append((idx_1based, name, y, h, bottom))
        assert not offenders, (
            f"Insight callout overlaps footer in {variant}: {offenders} "
            f"(bottom must be <= {max_bottom_allowed} EMU)"
        )

    # ---- 5. Consulting design tokens: white bg, navy left rail ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_white_background_and_navy_left_rail(self, pptx_files, variant):
        data = pptx_files[variant]
        # Navy = #1E3A8A → look for srgbClr val="1E3A8A" (case-insensitive)
        navy_pat = re.compile(r"srgbClr[^>]*val=[\"']1E3A8A[\"']", re.IGNORECASE)
        white_pat = re.compile(r"srgbClr[^>]*val=[\"']FFFFFF[\"']", re.IGNORECASE)
        rail_ok = 0
        white_ok = 0
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = sorted(
                n for n in z.namelist()
                if re.match(r"ppt/slides/slide\d+\.xml$", n)
            )
            slides.sort(key=lambda n: int(re.search(r"slide(\d+)\.xml$", n).group(1)))
            for idx_1based, name in enumerate(slides, start=1):
                if idx_1based not in CONTENT_SLIDE_INDICES_1BASED:
                    continue
                raw = z.read(name).decode("utf-8", errors="ignore")
                if white_pat.search(raw):
                    white_ok += 1
                # find a rectangle at x=0 with width <= 100000 EMU filled navy
                root = etree.fromstring(z.read(name))
                for sp in root.findall(".//p:sp", NS):
                    off = sp.find(".//a:off", NS)
                    ext = sp.find(".//a:ext", NS)
                    if off is None or ext is None:
                        continue
                    x = int(off.get("x", "-1"))
                    w = int(ext.get("cx", "0"))
                    if x == 0 and 0 < w <= 100000:
                        # check for navy fill within this shape
                        sp_xml = etree.tostring(sp).decode("utf-8", errors="ignore")
                        if navy_pat.search(sp_xml):
                            rail_ok += 1
                            break
        assert white_ok >= 10, (
            f"Expected >= 10 content slides with a white (#FFFFFF) fill in "
            f"{variant}, got {white_ok}"
        )
        assert rail_ok >= 10, (
            f"Expected >= 10 content slides with a navy (#1E3A8A) left rail "
            f"(x=0, width <=100000 EMU) in {variant}, got {rail_ok}"
        )

    # ---- 6. Chart & widget census ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_native_chart_type_census(self, pptx_files, variant):
        data = pptx_files[variant]
        found = {"doughnutChart": 0, "barChart": 0, "lineChart": 0}
        # column chart is a barChart with barDir=col; bar chart is barDir=bar
        col_chart_count = 0
        bar_chart_count = 0
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if not re.match(r"ppt/charts/chart\d+\.xml$", name):
                    continue
                root = etree.fromstring(z.read(name))
                if root.find(".//c:doughnutChart", NS) is not None:
                    found["doughnutChart"] += 1
                if root.find(".//c:lineChart", NS) is not None:
                    found["lineChart"] += 1
                bc = root.find(".//c:barChart", NS)
                if bc is not None:
                    found["barChart"] += 1
                    bar_dir = bc.find("c:barDir", NS)
                    if bar_dir is not None:
                        if bar_dir.get("val") == "col":
                            col_chart_count += 1
                        elif bar_dir.get("val") == "bar":
                            bar_chart_count += 1
        assert found["doughnutChart"] >= 1, (
            f"Expected >= 1 doughnut chart (posture gauge) in {variant}, "
            f"got {found}"
        )
        assert col_chart_count >= 1, (
            f"Expected >= 1 column chart (severity) in {variant}, "
            f"got col={col_chart_count}"
        )
        assert bar_chart_count >= 1, (
            f"Expected >= 1 bar chart (malware/MITRE) in {variant}, "
            f"got bar={bar_chart_count}"
        )
        assert found["lineChart"] >= 1, (
            f"Expected >= 1 line chart (automation trends) in {variant}, "
            f"got {found}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_at_least_two_native_tables(self, pptx_files, variant):
        data = pptx_files[variant]
        n_tables = 0
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if not re.match(r"ppt/slides/slide\d+\.xml$", name):
                    continue
                root = etree.fromstring(z.read(name))
                n_tables += len(root.findall(".//a:tbl", NS))
        assert n_tables >= 2, (
            f"Expected >= 2 native <a:tbl> tables in {variant}, got {n_tables}"
        )

    # ---- 7. Storytelling narrative titles ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_storytelling_titles_present(self, pptx_files, variant):
        data = pptx_files[variant]
        required_titles = [
            "Executive Summary",
            "Where we are",
            "Threat & Incident Landscape",
            "Speed of Response",
            "Threat Landscape",
            "Detection Coverage",
            "Automation ROI",
            "Client Impact",
            "AI Recommendations",
            "Next Steps",
        ]
        # Concatenate all slide text
        combined = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if not re.match(r"ppt/slides/slide\d+\.xml$", name):
                    continue
                combined.append(_extract_slide_text(_slide_shape_xmls(z, name)))
        all_text = "\n".join(combined)
        missing = [t for t in required_titles if t not in all_text]
        assert not missing, (
            f"Storytelling narrative titles missing from {variant}: {missing}"
        )

    # ---- 8. Client Impact funnel four stages ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_client_impact_funnel_labels_present(self, pptx_files, variant):
        data = pptx_files[variant]
        required = [
            "Total Assets Monitored",
            "Alerts Generated",
            "Incidents Opened",
            "Board Escalations",
        ]
        combined = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if not re.match(r"ppt/slides/slide\d+\.xml$", name):
                    continue
                combined.append(_extract_slide_text(_slide_shape_xmls(z, name)))
        all_text = "\n".join(combined)
        missing = [t for t in required if t not in all_text]
        assert not missing, (
            f"Client Impact funnel stages missing from {variant}: {missing}"
        )

    # ---- 9. Zero images / screenshots  regression (already covered but explicit) ----
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_no_matplotlib_or_screenshots_in_source(self, pptx_files, variant):
        # Read the pptx source
        with open(PPTX_EXPORT_PATH, "r") as f:
            src = f.read()
        for banned in ("matplotlib", "add_picture", "screenshot",
                       ".savefig", "html2image", "playwright"):
            assert banned not in src, (
                f"Source references banned dashboard helper '{banned}'"
            )
        # And zero <p:pic> in every slide of the actual deck
        data = pptx_files[variant]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if not re.match(r"ppt/slides/slide\d+\.xml$", name):
                    continue
                root = etree.fromstring(z.read(name))
                assert not root.findall(".//p:pic", NS), (
                    f"<p:pic> found in {name} for {variant}"
                )

