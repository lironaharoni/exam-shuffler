import argparse
import json

from document_reader import read_pdf_pages


def main():
    parser = argparse.ArgumentParser(
        description="Read native PDF text or use local Hebrew/English OCR"
    )
    parser.add_argument("pdf", help="Path to the source PDF")
    parser.add_argument("--page", type=int, help="Read only this one-based page")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    if args.page is not None:
        try:
            pages = read_pdf_pages(args.pdf, page_numbers=[args.page])
        except ValueError as error:
            parser.error(str(error))
    else:
        pages = read_pdf_pages(args.pdf)

    rendered = json.dumps(
        [page.to_dict() for page in pages], ensure_ascii=False, indent=2
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()