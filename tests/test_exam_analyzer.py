from exam_analyzer import analyze_exam


def _page(
    number, text, visual=False, regions=None, text_lines=None, page_bounds=None
):
    return {
        "page_number": number,
        "extracted_text": text,
        "source_type": "native_text",
        "visual_content_detected": visual,
        "visual_regions": regions or [],
        "text_lines": text_lines or [],
        "page_bounds": page_bounds,
    }


def test_analyzes_numbered_hebrew_question_choices_and_preamble():
    result = analyze_exam([_page(
        1,
        "אוניברסיטת הדוגמה\nבחרו תשובה אחת\n"
        "1. לאיזה אורגניזם?\n1. צמחים\n2. דגים\n"
        "2. כיצד הוא מתרבה?\n1. בדרך א\n2. בדרך ב",
    )])

    assert result["ignored_content"] == [
        {"page_number": 1, "text": "אוניברסיטת הדוגמה", "type": "header"},
        {"page_number": 1, "text": "בחרו תשובה אחת", "type": "instructions"},
    ]
    assert result["questions"] == [
        {
            "number": 1,
            "text": "לאיזה אורגניזם?",
            "choices": [
                {"label": "1", "text": "צמחים", "visuals": []},
                {"label": "2", "text": "דגים", "visuals": []},
            ],
            "question_visuals": [],
            "correct_answer_label": None,
            "page_number": 1,
            "has_visual_content": False,
            "needs_review": False,
        },
        {
            "number": 2,
            "text": "כיצד הוא מתרבה?",
            "choices": [
                {"label": "1", "text": "בדרך א", "visuals": []},
                {"label": "2", "text": "בדרך ב", "visuals": []},
            ],
            "question_visuals": [],
            "correct_answer_label": None,
            "page_number": 1,
            "has_visual_content": False,
            "needs_review": False,
        },
    ]
    assert result["analysis_status"] == "ready"
    assert result["safe_to_generate"] is True
    assert result["analysis_warnings"] == []


def test_preserves_multiline_text_and_flags_ambiguous_or_visual_content():
    result = analyze_exam([
        _page(
            3,
            "11. אילו קבוצות נקשרות?\n"
            "1. 2 + 5\n"
            "2. 2 + 3\n"
            "12. מהו המבנה השניוני?\n"
            "1. רצף\n"
            "13. איזו אפשרות מתאימה?\n"
            "1. \n"
            "2. ",
            visual=True,
            regions=[{"type": "image", "bounds": [10, 10, 40, 40]}],
        ),
        _page(4, "3. \n4. "),
    ])

    questions = result["questions"]
    assert [question["number"] for question in questions] == [11, 12, 13]
    assert questions[0]["choices"][0]["text"] == "2 + 5"
    assert questions[1]["choices"][0]["text"] == "רצף"
    assert [choice["label"] for choice in questions[2]["choices"]] == [
        "1", "2", "3", "4"
    ]
    assert [question["has_visual_content"] for question in questions] == [
        False, False, False
    ]
    assert questions[0]["needs_review"] is False
    assert questions[1]["needs_review"] is False
    assert questions[2]["needs_review"] is True
    assert len(result["unassigned_visuals"]) == 1
    assert result["unassigned_visuals"][0]["needs_review"] is True
    assert result["analysis_status"] == "needs_review"
    assert result["safe_to_generate"] is False


def test_quality_gate_blocks_implausibly_many_choices():
    choices = "\n".join(
        f"{chr(ord('A') + index)}. Option {index + 1}"
        for index in range(13)
    )
    result = analyze_exam([_page(1, f"37. What is correct?\n{choices}")])

    assert len(result["questions"]) == 1
    assert len(result["questions"][0]["choices"]) == 13
    assert result["analysis_status"] == "needs_review"
    assert result["safe_to_generate"] is False
    assert any("exceeding the plausible limit" in warning
               for warning in result["analysis_warnings"])


def _positioned_page(number, lines, bounds, visuals=()):
    return _page(
        number,
        "\n".join(lines),
        visual=bool(visuals),
        regions=list(visuals),
        text_lines=[
            {"line_index": index, "bounds": list(line_bounds)}
            for index, line_bounds in enumerate(bounds)
        ],
        page_bounds=[0, 0, 600, 800],
    )


def _visual(identifier, page_number, bounds):
    return {
        "id": identifier,
        "type": "image",
        "page_number": page_number,
        "bounds": list(bounds),
        "source_reference": {
            "page_number": page_number,
            "bounds": list(bounds),
            "xref": identifier,
        },
    }


def test_associates_stem_and_individual_choices_by_layout_without_page_bleed():
    result = analyze_exam([_positioned_page(
        7,
        [
            "31. What is shown?",
            "A. Alpha",
            "B. Beta",
            "C. Gamma",
            "32. Which item follows?",
            "1. First",
            "2. Second",
        ],
        [
            [410, 90, 500, 108],
            [410, 300, 500, 318],
            [410, 340, 500, 358],
            [410, 380, 500, 398],
            [410, 520, 500, 538],
            [410, 560, 500, 578],
            [410, 600, 500, 618],
        ],
        visuals=[
            _visual("stem", 7, [100, 140, 390, 250]),
            _visual("choice-a", 7, [250, 300, 400, 318]),
            _visual("choice-b", 7, [250, 340, 400, 358]),
        ],
    )])

    first, second = result["questions"]
    assert first["number"] == 31
    assert [visual["id"] for visual in first["question_visuals"]] == ["stem"]
    assert [
        [visual["id"] for visual in choice["visuals"]]
        for choice in first["choices"]
    ] == [["choice-a"], ["choice-b"], []]
    assert first["needs_review"] is False
    assert second["number"] == 32
    assert second["question_visuals"] == []
    assert all(not choice["visuals"] for choice in second["choices"])
    assert result["unassigned_visuals"] == []


def test_associates_choices_across_page_break_before_next_question():
    result = analyze_exam([
        _positioned_page(
            8,
            ["55. Which structure?", "A. First option"],
            [[400, 600, 510, 618], [400, 700, 510, 718]],
        ),
        _positioned_page(
            9,
            ["B. Second option", "56. Select the next item?", "1. One", "2. Two"],
            [[400, 100, 510, 118], [400, 180, 510, 198], [400, 220, 510, 238], [400, 260, 510, 278]],
            visuals=[_visual("continued-choice", 9, [250, 100, 390, 118])],
        ),
    ])

    first, second = result["questions"]
    assert first["number"] == 55
    assert first["page_number"] == 8
    assert [choice["label"] for choice in first["choices"]] == ["A", "B"]
    assert [visual["id"] for visual in first["choices"][1]["visuals"]] == [
        "continued-choice"
    ]
    assert second["number"] == 56
    assert second["has_visual_content"] is False
    assert result["unassigned_visuals"] == []


def test_leaves_visual_between_choice_rows_unassigned_for_review():
    result = analyze_exam([_positioned_page(
        20,
        ["81. Which option?", "A. Alpha", "B. Beta"],
        [[400, 100, 510, 118], [400, 200, 510, 220], [400, 222, 510, 242]],
        visuals=[_visual("ambiguous", 20, [250, 210, 390, 232])],
    )])

    question = result["questions"][0]
    assert question["question_visuals"] == []
    assert all(choice["visuals"] == [] for choice in question["choices"])
    assert question["needs_review"] is True
    assert result["unassigned_visuals"][0]["id"] == "ambiguous"
    assert result["unassigned_visuals"][0]["needs_review"] is True