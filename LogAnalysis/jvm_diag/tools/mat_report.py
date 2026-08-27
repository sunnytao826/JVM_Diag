from __future__ import annotations

import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_mat_html_report(heap_file: str, mat_script: str | None = None) -> str:
    """Run Eclipse MAT ParseHeapDump and return the Leak Suspects pages directory."""
    heap_path = Path(heap_file).expanduser().resolve()
    if not heap_path.exists():
        raise FileNotFoundError(f"Heap dump not found: {heap_path}")

    script = mat_script or os.getenv("MAT_PARSE_SCRIPT")
    if not script or not Path(script).exists():
        raise FileNotFoundError(
            "Eclipse MAT ParseHeapDump.sh not found. Set MAT_PARSE_SCRIPT to the script path. "
            "See README for installation notes."
        )

    work_dir = heap_path.parent / heap_path.stem
    work_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        script,
        str(heap_path),
        "org.eclipse.mat.api:suspects",
        "org.eclipse.mat.api:top_components",
    ]
    logger.info("Running MAT: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if result.returncode != 0:
        logger.error("MAT stdout:\n%s", result.stdout)
        logger.error("MAT stderr:\n%s", result.stderr)
        raise RuntimeError(f"MAT failed with exit code {result.returncode}")

    zip_files = list(work_dir.glob(f"{heap_path.stem}_*.zip"))
    zip_files.extend(Path.cwd().glob(f"{heap_path.stem}_*.zip"))
    zip_files = list({z.resolve() for z in zip_files})
    if not zip_files:
        raise RuntimeError(f"No MAT ZIP reports found for {heap_path.stem}_*.zip")

    mat_report_root = work_dir / "mat_report"
    if mat_report_root.exists():
        shutil.rmtree(mat_report_root)
    mat_report_root.mkdir()

    leak_suspects_dir = None
    for zip_path in zip_files:
        extract_to = mat_report_root / zip_path.stem
        extract_to.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_to)
        if "Leak_Suspects" in zip_path.stem:
            leak_suspects_dir = extract_to

    if leak_suspects_dir is None:
        raise RuntimeError("Leak_Suspects report not found among extracted ZIPs")

    pages_dir = leak_suspects_dir / "pages"
    if not pages_dir.exists():
        pages_dir = leak_suspects_dir
    if not any(pages_dir.glob("*.html")):
        raise RuntimeError(f"No HTML files in Leak_Suspects report: {pages_dir}")
    return str(pages_dir)
