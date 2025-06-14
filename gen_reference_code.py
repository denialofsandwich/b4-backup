"""Generate the code reference pages and navigation."""

import contextlib
import shutil
from pathlib import Path

app_name = "b4_backup"
reference_path = Path("docs/reference/code")
with contextlib.suppress(FileNotFoundError):
    shutil.rmtree(reference_path)

reference_path.mkdir(parents=True)

for path in sorted(Path(app_name).rglob("*.py")):
    module_path = path.with_suffix("")
    doc_path = path.relative_to(app_name).with_suffix(".md")
    full_doc_path = reference_path / doc_path

    parts = list(module_path.parts)

    if ".ipynb_checkpoints" in parts:
        continue

    if parts[-1] in ["__init__", "__main__"]:
        continue

    print(module_path)
    if module_path.is_relative_to(f"{app_name}/cli"):
        continue

    full_doc_path.parent.mkdir(parents=True, exist_ok=True)
    with full_doc_path.open("w", encoding="utf8") as file:
        file.write(f"::: {'.'.join(parts)}")
