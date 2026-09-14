from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import Response

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