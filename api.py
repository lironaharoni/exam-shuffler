from base64 import b64encode
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pymupdf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pypdf.errors import PdfReadError

from document_reader import has_usable_native_text, read_pdf_pages
from exam_analyzer import analyze_exam
from pipeline import run_pipeline


app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/process-exam")
def process_exam(
    file: UploadFile = File(...),
    number_of_versions: int = Form(..., gt=0),
):
    with TemporaryDirectory() as temporary_directory:
        temporary_directory = Path(temporary_directory)
        input_name = Path(file.filename or "exam.pdf").name
        input_path = temporary_directory / input_name
        output_directory = temporary_directory / "output"

        input_path.write_bytes(file.file.read())
        output_files = run_pipeline(
            input_path,
            output_directory,
            number_of_versions,
        )

        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, "w") as zip_file:
            for exam_path, answer_key_path in output_files:
                zip_file.write(exam_path, exam_path.name)
                zip_file.write(answer_key_path, answer_key_path.name)

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=exam_results.zip"
        },
    )


def _embed_visual_data(analysis, pdf_path):
    with pymupdf.open(pdf_path) as document:
        def embed_visual(visual):
            source = visual.get("source_reference")
            if not isinstance(source, dict):
                return

            page_number = source.get("page_number")
            bounds = source.get("bounds")
            if (
                isinstance(page_number, int)
                and 1 <= page_number <= len(document)
                and isinstance(bounds, list)
                and len(bounds) == 4
            ):
                page = document.load_page(page_number - 1)
                clip = pymupdf.Rect(bounds) & page.rect
                if not clip.is_empty and clip.width > 0 and clip.height > 0:
                    pixmap = page.get_pixmap(
                        matrix=pymupdf.Matrix(2, 2),
                        clip=clip,
                        alpha=False,
                    )
                    encoded = b64encode(pixmap.tobytes("png")).decode("ascii")
                    visual["data_url"] = f"data:image/png;base64,{encoded}"

            visual["source_reference"] = {
                key: value for key, value in source.items() if key != "pdf_path"
            }

        for question in analysis["questions"]:
            for visual in question["question_visuals"]:
                embed_visual(visual)
            for choice in question["choices"]:
                for visual in choice["visuals"]:
                    embed_visual(visual)
        for visual in analysis["unassigned_visuals"]:
            embed_visual(visual)


@app.post("/analyze-exam")
def analyze_exam_upload(file: UploadFile = File(...)):
    uploaded_bytes = file.file.read()
    if b"%PDF-" not in uploaded_bytes[:1024]:
        raise HTTPException(
            status_code=400,
            detail={"reason": "invalid_pdf", "message": "Upload a valid PDF."},
        )

    with TemporaryDirectory() as temporary_directory:
        pdf_path = Path(temporary_directory) / "upload.pdf"
        pdf_path.write_bytes(uploaded_bytes)
        try:
            has_native_text = has_usable_native_text(pdf_path)
        except (OSError, ValueError, PdfReadError, pymupdf.FileDataError) as error:
            raise HTTPException(
                status_code=400,
                detail={
                    "reason": "invalid_pdf",
                    "message": "The PDF is corrupt or unreadable.",
                },
            ) from error

        if not has_native_text:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "scanned_pdf_not_supported",
                    "message": "This MVP supports PDFs with native text on every page.",
                },
            )

        try:
            readings = read_pdf_pages(pdf_path)
        except (OSError, ValueError, PdfReadError, pymupdf.FileDataError) as error:
            raise HTTPException(
                status_code=400,
                detail={
                    "reason": "invalid_pdf",
                    "message": "The PDF is corrupt or unreadable.",
                },
            ) from error

        analysis = analyze_exam(readings)
        _embed_visual_data(analysis, pdf_path)
        return analysis