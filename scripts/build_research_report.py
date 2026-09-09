"""Build the combined arXiv manuscript, separate papers, and portable source bundles.

Requires an existing pdfLaTeX/latexmk installation. Does not run benchmarks,
install software, or submit/publish anything.
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
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "docs/paper"
BUILD = ROOT / "tmp/paper-build"


def compile_tex(directory, output, stem="research-report"):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    if directory == output:
        raise ValueError("The build directory must be separate from the source directory")
    output.mkdir(parents=True, exist_ok=True)
    # Compile a snapshot using local filenames. Long absolute -outdir paths can
    # wrap in TeX's log and confuse latexmk's auxiliary-file discovery, allowing
    # an old bibliography in the source directory to be mistaken for the result.
    for name, data in source_files(stem, directory, include_bbl=False).items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    # Remove only this document's disposable build products, never source files.
    # A fresh .aux and absent .bbl/.blg force BibTeX to use the current citations.
    for suffix in (".aux", ".bbl", ".blg", ".fdb_latexmk", ".fls", ".log", ".out", ".toc"):
        (output / (stem + suffix)).unlink(missing_ok=True)
    command = ["latexmk", "-norc", "-g", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
               "-synctex=1", f"{stem}.tex"]
    completed = subprocess.run(command, cwd=output,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # Some TeX/BibTeX diagnostics use legacy font encodings. Preserve raw bytes
    # and tolerate those diagnostics when displaying or checking the log.
    (output / "build-output.txt").write_bytes(completed.stdout)
    if completed.returncode:
        raise RuntimeError(completed.stdout[-8000:].decode("utf-8", errors="replace"))
    if not all((output / (stem + suffix)).is_file() for suffix in (".bbl", ".blg")):
        raise RuntimeError("The build did not produce a fresh BibTeX bibliography")
    log = (output / f"{stem}.log").read_text(errors="replace")
    problems = re.findall(r"^.*(?:Overfull|undefined references|Citation .* undefined|"
                          r"Undefined control sequence).*$", log, re.MULTILINE)
    if problems:
        raise RuntimeError("Unresolved LaTeX issues:\n" + "\n".join(problems))


def source_files(stem, directory=None, include_bbl=True):
    """Collect literal TeX inputs so each bundle has exactly one document root."""
    directory = PAPER if directory is None else Path(directory)
    directory = directory.resolve()
    names = set()
    pending = [directory / f"{stem}.tex"]
    while pending:
        path = pending.pop().resolve()
        if not path.is_relative_to(directory):
            raise ValueError("TeX input lies outside the paper directory")
        name = path.relative_to(directory).as_posix()
        if name in names:
            continue
        names.add(name)
        for child in re.findall(r"\\(?:input|include)\{([^{}]+)\}", path.read_text()):
            pending.append(directory / (child if Path(child).suffix else child + ".tex"))
    names.update(["references.bib", "arxiv.sty", "TEMPLATE-LICENSE", "template-provenance.json"])
    if include_bbl:
        names.add(f"{stem}.bbl")
    return {name: (directory / name).read_bytes() for name in sorted(names)}


def build_document(stem, check_bundle):
    build = BUILD / stem
    compile_tex(PAPER, build, stem)
    pdf = ROOT / f"output/pdf/{stem}.pdf"
    bundle = ROOT / f"output/arxiv/{stem}-source.tar.gz"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    bundle.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(build / f"{stem}.pdf", pdf)
    # Keep the compiled bibliography beside the source as required for portable
    # pdfLaTeX rebuilding, as well as inside the submission source package.
    shutil.copyfile(build / f"{stem}.bbl", PAPER / f"{stem}.bbl")
    # Package the exact snapshot that produced the PDF, including its new .bbl.
    files = source_files(stem, build)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size, item.mtime, item.mode = len(data), 0, 0o644
            archive.addfile(item, io.BytesIO(data))
    with bundle.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(buffer.getvalue())
    if check_bundle:
        # Read the actual finished archive, accepting only the explicitly
        # packaged regular files. No files from the development build leak in.
        with tempfile.TemporaryDirectory(prefix="paper-check-", dir=ROOT / "tmp") as temporary:
            directory = Path(temporary)
            with tarfile.open(bundle, "r:gz") as archive:
                members = archive.getmembers()
                if sorted(member.name for member in members) != sorted(files):
                    raise RuntimeError("Source archive member mismatch")
                for member in members:
                    if not member.isfile():
                        raise RuntimeError("Unexpected non-file source archive member")
                    data = archive.extractfile(member).read()
                    if data != files[member.name]:
                        raise RuntimeError("Source archive payload mismatch")
                    target = directory / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            compile_tex(directory, directory / "build", stem)
    manifest = {
        "source_files_sha256": {name: hashlib.sha256(data).hexdigest()
                                for name, data in files.items()},
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "source_bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "isolated_bundle_build_passed": check_bundle,
        "result_inputs": json.loads((PAPER / "generated/input-manifest.json").read_text()),
        "compiler": subprocess.run(["pdflatex", "--version"], check=True, text=True,
                                   stdout=subprocess.PIPE).stdout.splitlines()[0],
    }
    (pdf.parent / f"{stem}-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"pdf": str(pdf), "source_bundle": str(bundle),
            "source_files": len(files), "isolated_build": check_bundle}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-bundle", action="store_true",
                        help="also compile each source bundle in an isolated directory")
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT / "scripts/prepare_research_report.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/prepare_combined_report.py")], check=True)
    for stem in ("research-report", "technical-supplement", "combined-report"):
        print(json.dumps(build_document(stem, args.check_bundle)), flush=True)


if __name__ == "__main__":
    main()
