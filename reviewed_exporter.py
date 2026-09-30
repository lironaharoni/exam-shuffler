import base64
import html
import re
import shutil
from pathlib import Path

import pymupdf


_HEBREW_CHOICES = "אבגדהוזחטיכלמנסעפצקרשת"
_FONT_DIRECTORY = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_FILES = (
    "heebo-hebrew-400.ttf",
    "heebo-latin-400.ttf",
)
_CSS = """
@font-face { font-family: ExamHebrew; src: url("heebo-hebrew-400.ttf"); }
@font-face { font-family: ExamLatin; src: url("heebo-latin-400.ttf"); }
body { font-family: ExamHebrew, ExamLatin; direction: rtl; font-size: 11pt; color: #17251d; }
h1 { font-size: 19pt; margin: 0 0 20pt; }
.question { margin: 0 0 17pt; padding: 0 0 10pt; border-bottom: 0.6pt solid #b8c8ba; }
.question-heading { font-size: 12pt; font-weight: bold; line-height: 1.5; }
.question-text { margin: 3pt 0 7pt; line-height: 1.55; white-space: pre-wrap; }
.visual-list { margin: 5pt 0 8pt; }
img { max-width: 270pt; max-height: 190pt; object-fit: contain; }
.choice { margin: 4pt 0; line-height: 1.5; }
.choice-label { font-weight: bold; margin-left: 5pt; }
.choice-text { white-space: pre-wrap; }
.answer { margin: 5pt 0; font-size: 12pt; }
.answer-marker { font-weight: bold; }
.note { margin-top: 16pt; font-size: 10pt; color: #495b4e; }
"""


def _display_label(choices, position):
    if not choices:
        return str(position)
    first_label = str(choices[0].label).strip()
    if first_label.isdigit():
        return str(position)
    if re.fullmatch(r"[A-Za-z]", first_label):
        base = ord(first_label)
        return chr(base + position - 1)
    normalized = first_label.rstrip(".׳'’")
    if normalized in _HEBREW_CHOICES:
        geresh = "׳" if "׳" in first_label else ""
        return _HEBREW_CHOICES[position - 1] + geresh
    return str(position)


def _escaped_text(value):
    return html.escape(value).replace("\r\n", "\n").replace("\n", "<br>")


def _image_html(visuals, assets_directory, counter):
    items = []
    for visual in visuals:
        data_url = visual.data_url
        if data_url is None:
            raise ValueError("A visual image is missing its embedded data.")
        mime_type, encoded = data_url[5:].split(";base64,", 1)
        extension = "png" if mime_type == "image/png" else "jpg"
        filename = f"visual-{counter[0]}.{extension}"
        counter[0] += 1
        image_path = assets_directory / filename
        image_path.write_bytes(base64.b64decode(encoded, validate=True))
        items.append(f'<div class="visual-list"><img src="{filename}" alt="תמונה משויכת"></div>')
    return "".join(items)


def _render_pdf(document_html, file_path, assets_directory):
    for font_file in _FONT_FILES:
        font_path = _FONT_DIRECTORY / font_file
        if not font_path.is_file():
            raise RuntimeError(f"Required bundled PDF font is missing: {font_file}")
        shutil.copyfile(font_path, assets_directory / font_file)
    archive = pymupdf.Archive(str(assets_directory))
    story = pymupdf.Story(document_html, user_css=_CSS, archive=archive)
    writer = pymupdf.DocumentWriter(str(file_path))
    page_rect = pymupdf.Rect(0, 0, 595, 842)
    content_rect = pymupdf.Rect(48, 48, 547, 794)
    has_more = True
    page_count = 0
    try:
        while has_more:
            device = writer.begin_page(page_rect)
            has_more, _ = story.place(content_rect)
            story.draw(device)
            writer.end_page()
            page_count += 1
            if page_count > 500:
                raise ValueError("Generated document exceeds the page limit.")
    finally:
        writer.close()


def export_reviewed_exam_pdf(questions, file_path, assets_directory):
    assets_directory = Path(assets_directory)
    assets_directory.mkdir(parents=True, exist_ok=True)
    counter = [0]
    sections = ['<h1 dir="rtl">מבחן</h1>']

    for question_number, question in enumerate(questions, start=1):
        question_text = _escaped_text(question.text)
        question_visuals = _image_html(
            question.question_visuals,
            assets_directory,
            counter,
        )
        choices_html = []
        for position, choice in enumerate(question.choices, start=1):
            label = _escaped_text(_display_label(question.choices, position))
            text = _escaped_text(choice.text)
            visuals = _image_html(choice.visuals, assets_directory, counter)
            choices_html.append(
                f'<div class="choice" dir="rtl"><span class="choice-label" dir="auto">'
                f'{label}.</span><span class="choice-text" dir="auto">{text}</span>{visuals}</div>'
            )
        sections.append(
            '<section class="question" dir="rtl">'
            f'<div class="question-heading"><span dir="ltr">{question_number}.</span></div>'
            f'<div class="question-text" dir="auto">{question_text}</div>'
            f'{question_visuals}{"".join(choices_html)}</section>'
        )

    _render_pdf("<html><body>" + "".join(sections) + "</body></html>", file_path, assets_directory)


def export_reviewed_answer_key_pdf(questions, answer_positions, file_path, assets_directory):
    assets_directory = Path(assets_directory)
    assets_directory.mkdir(parents=True, exist_ok=True)
    rows = ['<h1 dir="rtl">מפתח תשובות</h1>']
    for question_number, (question, position) in enumerate(
        zip(questions, answer_positions),
        start=1,
    ):
        marker = "—" if position is None else _display_label(question.choices, position)
        rows.append(
            f'<div class="answer" dir="rtl"><span dir="ltr">{question_number}.</span> '
            f'<span class="answer-marker" dir="auto">{_escaped_text(marker)}</span></div>'
        )
    rows.append('<p class="note" dir="rtl">— = תשובה נכונה לא הוגדרה</p>')
    _render_pdf("<html><body>" + "".join(rows) + "</body></html>", file_path, assets_directory)