from pathlib import Path

from papercraft.render.exporter import _make_file_url_compatible


def test_static_html_can_open_directly_from_file_url(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text(
        '<script type="module" src="./poster_data.js"></script>'
        '<script type="module" crossorigin src="./assets/index.js"></script>'
        '<link rel="stylesheet" crossorigin href="./assets/index.css">',
        encoding="utf-8",
    )

    _make_file_url_compatible(index)

    html = index.read_text(encoding="utf-8")
    assert 'type="module"' not in html
    assert html.index("poster_data.js") < html.index("assets/index.js")
    assert '<script defer src="./poster_data.js"></script>' in html
    assert '<script defer src="./assets/index.js"></script>' in html
    assert "stylesheet\" crossorigin" not in html
