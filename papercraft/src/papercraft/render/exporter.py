"""Build the controlled React renderer and verify it in a real browser."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from papercraft.models import PosterPlan
from papercraft.review import NarrativeRenderMetric, RenderMetrics


@dataclass(frozen=True)
class ExportResult:
    static_dir: Path
    screen_png: Path
    print_png: Path
    a0_pdf: Path
    method_inspector_png: Path
    source_inspector_png: Path
    equation_inspector_png: Path
    metrics: tuple[RenderMetrics, RenderMetrics]


class PosterExporter:
    def __init__(self, project_root: Path, *, chrome_path: Path | None = None) -> None:
        self.project_root = project_root
        self.web_root = project_root / "web"
        self.chrome_path = chrome_path or _find_chrome()
        self._built = False

    def build_web(self) -> Path:
        if self._built and (self.web_root / "dist" / "index.html").exists():
            return self.web_root / "dist"
        if not (self.web_root / "node_modules").exists():
            subprocess.run(["npm", "install"], cwd=self.web_root, check=True)
        subprocess.run(["npm", "run", "build"], cwd=self.web_root, check=True)
        self._built = True
        return self.web_root / "dist"

    def write_static_bundle(
        self,
        *,
        bundle: dict,
        source_assets_dir: Path,
        output_dir: Path,
    ) -> Path:
        distribution = self.build_web()
        static_dir = output_dir / "interactive"
        if static_dir.exists():
            shutil.rmtree(static_dir)
        shutil.copytree(distribution, static_dir)
        _make_file_url_compatible(static_dir / "index.html")
        asset_dir = static_dir / "assets" / "source"
        asset_dir.mkdir(parents=True, exist_ok=True)
        if source_assets_dir.exists():
            for source in source_assets_dir.glob("*"):
                if source.is_file():
                    shutil.copy2(source, asset_dir / source.name)
        payload = dict(bundle)
        payload["asset_base"] = "./assets/source"
        (static_dir / "poster_data.js").write_text(
            "window.__PAPERCRAFT_POSTER__ = "
            + json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
            + ";\n",
            encoding="utf-8",
        )
        return static_dir
    def export(
        self,
        *,
        bundle: dict,
        plan: PosterPlan,
        source_assets_dir: Path,
        output_dir: Path,
        render_revision: int = 1,
    ) -> ExportResult:
        static_dir = self.write_static_bundle(
            bundle=bundle,
            source_assets_dir=source_assets_dir,
            output_dir=output_dir,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        screen_png = output_dir / "screen-16x9.png"
        print_png = output_dir / "print-a0-preview.png"
        method_inspector_png = output_dir / "method-inspector.png"
        source_inspector_png = output_dir / "source-inspector.png"
        equation_inspector_png = output_dir / "equation-inspector.png"
        pdf_dir = self.project_root / "output" / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        a0_pdf = pdf_dir / f"{plan.paper_id}-a0.pdf"

        from playwright.sync_api import sync_playwright

        with _serve(static_dir) as base_url, sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=str(self.chrome_path) if self.chrome_path else None,
                args=["--allow-file-access-from-files"],
            )
            page = browser.new_page(viewport={"width": 1920, "height": 1200})
            page.goto(f"{base_url}/index.html?profile=screen_16_9", wait_until="networkidle")
            page.wait_for_selector("[data-narrative-role='problem']")
            page.locator("#poster-canvas").screenshot(path=str(screen_png))
            screen_metrics = _measure(page, plan, "screen_16_9", render_revision)

            method_button = page.get_by_role("button", name="Open Method Inspector")
            if method_button.count():
                method_button.click()
                page.wait_for_selector(".method-inspector")
                page.locator(".method-inspector").screenshot(path=str(method_inspector_png))
                source_button = page.locator(".method-inspector .source-button")
                if source_button.count():
                    source_button.click()
                    page.wait_for_selector(".source-viewer")
                    page.locator(".source-viewer").screenshot(path=str(source_inspector_png))
                    page.get_by_role("button", name="Close Source Inspector").click()
                page.locator(".method-inspector > header button").click()
            equation_button = page.get_by_role("button", name="Explore all equations")
            if equation_button.count():
                equation_button.click()
                page.wait_for_selector(".equation-inspector")
                page.locator(".equation-inspector").screenshot(path=str(equation_inspector_png))
                page.locator(".equation-inspector > header button").click()

            page.goto(
                f"{base_url}/index.html?profile=print_a0_landscape",
                wait_until="networkidle",
            )
            page.evaluate("document.querySelector('.poster-toolbar').style.display = 'none'")
            print_metrics = _measure(page, plan, "print_a0_landscape", render_revision)
            page.emulate_media(media="print")
            page.pdf(
                path=str(a0_pdf),
                width="1189mm",
                height="841mm",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                prefer_css_page_size=True,
            )

            # The shipped artifact must work when double-clicked in Chrome.
            # This is intentionally checked against file://, not the local test server.
            file_page = browser.new_page(viewport={"width": 1920, "height": 1200})
            browser_errors: list[str] = []
            file_page.on("pageerror", lambda error: browser_errors.append(str(error)))
            file_page.goto((static_dir / "index.html").resolve().as_uri(), wait_until="load")
            file_page.wait_for_timeout(700)
            offline_ok = file_page.locator("[data-narrative-role='problem']").count() == 1
            fallback_visible = file_page.locator("#boot-fallback:visible").count() > 0
            if not offline_ok or fallback_visible or browser_errors:
                details = "; ".join(browser_errors[:3]) or "poster root remained empty"
                raise RuntimeError(f"Offline file:// poster failed to start: {details}")
            file_page.close()
            browser.close()
        import fitz

        with fitz.open(a0_pdf) as rendered_pdf:
            preview = rendered_pdf[0].get_pixmap(matrix=fitz.Matrix(0.625, 0.625), alpha=False)
            preview.save(print_png)
        return ExportResult(
            static_dir=static_dir,
            screen_png=screen_png,
            print_png=print_png,
            a0_pdf=a0_pdf,
            method_inspector_png=method_inspector_png,
            source_inspector_png=source_inspector_png,
            equation_inspector_png=equation_inspector_png,
            metrics=(screen_metrics, print_metrics),
        )


def _make_file_url_compatible(index_path: Path) -> None:
    """Turn Vite's bundled module scripts into file://-safe classic scripts."""

    html = index_path.read_text(encoding="utf-8")
    html = re.sub(
        r'<script\s+type="module"(?:\s+crossorigin)?\s+src="([^"]+)"\s*></script>',
        r'<script defer src="\1"></script>',
        html,
    )
    html = html.replace('<link rel="stylesheet" crossorigin ', '<link rel="stylesheet" ')
    index_path.write_text(html, encoding="utf-8")


