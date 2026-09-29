"""Read native PDF text and fall back to local Hebrew/English OCR per page."""

from dataclasses import asdict, dataclass
import csv
import io
import os
from pathlib import Path
import shutil
import subprocess

import pymupdf
from pypdf import PdfReader


DEFAULT_OCR_LANGUAGES = "heb+eng"
DEFAULT_NATIVE_TEXT_THRESHOLD = 40
DEFAULT_OCR_TIMEOUT = 120


@dataclass(frozen=True)
class PageReading:
    page_number: int
    extracted_text: str
    source_type: str
    visual_content_detected: bool
    visual_regions: list
    text_lines: list
    page_bounds: list
    page_image_reference: dict | None

    def to_dict(self):
        return asdict(self)


def _find_tesseract(executable=None):
    executable = executable or os.environ.get("TESSERACT_CMD")
    if executable:
        if Path(executable).is_file():
            return str(executable)
        resolved = shutil.which(executable)
        if resolved:
            return resolved
        raise RuntimeError(f"Tesseract executable not found: {executable}")

    resolved = shutil.which("tesseract")
    if resolved:
        return resolved

    for program_directory in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ):
        if program_directory:
            candidate = Path(program_directory) / "Tesseract-OCR" / "tesseract.exe"
            if candidate.is_file():
                return str(candidate)

    raise RuntimeError(
        "Tesseract is required for scanned pages. Install Tesseract OCR with "
        "the Hebrew (heb) and English (eng) language data, or set TESSERACT_CMD."
    )


def _visual_regions(page, is_ocr_page, source_pdf, page_number):
    regions = []

    def add_region(region_type, bounds, **details):
        region_number = len(regions) + 1
        bounds = [round(value, 2) for value in bounds]
        regions.append({
            "id": f"page-{page_number}-visual-{region_number}",
            "type": region_type,
            "page_number": page_number,
            "bounds": bounds,
            "source_reference": {
                "pdf_path": str(source_pdf),
                "page_number": page_number,
                "bounds": bounds,
                **details,
            },
        })

    for image in page.get_image_info(xrefs=True):
        bounds = image["bbox"]
        image_area = max(0, bounds[2] - bounds[0]) * max(
            0, bounds[3] - bounds[1]
        )
        page_area = max(1, page.rect.width * page.rect.height)
        if is_ocr_page and image_area / page_area >= 0.8:
            continue
        add_region(
            "image",
            bounds,
            xref=image.get("xref"),
            width=image.get("width"),
            height=image.get("height"),
        )

    drawings = page.get_drawings()
    for drawing in drawings:
        bounds = drawing.get("rect")
        if bounds:
            width = bounds.width
            height = bounds.height
            if width <= 80 and height <= 80 and width * height <= 200:
                continue
            add_region("vector_graphic", bounds)

    return regions


def _text_line_regions(text_page, page_height):
    baselines = []

    def collect(text, matrix, text_matrix, font, font_size):
        if not text.strip():
            return
        x = matrix[0] * text_matrix[4] + matrix[2] * text_matrix[5] + matrix[4]
        y = matrix[1] * text_matrix[4] + matrix[3] * text_matrix[5] + matrix[5]
        try:
            width = font.get_width(text) * font_size / 1000
        except (AttributeError, TypeError, ValueError):
            width = len(text) * font_size * 0.5
        top = page_height - y - font_size * 0.8
        bottom = page_height - y + font_size * 0.2
        baselines.append((y, x, x + max(width, 0), top, bottom))

    text_page.extract_text(visitor_text=collect)
    rows = []
    for baseline, x0, x1, top, bottom in sorted(baselines, key=lambda item: -item[0]):
        if not rows or abs(rows[-1]["baseline"] - baseline) > 1.5:
            rows.append({
                "baseline": baseline,
                "x0": x0,
                "x1": x1,
                "top": top,
                "bottom": bottom,
            })
        else:
            row = rows[-1]
            row["x0"] = min(row["x0"], x0)
            row["x1"] = max(row["x1"], x1)
            row["top"] = min(row["top"], top)
            row["bottom"] = max(row["bottom"], bottom)

    source_lines = [
        line for line in (text_page.extract_text() or "").splitlines()
        if line.strip()
    ]
    if len(rows) != len(source_lines):
        return []

    return [
        {
            "line_index": line_index,
            "bounds": [
                round(row["x0"], 2),
                round(row["top"], 2),
                round(row["x1"], 2),
                round(row["bottom"], 2),
            ],
        }
        for line_index, row in enumerate(rows)
    ]


def has_usable_native_text(
    pdf_path, *, native_text_threshold=DEFAULT_NATIVE_TEXT_THRESHOLD
):
    """Return whether every page has enough native text to avoid OCR."""
    pages = PdfReader(str(pdf_path)).pages
    return bool(pages) and all(
        sum(
            not character.isspace()
            for character in (page.extract_text() or "")
        ) >= native_text_threshold
        for page in pages
    )


