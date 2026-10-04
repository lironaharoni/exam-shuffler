import base64
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import pytest
from fastapi.testclient import TestClient

from api import app
import reviewed_exporter
from reviewed_exporter import export_reviewed_answer_key_pdf
from reviewed_exporter import export_reviewed_exam_pdf
from reviewed_generation import (
    GenerationSettings,
    ReviewedExam,
    apply_answer_source,
    build_generation_questions,
    generate_reviewed_versions,
)


client = TestClient(app)


def image_data_url(color):
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
    pixmap.clear_with(color)
    encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    pixmap = None
    return f"data:image/png;base64,{encoded}"


def make_choice(identity, label, text, visuals=None):
    return {
        "reviewId": identity,
        "label": label,
        "text": text,
        "visuals": visuals or [],
    }


def make_question(identity, number, text, choices, correct_choice_id=None, included=True, visuals=None):
    return {
        "reviewId": identity,
        "number": number,
        "text": text,
        "page_number": 1,
        "question_visuals": visuals or [],
        "choices": choices,
        "correct_choice_id": correct_choice_id,
        "included": included,
    }


def make_reviewed_exam(questions, answer_source=None, preamble=None):
    return ReviewedExam.model_validate({
        "questions": questions,
        "answer_source": answer_source or {"mode": "manual", "position": None},
        "preamble": preamble or {"enabled": True, "lines": []},
    })


class ReverseRandom:
    def shuffle(self, values):
        values.reverse()


def test_generation_adapter_omits_excluded_questions_and_preserves_review_data():
    q_image = image_data_url(0xCC0000)
    c_image = image_data_url(0x0000CC)
    included = make_question(
        "q-included",
        8,
        "שאלה מעורבת E. coli",
        [
            make_choice("choice-a", "A", "alpha", [{"data_url": c_image}]),
            make_choice("choice-b", "B", "beta"),
        ],
        "choice-b",
        visuals=[{"data_url": q_image}],
    )
    excluded = make_question("q-excluded", 9, "", [], included=False)

    converted = build_generation_questions(make_reviewed_exam([included, excluded]))

    assert len(converted) == 1
    assert converted[0].review_id == "q-included"
    assert converted[0].text == "שאלה מעורבת E. coli"
    assert converted[0].question_visuals[0].data_url == q_image
    assert converted[0].choices[0].review_id == "choice-a"
    assert converted[0].choices[0].visuals[0].data_url == c_image
    assert converted[0].correct_choice_id == "choice-b"


def test_same_answer_source_maps_by_position_and_flags_missing_position():
    analysis = {
        "questions": [
            {"choices": [{"label": "A"}, {"label": "B"}], "correct_answer_label": None},
            {"choices": [{"label": "1"}], "correct_answer_label": None},
        ]
    }

    result = apply_answer_source(analysis, "same_position", 2)

    assert result["questions"][0]["correct_answer_label"] == "B"
    assert result["questions"][0]["answer_source_attention"] is None
    assert result["questions"][1]["correct_answer_label"] is None
    assert "מיקום 2" in result["questions"][1]["answer_source_attention"]
    assert result["answer_source"] == {"mode": "same_position", "position": 2}


def create_native_exam_pdf():
    document = pymupdf.open()
    page = document.new_page()
    for index, text in enumerate((
        "1. Which item is second?",
        "A. alpha",
        "B. beta",
        "C. gamma",
        "D. delta",
    )):
        page.insert_text((50, 80 + index * 30), text)
    output = document.tobytes()
    document.close()
    return output


def test_analyze_endpoint_applies_same_answer_source_by_position():
    response = client.post(
        "/analyze-exam",
        files={"file": ("position.pdf", create_native_exam_pdf(), "application/pdf")},
        data={"answer_source": "same_position", "same_answer_position": "2"},
    )

    assert response.status_code == 200
    analysis = response.json()
    assert analysis["answer_source"] == {"mode": "same_position", "position": 2}
    assert analysis["questions"][0]["correct_answer_label"] == "B"


def test_analyze_endpoint_defers_same_position_choice_until_after_analysis():
    response = client.post(
        "/analyze-exam",
        files={"file": ("position.pdf", create_native_exam_pdf(), "application/pdf")},
        data={"answer_source": "same_position"},
    )

    assert response.status_code == 200
    analysis = response.json()
    assert analysis["answer_source"] == {"mode": "same_position", "position": None}
    assert analysis["questions"][0]["correct_answer_label"] is None


