"""Build only the DLP Nova paper and an independently rebuildable source archive.

Requires existing latexmk, pdfLaTeX and BibTeX. Does not run benchmarks, modify
the earlier manuscript, install software, or submit/publish the paper.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "docs/paper"
STEM = "dlp-nova"
BUILD = ROOT / "tmp/paper-build" / STEM
SOURCE_NAMES = ("dlp-nova.tex", "dlp-nova-references.bib", "arxiv.sty",
                "TEMPLATE-LICENSE", "template-provenance.json")
EVIDENCE_NAMES = ("benchmarks/dlp-nova-spatial-results.json",
                  "benchmarks/dlp-nova-example-results.json",
                  "benchmarks/query-preparation-results.json")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compile_snapshot(files, directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Auxiliary products live only in this document's disposable build tree.
    for suffix in (".aux", ".bbl", ".blg", ".fdb_latexmk", ".fls", ".log", ".out"):
        (directory / (STEM + suffix)).unlink(missing_ok=True)
    command = ["latexmk", "-norc", "-g", "-pdf", "-interaction=nonstopmode",
               "-halt-on-error", "-file-line-error", f"{STEM}.tex"]
    result = subprocess.run(command, cwd=directory, capture_output=True)
    output = result.stdout + result.stderr
    (directory / "build-output.txt").write_bytes(output)
    if result.returncode:
        raise RuntimeError(output[-8000:].decode(errors="replace"))
    log = (directory / f"{STEM}.log").read_text(errors="replace")
    problems = re.findall(r"^.*(?:Overfull|undefined references|Citation .* undefined|"
                          r"Undefined control sequence).*$", log, re.MULTILINE)
    if problems:
        raise RuntimeError("Unresolved LaTeX issues:\n" + "\n".join(problems))
    for suffix in (".pdf", ".bbl", ".blg"):
        if not (directory / (STEM + suffix)).is_file():
            raise RuntimeError(f"Build did not produce {STEM}{suffix}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-bundle", action="store_true",
                        help="compile the actual packaged files in an isolated directory")
    args = parser.parse_args()
    files = {name: (PAPER / name).read_bytes() for name in SOURCE_NAMES}
    evidence = {name: (ROOT / name).read_bytes() for name in EVIDENCE_NAMES}
    files.update({"evidence/" + Path(name).name: data for name, data in evidence.items()})
    compile_snapshot(files, BUILD)
    files[f"{STEM}.bbl"] = (BUILD / f"{STEM}.bbl").read_bytes()
    pdf = ROOT / "output/pdf" / f"{STEM}.pdf"
    bundle = ROOT / "output/arxiv" / f"{STEM}-source.tar.gz"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    bundle.parent.mkdir(parents=True, exist_ok=True)
    memory = io.BytesIO()
    with tarfile.open(fileobj=memory, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mtime, entry.mode = len(data), 0, 0o644
            archive.addfile(entry, io.BytesIO(data))
    with bundle.open("wb") as output:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as compressed:
            compressed.write(memory.getvalue())
    if args.check_bundle:
        with tempfile.TemporaryDirectory(prefix="dlp-nova-check-", dir=ROOT / "tmp") as temp:
            extracted = {}
            with tarfile.open(bundle, "r:gz") as archive:
                for member in archive.getmembers():
                    if (not member.isfile() or member.name not in files
                            or member.name in extracted):
                        raise RuntimeError("Unexpected archive member")
                    data = archive.extractfile(member).read()
                    if data != files[member.name]:
                        raise RuntimeError("Archive payload mismatch")
                    extracted[member.name] = data
            if extracted.keys() != files.keys():
                raise RuntimeError("Archive member mismatch")
            compile_snapshot(extracted, Path(temp) / "build")
    shutil.copyfile(BUILD / f"{STEM}.pdf", pdf)
    manifest = {
        "document": "DLP Nova: A Reasoner with Geospatial and Temporal Extensions",
        "source_files_sha256": {name: digest(data) for name, data in sorted(files.items())},
        "evidence_files_sha256": {name: digest(data) for name, data in evidence.items()},
        "build_script_sha256": digest(Path(__file__).read_bytes()),
        "pdf_sha256": digest(pdf.read_bytes()),
        "source_bundle_sha256": digest(bundle.read_bytes()),
        "isolated_bundle_build_passed": args.check_bundle,
        "compiler": subprocess.check_output(["pdflatex", "--version"], text=True).splitlines()[0],
        "publication_status": "local draft; not submitted by this build",
    }
    (pdf.parent / f"{STEM}-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"pdf": str(pdf), "source_bundle": str(bundle),
                      "isolated_build": args.check_bundle}, indent=2))


if __name__ == "__main__":
    main()