def _run_tesseract(image_bytes, executable, languages, timeout, output_format=None):
    command = [
        executable,
        "stdin",
        "stdout",
        "-l",
        languages,
        "--psm",
        "3",
    ]
    if output_format:
        command.append(output_format)
    try:
        completed = subprocess.run(
            command,
            input=image_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Tesseract OCR timed out after {timeout} seconds") from error
    except subprocess.CalledProcessError as error:
        details = error.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract OCR failed: {details}") from error
    return completed.stdout.decode("utf-8", errors="replace").strip()


def _ocr_page(page, executable, languages, timeout, pixmap=None):
    pixmap = pixmap or page.get_pixmap(dpi=200, alpha=False)
    return _run_tesseract(
        pixmap.tobytes("png"), executable, languages, timeout
    )


def _ocr_text_lines(page, executable, languages, timeout, extracted_text, pixmap):
    tsv = _run_tesseract(
        pixmap.tobytes("png"), executable, languages, timeout, "tsv"
    )
    groups = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        text = row.get("text")
        if (
            row.get("level") != "5"
            or not isinstance(text, str)
            or not text.strip()
        ):
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        left = int(row["left"])
        top = int(row["top"])
        width = int(row["width"])
        height = int(row["height"])
        if width <= 0 or height <= 0:
            continue
        right = left + width
        bottom = top + height
        group = groups.setdefault(key, {
            "words": [],
            "bounds": [left, top, right, bottom],
        })
        group["bounds"] = [
            min(group["bounds"][0], left),
            min(group["bounds"][1], top),
            max(group["bounds"][2], right),
            max(group["bounds"][3], bottom),
        ]
        scale_x = page.rect.width / pixmap.width
        scale_y = page.rect.height / pixmap.height
        group["words"].append({
            "text": text,
            "confidence": float(row["conf"]),
            "bounds": [
                round(left * scale_x, 2),
                round(top * scale_y, 2),
                round(right * scale_x, 2),
                round(bottom * scale_y, 2),
            ],
        })

    source_lines = [
        line for line in extracted_text.splitlines() if line.strip()
    ]
    if len(groups) != len(source_lines):
        return []

    scale_x = page.rect.width / pixmap.width
    scale_y = page.rect.height / pixmap.height
    text_lines = []
    for line_index, (source_line, group) in enumerate(
        zip(source_lines, groups.values())
    ):
        left, top, right, bottom = group["bounds"]
        reliable_words = [
            word for word in group["words"] if word["confidence"] >= 70
        ]
        text_bounds = None
        if reliable_words:
            text_bounds = [
                min(word["bounds"][0] for word in reliable_words),
                min(word["bounds"][1] for word in reliable_words),
                max(word["bounds"][2] for word in reliable_words),
                max(word["bounds"][3] for word in reliable_words),
            ]
        text_lines.append({
            "line_index": line_index,
            "text": source_line,
            "bounds": [
                round(left * scale_x, 2),
                round(top * scale_y, 2),
                round(right * scale_x, 2),
                round(bottom * scale_y, 2),
            ],
            "words": group["words"],
            "text_bounds": text_bounds,
        })
    return text_lines


def read_pdf_pages(
    pdf_path,
    *,
    page_numbers=None,
    native_text_threshold=DEFAULT_NATIVE_TEXT_THRESHOLD,
    ocr_languages=DEFAULT_OCR_LANGUAGES,
    tesseract_executable=None,
    ocr_timeout=DEFAULT_OCR_TIMEOUT,
):
    """Return one reading record per page, using OCR only for sparse pages.

    Visual regions are reported separately from text. The original PDF remains
    the source of diagrams and image-based answer choices; OCR is text-only.
    """
    path = Path(pdf_path)
    pdf_text_pages = PdfReader(str(path)).pages
    document = pymupdf.open(str(path))
    try:
        if len(pdf_text_pages) != len(document):
            raise ValueError("PDF readers disagree about the page count")

        if page_numbers is None:
            page_indexes = range(len(pdf_text_pages))
        else:
            page_indexes = [page_number - 1 for page_number in page_numbers]
            if any(
                page_index < 0 or page_index >= len(pdf_text_pages)
                for page_index in page_indexes
            ):
                raise ValueError(
                    f"page_numbers must be between 1 and {len(pdf_text_pages)}"
                )

        results = []
        executable = None
        for page_index in page_indexes:
            text_page = pdf_text_pages[page_index]
            native_text = text_page.extract_text() or ""
            useful_characters = sum(not character.isspace() for character in native_text)
            use_native_text = useful_characters >= native_text_threshold
            page = document.load_page(page_index)

            if use_native_text:
                extracted_text = native_text.strip()
                source_type = "native_text"
                text_lines = _text_line_regions(text_page, page.rect.height)
                page_image_reference = None
            else:
                if executable is None:
                    executable = _find_tesseract(tesseract_executable)
                ocr_pixmap = page.get_pixmap(dpi=200, alpha=False)
                extracted_text = _ocr_page(
                    page, executable, ocr_languages, ocr_timeout, ocr_pixmap
                )
                text_lines = _ocr_text_lines(
                    page,
                    executable,
                    ocr_languages,
                    ocr_timeout,
                    extracted_text,
                    ocr_pixmap,
                )
                source_type = "ocr"
                page_image_reference = {
                    "pdf_path": str(path),
                    "page_number": page_index + 1,
                    "bounds": [
                        0.0, 0.0,
                        round(page.rect.width, 2),
                        round(page.rect.height, 2),
                    ],
                    "dpi": 200,
                }

            regions = _visual_regions(
                page, source_type == "ocr", path, page_index + 1
            )
            results.append(PageReading(
                page_number=page_index + 1,
                extracted_text=extracted_text,
                source_type=source_type,
                visual_content_detected=bool(regions),
                visual_regions=regions,
                text_lines=text_lines,
                page_bounds=[
                    round(value, 2)
                    for value in (0, 0, page.rect.width, page.rect.height)
                ],
                page_image_reference=page_image_reference,
            ))
        return results
    finally:
        document.close()