#!/usr/bin/env python3
"""Lightweight PDF text extractor. Runs as standalone process to avoid
   forking the heavy ONNX/fastembed-loaded server process."""
import sys
import subprocess  # nosec B404
import pathlib
import re


def normalize(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_text.py <pdf_path> [output_path]", file=sys.stderr)
        sys.exit(1)

    pdf_path = pathlib.Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    out_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pdf_path.with_suffix(".txt")

    result = subprocess.run(  # nosec
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(f"pdftotext failed: {result.stderr[:200]}", file=sys.stderr)
        sys.exit(1)

    text = normalize(result.stdout)
    out_path.write_text(text, encoding="utf-8")
    print(f"OK chars={len(text)} output={out_path}")


if __name__ == "__main__":
    main()