def test_no_known_answers_clears_existing_answers_but_manual_preserves_them():
    analysis = {"questions": [{"choices": [{"label": "A"}], "correct_answer_label": "A"}]}

    no_answers = apply_answer_source(analysis, "none")
    assert no_answers["questions"][0]["correct_answer_label"] is None
    analysis["questions"][0]["correct_answer_label"] = "A"
    manual = apply_answer_source(analysis, "manual")
    assert manual["questions"][0]["correct_answer_label"] == "A"


def test_choice_and_question_shuffle_recalculate_answer_positions_without_mutation():
    question_one = make_question(
        "q-one",
        1,
        "first question",
        [make_choice("one-a", "A", "first"), make_choice("one-b", "B", "second")],
        "one-a",
    )
    question_two = make_question(
        "q-two",
        2,
        "second question",
        [make_choice("two-a", "A", "red"), make_choice("two-b", "B", "blue")],
        "two-b",
    )
    reviewed_exam = make_reviewed_exam([question_one, question_two])
    settings = GenerationSettings(
        number_of_versions=1,
        shuffle_questions=True,
        shuffle_choices=True,
    )

    version = generate_reviewed_versions(reviewed_exam, settings, ReverseRandom())[0]

    assert [question.review_id for question in version.questions] == ["q-two", "q-one"]
    assert version.answer_positions == [1, 2]
    assert version.questions[0].choices[0].review_id == "two-b"
    assert [question.review_id for question in reviewed_exam.questions] == ["q-one", "q-two"]
    assert [choice.review_id for choice in reviewed_exam.questions[0].choices] == ["one-a", "one-b"]


def test_unknown_correct_answer_stays_null_and_all_unknown_exam_generates():
    question = make_question(
        "q-unknown",
        1,
        "unknown answer",
        [make_choice("unknown-a", "A", "first"), make_choice("unknown-b", "B", "second")],
    )
    reviewed_exam = make_reviewed_exam([question])

    versions = generate_reviewed_versions(
        reviewed_exam,
        GenerationSettings(number_of_versions=2, shuffle_questions=False, shuffle_choices=True),
        ReverseRandom(),
    )

    assert len(versions) == 2
    assert all(version.answer_positions == [None] for version in versions)


def test_answer_key_uses_unknown_marker_for_partial_answers(tmp_path):
    questions = build_generation_questions(make_reviewed_exam([
        make_question(
            "q-known",
            1,
            "known",
            [make_choice("known-a", "A", "one"), make_choice("known-b", "B", "two")],
            "known-a",
        ),
        make_question(
            "q-unknown",
            2,
            "unknown",
            [make_choice("unknown-a", "A", "one"), make_choice("unknown-b", "B", "two")],
        ),
    ]))
    output = tmp_path / "key.pdf"
    export_reviewed_answer_key_pdf(questions, [1, None], output, tmp_path / "assets")

    document = pymupdf.open(output)
    text = "\n".join(page.get_text() for page in document).replace("\xa0", " ")
    document.close()

    assert "1" in text
    assert "—" in text
    assert "תשובה נכונה לא הוגדרה" in text


def test_reviewed_pdf_uses_bundled_font_without_windows_font_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("WINDIR", str(tmp_path / "missing-windows-install"))
    font_directory = Path(reviewed_exporter.__file__).resolve().parent / "assets" / "fonts"
    monkeypatch.setattr(reviewed_exporter, "_FONT_DIRECTORY", font_directory)
    question = make_question(
        "portable-q1",
        1,
        "שאלה מעורבת E. coli",
        [
            make_choice("portable-c1", "A", "תשובה באנגלית E. coli", [{"data_url": image_data_url(0x336699)}]),
            make_choice("portable-c2", "B", "תשובה נוספת"),
        ],
        visuals=[{"data_url": image_data_url(0x993366)}],
    )
    reviewed_question = make_reviewed_exam([question]).questions[0]
    output_path = tmp_path / "portable.pdf"

    export_reviewed_exam_pdf(
        [reviewed_question],
        output_path,
        tmp_path / "assets",
    )

    document = pymupdf.open(output_path)
    text = " ".join(page.get_text() for page in document).replace("\xa0", " ")
    fonts = [font[3] for page in document for font in page.get_fonts(full=True)]
    images = sum(len(page.get_image_info()) for page in document)
    assert len(document) == 1
    assert "שאלה מעורבת" in text
    assert "E. coli" in text
    assert "Heebo" in " ".join(fonts)
    assert images == 2
    document.close()


