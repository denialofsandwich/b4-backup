import colorsys
import urllib.parse
from pathlib import Path

import requests


def _extract_coverage(content: str) -> int:
    content = content.split('<tr class="total">')[1]
    content = content.split("</tr>")[0]
    content = content.split("<td")[-1]
    content = content.split(">")[1]
    content = content.split("%")[0]

    return int(content)


def _create_badge(title: str, value: str, color: str):
    print(title, value, color)
    title = urllib.parse.quote(title)
    value = urllib.parse.quote(value)
    color = urllib.parse.quote(color)

    path = Path(f"docs/badges/{title}.svg")
    path.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(f"https://img.shields.io/badge/{title}-{value}-{color}", timeout=60)
    path.write_bytes(response.content)


def _create_badge_coverage(value: int):
    ramp = max(50, min(100, value)) / 100 * 0.31
    r, g, b = colorsys.hsv_to_rgb(ramp, 0.93, 0.77)
    _create_badge("coverage", f"{value}%", f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}")


def _create_badge_versions(versions: list[str]):
    _create_badge("python", " | ".join(versions), "blue")


versions = []
for path in Path("htmlcov").glob("*"):
    print(path)
    versions.append(path.name[1:])
    coverage = _extract_coverage((path / "index.html").read_text())
    _create_badge_coverage(coverage)

_create_badge_versions(versions)
