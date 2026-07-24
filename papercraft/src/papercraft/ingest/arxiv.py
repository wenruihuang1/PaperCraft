"""Small, reproducible arXiv source downloader used by the local CLI."""

from __future__ import annotations

import re
import shutil
import tarfile
import urllib.request
from pathlib import Path


ARXIV_ID_RE = re.compile(r"(?:arxiv\.org|export\.arxiv\.org)/(?:abs|pdf|e-print)/([^/?#]+)", re.I)


def download_arxiv(url: str, output_dir: Path) -> dict[str, str]:
    """Download a versioned arXiv PDF and TeX source into ``output_dir``.

    The returned manifest is deliberately plain data so it can be persisted
    alongside a job without expanding the frozen DocumentIR 1.0 contract.
    """

    match = ARXIV_ID_RE.search(url)
    if not match:
        raise ValueError("expected an arXiv abs, pdf, or e-print URL")
    arxiv_id = match.group(1)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "paper.pdf"
    source_archive = output_dir / "source.tar"
    source_dir = output_dir / "latex"
    if not pdf_path.exists():
        _download(f"https://arxiv.org/pdf/{arxiv_id}", pdf_path)
    if not source_dir.exists():
        _download(f"https://export.arxiv.org/e-print/{arxiv_id}", source_archive)
        source_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(source_archive, "r:*") as archive:
            _safe_extract(archive, source_dir)
    main_tex = next(source_dir.rglob("main.tex"), None)
    if main_tex is None:
        tex_files = sorted(source_dir.rglob("*.tex"))
        if not tex_files:
            raise ValueError("arXiv source archive contains no TeX files")
        main_tex = tex_files[0]
    return {
        "arxiv_id": arxiv_id,
        "requested_url": url,
        "pdf_path": str(pdf_path),
        "latex_root": str(main_tex.parent),
        "main_tex": str(main_tex),
    }


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "PaperCraft/0.1"})
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if root not in target.parents and target != root:
            raise ValueError("arXiv source archive contains an unsafe path")
    archive.extractall(destination)