def test_shuffle_keeps_question_and_choice_visuals_with_their_ids():
    q_one_visual = image_data_url(0xCC0000)
    q_two_visual = image_data_url(0x00CC00)
    choice_visual = image_data_url(0x0000CC)
    questions = [
        make_question(
            "q-one",
            1,
            "first",
            [
                make_choice("one-a", "A", "red", [{"data_url": choice_visual}]),
                make_choice("one-b", "B", "blue"),
            ],
            "one-a",
            visuals=[{"data_url": q_one_visual}],
        ),
        make_question(
            "q-two",
            2,
            "second",
            [make_choice("two-a", "A", "one"), make_choice("two-b", "B", "two")],
            visuals=[{"data_url": q_two_visual}],
        ),
    ]
    versions = generate_reviewed_versions(
        make_reviewed_exam(questions),
        GenerationSettings(number_of_versions=1, shuffle_questions=True, shuffle_choices=True),
        ReverseRandom(),
    )

    shuffled = versions[0].questions
    assert shuffled[0].review_id == "q-two"
    assert shuffled[0].question_visuals[0].data_url == q_two_visual
    assert shuffled[1].question_visuals[0].data_url == q_one_visual
    visual_choice = next(choice for choice in shuffled[1].choices if choice.review_id == "one-a")
    assert visual_choice.visuals[0].data_url == choice_visual