def _measure(page, plan: PosterPlan, profile: str, revision: int) -> RenderMetrics:
    data = page.evaluate(
        """
        () => {
          const canvas = document.querySelector('#poster-canvas');
          const components = [...document.querySelectorAll('.poster-component')];
          const canvasRect = canvas.getBoundingClientRect();
          const componentRects = components.map(el => el.getBoundingClientRect());
          const area = rect => Math.max(0, rect.width) * Math.max(0, rect.height);
          const clippedArea = (child, parent) => {
            const left=Math.max(child.left,parent.left), right=Math.min(child.right,parent.right);
            const top=Math.max(child.top,parent.top), bottom=Math.min(child.bottom,parent.bottom);
            return Math.max(0,right-left)*Math.max(0,bottom-top);
          };
          const textIsTruncated = root => [...root.querySelectorAll('h1,h2,h3,p,strong,small,span,figcaption')].some(node => {
            const style=getComputedStyle(node);
            const clamp=parseInt(style.webkitLineClamp || '0',10);
            const hiddenClamp=clamp > 0 && node.scrollHeight > node.clientHeight + 2;
            const ellipsis=style.textOverflow === 'ellipsis' && node.scrollWidth > node.clientWidth + 1;
            const authored=/…|[.][.][.]$/.test((node.textContent || '').trim());
            return hiddenClamp || ellipsis || authored;
          });
          const componentDensity = (el, rect) => {
            const selector='.component-kicker,.poster-component > h2,.component-summary,.method-main-figure,.flow-step,.equation-chain > article,.result-comparison > article,.result-source-asset,.gallery-item,.claim-row,.evidence-note';
            const nodes=[...el.querySelectorAll(selector)].filter(node => node.offsetParent !== null);
            let ink=0, weightedX=0, weightedY=0;
            nodes.forEach(node => {
              const nodeRect=node.getBoundingClientRect();
              const visible=clippedArea(nodeRect,rect);
              ink += visible;
              weightedX += visible * (nodeRect.left + nodeRect.width/2);
              weightedY += visible * (nodeRect.top + nodeRect.height/2);
            });
            const utilization=Math.min(1, ink / Math.max(1, area(rect)));
            const cx=ink ? weightedX/ink : rect.left, cy=ink ? weightedY/ink : rect.top;
            const distance=Math.hypot(cx-(rect.left+rect.width/2),cy-(rect.top+rect.height/2));
            const halfDiagonal=Math.max(1,Math.hypot(rect.width/2,rect.height/2));
            return {utilization, centerOffset: Math.min(1,distance/halfDiagonal)};
          };
          const heading = document.querySelector('.paper-heading').getBoundingClientRect();
          const titleNode = document.querySelector('.paper-heading h1');
          const narratives = [...document.querySelectorAll('.narrative-region')].map(el => el.getBoundingClientRect());
          const footer = document.querySelector('.poster-footer').getBoundingClientRect();
          const occupied = componentRects.reduce((sum, rect) => sum + area(rect), 0) + narratives.reduce((sum, rect) => sum + area(rect), 0) + area(heading) + area(footer);
          // Measure the layout area intentionally allocated to visual
          // explanation. Summing selected descendants under-counted sparse
          // diagrams and double-counted nested formula/figure elements, so the
          // result depended on component implementation details rather than
          // the poster's visual/text balance.
          const visual = [...document.querySelectorAll('.poster-component > .component-visual')].reduce((sum, el) => sum + area(el.getBoundingClientRect()), 0);
          const ordered = componentRects.map((rect, index) => ({index, top: rect.top, left: rect.left}))
            .sort((a,b) => Math.abs(a.top-b.top) > 4 ? a.top-b.top : a.left-b.left).map(x => x.index);
          const densityDetails = components.map((el,index) => componentDensity(el,componentRects[index]));
          const densities = densityDetails.map(item => item.utilization);
          const allGaps = [];
          for (let i=0; i<componentRects.length; i++) for (let j=i+1; j<componentRects.length; j++) {
            const a=componentRects[i], b=componentRects[j];
            const horizontal=Math.max(0, Math.max(a.left,b.left)-Math.min(a.right,b.right));
            const vertical=Math.max(0, Math.max(a.top,b.top)-Math.min(a.bottom,b.bottom));
            if (horizontal > 0 && vertical === 0) allGaps.push(horizontal);
            if (vertical > 0 && horizontal === 0) allGaps.push(vertical);
          }
          return {
            occupied: Math.min(1, occupied / area(canvasRect)),
            visual: Math.min(1, visual / componentRects.reduce((sum,r) => sum + area(r), 1)),
            order: ordered,
            imbalance: densities.length ? Math.min(1, Math.max(...densities)-Math.min(...densities)) : 0,
            gap: allGaps.length ? Math.min(...allGaps) : 0,
            // Font ascenders/descenders can make scrollHeight exceed the
            // client box by a few pixels even when no glyph is clipped.
            // Require a meaningful overflow delta before flagging a layout.
            titleOverflow: titleNode ? titleNode.scrollWidth > titleNode.clientWidth + 4 || titleNode.scrollHeight > titleNode.clientHeight + 12 : false,
            narrativeMetrics: [...document.querySelectorAll('.narrative-region')].map(el => {
              const role = [...el.classList].find(value => value.startsWith('narrative-') && value !== 'narrative-region')?.replace('narrative-', '') || 'problem';
              const headline = el.querySelector('h2');
              const body = el.querySelector('p');
              return {
                role,
                headline_clipped: headline ? headline.scrollHeight > headline.clientHeight + 12 : false,
                body_clipped: body ? body.scrollHeight > body.clientHeight + 12 : false,
                headline_overflow: headline ? headline.scrollWidth > headline.clientWidth + 4 : false,
                body_overflow: body ? body.scrollWidth > body.clientWidth + 4 : false,
                text_truncated: textIsTruncated(el),
              };
            }),
            summaryClipped: components.filter(el => {
              const summary = el.querySelector('.component-summary');
              return summary && (summary.scrollHeight > summary.clientHeight + 12 || summary.scrollWidth > summary.clientWidth + 4);
            }).map(el => el.dataset.componentId),
            components: components.map((el, index) => {
              const rect=componentRects[index];
              const body=[...el.querySelectorAll('.component-summary,.flow-step strong,.flow-step p,.claim-row strong,.result-comparison strong,.evidence-note')];
              const sizes=body.map(node => parseFloat(getComputedStyle(node).fontSize)).filter(Number.isFinite);
              const density=densityDetails[index];
              let overlap=false;
              for (let j=0;j<componentRects.length;j++) if (j!==index) {
                const other=componentRects[j];
                if (rect.left < other.right-1 && rect.right > other.left+1 && rect.top < other.bottom-1 && rect.bottom > other.top+1) overlap=true;
              }
              return {
                id: el.dataset.componentId,
                clipped: el.scrollHeight > el.clientHeight + 12 || el.scrollWidth > el.clientWidth + 12 || [...el.querySelectorAll('.component-visual,.safe-formula,.method-flow,.equation-chain,.claim-chain,.result-comparison,.visual-gallery')].some(node => node.scrollHeight > node.clientHeight + 12 || node.scrollWidth > node.clientWidth + 12),
                overlap,
                overflow: rect.left < canvasRect.left-1 || rect.top < canvasRect.top-1 || rect.right > canvasRect.right+1 || rect.bottom > canvasRect.bottom+1,
                label: [...el.querySelectorAll('.result-comparison article > span')].some(node => node.scrollWidth > node.clientWidth + 1),
                truncated: textIsTruncated(el),
                utilization: density.utilization,
                blank: Math.max(0, 1-density.utilization),
                centerOffset: density.centerOffset,
                allocated: Math.min(1, area(rect)/Math.max(1,area(canvasRect))),
                formulaCount: el.querySelectorAll('.safe-formula').length,
                font: sizes.length ? Math.min(...sizes) : 999
              };
            })
          };
        }
        """
    )
    component_ids = [item.component_id for item in plan.components]
    reading_valid = data["order"] == list(range(len(component_ids)))
    is_print = profile == "print_a0_landscape"
    scale = 0.75 if is_print else 1.0
    gap_scale = 25.4 / 96 if is_print else 1.0
    from papercraft.review.deterministic import ComponentRenderMetric

    return RenderMetrics(
        profile=profile,
        render_revision=revision,
        occupied_area_ratio=data["occupied"],
        visual_area_ratio=data["visual"],
        reading_order_valid=reading_valid,
        density_imbalance=data["imbalance"],
        narratives=[NarrativeRenderMetric.model_validate(item) for item in data["narrativeMetrics"]],
        poster_title_overflow=data["titleOverflow"],
        summary_clipped_components=data["summaryClipped"],
        components=[
            ComponentRenderMetric(
                component_id=item["id"],
                clipped=item["clipped"],
                overlap=item["overlap"],
                canvas_overflow=item["overflow"],
                chart_label_clipped=item["label"],
                text_truncated=item["truncated"],
                content_utilization_ratio=item["utilization"],
                blank_area_ratio=item["blank"],
                visual_center_offset=item["centerOffset"],
                allocated_area_ratio=item["allocated"],
                formula_count=item["formulaCount"],
                minimum_font_size=item["font"] * scale,
                minimum_gap=data["gap"] * gap_scale,
            )
            for item in data["components"]
        ],
    )


@contextmanager
def _serve(directory: Path) -> Iterator[str]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _find_chrome() -> Path | None:
    candidates = (
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/chromium"),
    )
    return next((path for path in candidates if path.exists()), None)
