from pypdf import PdfReader


def extract_text_from_pdf(file_path):
    reader = PdfReader(file_path)

    text = ""

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return text

text = extract_text_from_pdf("example_final.pdf")
with open("extracted_example_final.txt", "w", encoding="utf-8") as file:
    file.write(text)