def test_generate_versions_endpoint_returns_expected_zip_and_partial_keys():
    q_visual = image_data_url(0xCC0000)
    c_visual = image_data_url(0x0000CC)
    payload = {
        "reviewed_exam": {
            "answer_source": {"mode": "none", "position": None},
            "questions": [
                make_question(
                    "q-one",
                    1,
                    "שאלה בעברית E. coli",
                    [
                        make_choice("one-a", "A", "alpha", [{"data_url": c_visual}]),
                        make_choice("one-b", "B", "beta"),
                    ],
                    visuals=[{"data_url": q_visual}],
                ),
                make_question(
                    "q-excluded",
                    2,
                    "excluded question",
                    [make_choice("excluded-a", "A", "one"), make_choice("excluded-b", "B", "two")],
                    included=False,
                ),
            ],
        },
        "settings": {
            "number_of_versions": 3,
            "shuffle_questions": True,
            "shuffle_choices": True,
        },
    }

    response = client.post("/generate-versions", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == sorted([
            "exam-version-A.pdf",
            "answer-key-A.pdf",
            "exam-version-B.pdf",
            "answer-key-B.pdf",
            "exam-version-C.pdf",
            "answer-key-C.pdf",
        ])
        exam = pymupdf.open(stream=archive.read("exam-version-A.pdf"), filetype="pdf")
        exam_text = "\n".join(page.get_text() for page in exam).replace("\xa0", " ")
        assert "שאלה" in exam_text
        assert "E. coli" in exam_text
        assert "excluded question" not in exam_text
        assert sum(len(page.get_images(full=True)) for page in exam) >= 2
        exam.close()

        answer_key = pymupdf.open(
            stream=archive.read("answer-key-A.pdf"),
            filetype="pdf",
        )
        key_text = "\n".join(page.get_text() for page in answer_key).replace("\xa0", " ")
        assert "—" in key_text
        assert "תשובה נכונה לא הוגדרה" in key_text
        answer_key.close()


def test_generation_endpoint_rejects_invalid_payloads():
    response = client.post(
        "/generate-versions",
        json={
            "reviewed_exam": {
                "questions": [make_question("q1", 1, "", [])],
                "answer_source": {"mode": "manual", "position": None},
            },
            "settings": {
                "number_of_versions": 11,
                "shuffle_questions": True,
                "shuffle_choices": True,
            },
        },
    )

    assert response.status_code == 422


def test_generation_endpoint_rejects_no_included_questions():
    response = client.post(
        "/generate-versions",
        json={
            "reviewed_exam": {
                "questions": [
                    make_question(
                        "q1",
                        1,
                        "excluded",
                        [make_choice("c1", "A", "one"), make_choice("c2", "B", "two")],
                        included=False,
                    )
                ],
                "answer_source": {"mode": "none", "position": None},
            },
            "settings": {
                "number_of_versions": 1,
                "shuffle_questions": False,
                "shuffle_choices": False,
            },
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("answer_key_mode", "expected_names", "appended"),
    [
        ("separate", {"exam-version-A.pdf", "answer-key-A.pdf"}, False),
        ("appended", {"exam-version-A.pdf"}, True),
        ("both", {"exam-version-A.pdf", "answer-key-A.pdf"}, True),
    ],
)
def test_answer_key_output_modes_control_zip_contents(
    answer_key_mode,
    expected_names,
    appended,
):
    payload = {
        "reviewed_exam": {
            "answer_source": {"mode": "manual", "position": None},
            "questions": [
                make_question(
                    "mode-q1",
                    1,
                    "Mode question",
                    [
                        make_choice("mode-c1", "A", "First choice"),
                        make_choice("mode-c2", "B", "Second choice"),
                    ],
                    "mode-c2",
                )
            ],
        },
        "settings": {
            "number_of_versions": 1,
            "shuffle_questions": False,
            "shuffle_choices": False,
            "answer_key_mode": answer_key_mode,
        },
    }

    response = client.post("/generate-versions", json=payload)

    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == expected_names
        exam = pymupdf.open(
            stream=archive.read("exam-version-A.pdf"),
            filetype="pdf",
        )
        assert (len(exam) > 1) is appended
        exam.close()


def test_reviewed_preamble_is_preserved_and_disabled_preamble_is_not_rendered(tmp_path):
    question = make_question(
        "preamble-q1",
        1,
        "Question after preamble",
        [
            make_choice("preamble-c1", "A", "First"),
            make_choice("preamble-c2", "B", "Second"),
        ],
    )
    preamble = {
        "enabled": True,
        "lines": [
            {"type": "header", "text": "Example University"},
            {"type": "metadata", "text": "Duration: 90 minutes"},
            {"type": "instructions", "text": "Choose one answer"},
        ],
    }
    reviewed_exam = make_reviewed_exam([question], preamble=preamble)
    version = generate_reviewed_versions(
        reviewed_exam,
        GenerationSettings(
            number_of_versions=1,
            shuffle_questions=False,
            shuffle_choices=False,
        ),
    )[0]
    assert [line.text for line in version.preamble_lines] == [
        "Example University",
        "Duration: 90 minutes",
        "Choose one answer",
    ]

    enabled_output = tmp_path / "preamble-enabled.pdf"
    export_reviewed_exam_pdf(
        version.questions,
        enabled_output,
        tmp_path / "preamble-enabled-assets",
        version.preamble_lines,
    )
    enabled_document = pymupdf.open(enabled_output)
    enabled_text = " ".join(page.get_text() for page in enabled_document)
    enabled_document.close()
    assert "Example University" in enabled_text
    assert "Duration: 90 minutes" in enabled_text
    assert "Choose one answer" in enabled_text

    disabled_exam = make_reviewed_exam(
        [question],
        preamble={**preamble, "enabled": False},
    )
    disabled_version = generate_reviewed_versions(
        disabled_exam,
        GenerationSettings(
            number_of_versions=1,
            shuffle_questions=False,
            shuffle_choices=False,
        ),
    )[0]
    disabled_output = tmp_path / "preamble-disabled.pdf"
    export_reviewed_exam_pdf(
        disabled_version.questions,
        disabled_output,
        tmp_path / "preamble-disabled-assets",
        disabled_version.preamble_lines,
    )
    disabled_document = pymupdf.open(disabled_output)
    disabled_text = " ".join(page.get_text() for page in disabled_document)
    disabled_document.close()
    assert "Example University" not in disabled_text
    assert "Choose one answer" not in disabled_text


def _find_word(words, token):
    return next(word for word in words if word[4] == token)


def _nearest_number_on_row(words, token_word, expected_label):
    candidates = [
        word for word in words
        if word[4] == expected_label
        and abs(word[1] - token_word[1]) < 3
    ]
    assert candidates
    return min(candidates, key=lambda word: abs(word[0] - token_word[0]))


def _number_start_on_row(words, token_word, expected_number="1"):
    candidates = [
        word for word in words
        if word[4] == expected_number
        and abs(word[1] - token_word[1]) < 3
    ]
    assert candidates
    number = max(candidates, key=lambda word: word[0])
    periods = [
        word for word in words
        if word[4] == "." and abs(word[1] - token_word[1]) < 3
    ]
    assert periods
    assert any(abs(period[2] - number[0]) < 8 for period in periods)
    return number


def test_pdf_numbering_and_mixed_direction_content_stay_in_visual_rows(tmp_path):
    question = make_question(
        "mixed-q1",
        1,
        "שאלה MixedStemToken בעברית RNA polymerase DNA E. coli 2 + 5 3' 5' COOH",
        [
            make_choice("mixed-c1", "A", "ChoiceTokenOne DNA 2 + 5"),
            make_choice("mixed-c2", "B", "ChoiceTokenTwo E. coli COOH"),
        ],
    )
    reviewed_question = make_reviewed_exam([question]).questions[0]
    output = tmp_path / "mixed.pdf"
    export_reviewed_exam_pdf(
        [reviewed_question],
        output,
        tmp_path / "mixed-assets",
    )

    document = pymupdf.open(output)
    words = document[0].get_text("words")
    text = " ".join(word[4] for word in words)
    stem = _find_word(words, "MixedStemToken")
    first_choice = _find_word(words, "ChoiceTokenOne")
    question_number = _number_start_on_row(words, stem)
    choice_number = _number_start_on_row(words, first_choice)
    assert abs(question_number[1] - stem[1]) < 3
    assert abs(choice_number[1] - first_choice[1]) < 3
    assert question_number[0] > stem[0]
    assert choice_number[0] > first_choice[0]
    assert "RNA" in text
    assert "DNA" in text
    assert "E." in text and "coli" in text
    assert "COOH" in text
    assert "+" in text
    numeric_choice_run = [
        next(
            word for word in words
            if word[4] == token and abs(word[1] - first_choice[1]) < 3
        )
        for token in ("2", "+", "5")
    ]
    assert [word[0] for word in numeric_choice_run] == sorted(
        word[0] for word in numeric_choice_run
    )
    document.close()


@pytest.mark.parametrize("embedded_tokens", [
    ["DNA"],
    ["RNA", "polymerase"],
    ["E.", "coli"],
    ["2", "+", "5"],
    ["3'", "/", "5'"],
    ["COOH"],
])
def test_hebrew_ltr_run_keeps_logical_visual_order_without_changing_source(
    tmp_path,
    embedded_tokens,
):
    embedded = " ".join(embedded_tokens)
    source_text = f"לפני {embedded} אחרי"
    question = make_question(
        "bidi-q1",
        1,
        source_text,
        [
            make_choice("bidi-c1", "A", source_text),
            make_choice("bidi-c2", "B", "אפשרות נוספת"),
        ],
    )
    reviewed_question = make_reviewed_exam([question]).questions[0]
    assert reviewed_question.text == source_text
    assert reviewed_question.choices[0].text == source_text

    output = tmp_path / "bidi.pdf"
    export_reviewed_exam_pdf(
        [reviewed_question],
        output,
        tmp_path / "bidi-assets",
    )

    document = pymupdf.open(output)
    words = document[0].get_text("words")
    prefix = _find_word(words, "לפני")
    suffix = _find_word(words, "אחרי")
    run = [_find_word(words, token) for token in embedded_tokens]
    number = _number_start_on_row(words, prefix)

    assert all(abs(word[1] - prefix[1]) < 3 for word in [suffix, *run])
    assert number[0] > prefix[0] > run[0][0]
    assert run[-1][2] > suffix[0]
    assert [word[0] for word in run] == sorted(word[0] for word in run)
    document.close()


def large_image_data_url(color):
    pixmap = pymupdf.Pixmap(
        pymupdf.csRGB,
        pymupdf.IRect(0, 0, 500, 350),
        False,
    )
    pixmap.clear_with(color)
    encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    pixmap = None
    return f"data:image/png;base64,{encoded}"


def test_visual_choice_label_stays_with_image_across_pagination(tmp_path):
    choices = [
        make_choice(
            f"visual-c{index}",
            str(index),
            f"VisualChoiceToken{index}",
            [{"data_url": large_image_data_url(0x220000 * index)}],
        )
        for index in range(1, 6)
    ]
    reviewed_question = make_reviewed_exam([
        make_question("visual-q1", 1, "Image choices", choices),
    ]).questions[0]
    output = tmp_path / "visual-pagination.pdf"
    export_reviewed_exam_pdf(
        [reviewed_question],
        output,
        tmp_path / "visual-pagination-assets",
    )

    document = pymupdf.open(output)
    assert len(document) > 1
    image_count = 0
    for page in document:
        words = page.get_text("words")
        for image in page.get_image_info():
            image_count += 1
            image_top = image["bbox"][1]
            labels = [
                word for word in words
                if word[4].rstrip(".").isdigit()
                and word[3] <= image_top + 2
                and image_top - word[3] < 45
            ]
            assert labels, "a visual choice image was orphaned from its numeric label"
    assert image_count == 5
    document.close()
