from pathlib import Path

from answer_key import generate_answer_key
from exporter import export_answer_key_pdf, export_exam_pdf
from generator import generate_versions
from parser import parse_exam
from pdf_reader import extract_text_from_pdf


def run_pipeline(input_pdf_path, output_directory, number_of_versions):
    extracted_text = extract_text_from_pdf(input_pdf_path)
    exam = parse_exam(extracted_text)
    versions = generate_versions(exam, number_of_versions)

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    output_files = []

    for version_number, version in enumerate(versions, start=1):
        answer_key = generate_answer_key(version)
        exam_path = output_directory / f"version_{version_number}.pdf"
        answer_key_path = (
            output_directory / f"version_{version_number}_answer_key.pdf"
        )

        export_exam_pdf(version, str(exam_path))
        export_answer_key_pdf(answer_key, str(answer_key_path))
        output_files.append((exam_path, answer_key_path))

    return output_files