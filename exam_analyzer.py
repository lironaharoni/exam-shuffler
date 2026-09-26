"""Lightweight deterministic structuring for document_reader page records."""

from collections.abc import Mapping, Sequence
import re

import pymupdf


_NUMBERED_LINE = re.compile(r"^\s*(\d+|[A-Za-z]|[א-ת])[.)][ \t]*(.*)$")
_QUESTION_CUES = (
    "מהו", "מהי", "מהם", "מהן", "מה ", "מי ", "לאיזה", "איזה",
    "אילו", "באיזה", "היכן", "איפה", "כיצד", "איך", "מתי", "למה",
    "what ", "which ", "who ", "where ", "when ", "why ", "how ",
    "select ", "identify ", "choose ",
)
_MAX_PLAUSIBLE_CHOICES = 12


def _as_page_record(page):
    if hasattr(page, "to_dict"):
        page = page.to_dict()
    if not isinstance(page, Mapping):
        raise TypeError("each page must be a document_reader page record")

    page_number = page.get("page_number")
    text = page.get("extracted_text")
    if (
        not isinstance(page_number, int)
        or isinstance(page_number, bool)
        or page_number < 1
    ):
        raise ValueError("each page requires a positive page_number")
    if not isinstance(text, str):
        raise ValueError("each page requires extracted_text")
    regions = page.get("visual_regions", [])
    if not isinstance(regions, list):
        raise ValueError("visual_regions must be a list")
    text_lines = page.get("text_lines", [])
    if not isinstance(text_lines, list):
        raise ValueError("text_lines must be a list")
    page_bounds = page.get("page_bounds")
    if page_bounds is not None and (
        not isinstance(page_bounds, list) or len(page_bounds) != 4
    ):
        raise ValueError("page_bounds must contain four coordinates")
    visual_detected = page.get("visual_content_detected", bool(regions))
    if not isinstance(visual_detected, bool):
        raise ValueError("visual_content_detected must be a boolean")
    source_type = page.get("source_type", "native_text")
    page_image_reference = page.get("page_image_reference")
    if page_image_reference is not None and not isinstance(page_image_reference, Mapping):
        raise ValueError("page_image_reference must be an object")
    return (
        page_number, text, visual_detected, regions, text_lines, page_bounds,
        source_type, page_image_reference,
    )


def _looks_like_question(text):
    normalized = text.casefold()
    return (
        normalized.rstrip().endswith(("?", "؟"))
        or any(cue in normalized for cue in _QUESTION_CUES)
    )


def _preamble_type(text):
    normalized = text.casefold()
    if "אוניברסיטת" in normalized or "בית הספר" in normalized:
        return "header"
    if any(cue in normalized for cue in (
        "עליכם", "בהצלחה", "בחרו", "ענו", "שאלות רב ברירה",
        "תשובה אחת נכונה", "משקל כל השאלות",
    )):
        return "instructions"
    return "metadata"


def _new_question(number, text, page_number):
    return {
        "number": number,
        "text_parts": [text],
        "choices": [],
        "page_number": page_number,
        "source_pages": {page_number},
        "stem_positions": [],
        "needs_review": not bool(text.strip()),
        "question_visuals": [],
    }


def _line_bounds_by_index(text_lines):
    result = {}
    for line in text_lines:
        if not isinstance(line, Mapping):
            continue
        line_index = line.get("line_index")
        bounds = line.get("text_bounds", line.get("bounds"))
        if (
            isinstance(line_index, int)
            and not isinstance(line_index, bool)
            and isinstance(bounds, list)
            and len(bounds) == 4
        ):
            result[line_index] = bounds
    return result


def _expected_choice_label(position, first_label):
    if first_label.isdigit():
        return str(int(first_label) + position - 1)
    if len(first_label) == 1 and first_label.isalpha():
        base = ord(first_label.lower())
        return chr(base + position - 1)
    hebrew_alphabet = "אבגדהוזחטיכלמנסעפצקרשת"
    if first_label in hebrew_alphabet:
        index = hebrew_alphabet.index(first_label) + position - 1
        return hebrew_alphabet[index] if index < len(hebrew_alphabet) else None
    return None


def _combined_bounds(bounds):
    return [
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    ]


def _rect_overlap_area(first, second):
    width = max(0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0, min(first[3], second[3]) - max(first[1], second[1]))
    return width * height


def _scan_ink_bounds(pixmap, page, zone):
    scale_x = pixmap.width / page.rect.width
    scale_y = pixmap.height / page.rect.height
    x0 = max(0, min(pixmap.width, int(zone[0] * scale_x)))
    y0 = max(0, min(pixmap.height, int(zone[1] * scale_y)))
    x1 = max(x0, min(pixmap.width, int(zone[2] * scale_x)))
    y1 = max(y0, min(pixmap.height, int(zone[3] * scale_y)))
    if x1 <= x0 or y1 <= y0:
        return None

    samples = pixmap.samples
    ink_count = 0
    bounds = [x1, y1, x0, y0]
    threshold = 215
    for pixel_y in range(y0, y1):
        row_start = pixel_y * pixmap.width + x0
        row = samples[row_start:row_start + (x1 - x0)]
        for offset, value in enumerate(row):
            if value < threshold:
                pixel_x = x0 + offset
                ink_count += 1
                bounds[0] = min(bounds[0], pixel_x)
                bounds[1] = min(bounds[1], pixel_y)
                bounds[2] = max(bounds[2], pixel_x + 1)
                bounds[3] = max(bounds[3], pixel_y + 1)

    zone_area = (x1 - x0) * (y1 - y0)
    if ink_count < max(28, int(zone_area * 0.0015)):
        return None

    detected = [
        bounds[0] / scale_x,
        bounds[1] / scale_y,
        bounds[2] / scale_x,
        bounds[3] / scale_y,
    ]
    if detected[2] - detected[0] < 8 or detected[3] - detected[1] < 8:
        return None

    clipped = (
        bounds[0] <= x0 + 2
        or bounds[1] <= y0 + 2
        or bounds[2] >= x1 - 2
        or bounds[3] >= y1 - 2
    )
    margin = 2.0
    detected = [
        max(page.rect.x0, detected[0] - margin),
        max(page.rect.y0, detected[1] - margin),
        min(page.rect.x1, detected[2] + margin),
        min(page.rect.y1, detected[3] + margin),
    ]
    return detected, clipped


def _merge_scan_candidates(candidates):
    merged = []
    for candidate in candidates:
        bounds = candidate["bounds"]
        match = None
        for existing in merged:
            other = existing["bounds"]
            overlap = _rect_overlap_area(bounds, other)
            smaller_area = min(
                max(1, (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])),
                max(1, (other[2] - other[0]) * (other[3] - other[1])),
            )
            if overlap / smaller_area >= 0.65:
                match = existing
                break
        if match is None:
            merged.append(candidate)
            continue
        existing_bounds = match["bounds"]
        existing_contains = all(
            existing_bounds[index] <= bounds[index]
            for index in (0, 1)
        ) and all(
            existing_bounds[index] >= bounds[index]
            for index in (2, 3)
        )
        candidate_contains = all(
            bounds[index] <= existing_bounds[index]
            for index in (0, 1)
        ) and all(
            bounds[index] >= existing_bounds[index]
            for index in (2, 3)
        )
        match["bounds"] = _combined_bounds([match["bounds"], bounds])
        match["_targets"].extend(candidate["_targets"])
        if candidate_contains and not candidate["_clipped"]:
            match["_clipped"] = False
        elif not (existing_contains and not match["_clipped"]):
            match["_clipped"] = match["_clipped"] or candidate["_clipped"]

    for candidate in merged:
        unique_targets = {}
        for question, choice in candidate["_targets"]:
            unique_targets[(id(question), id(choice) if choice is not None else None)] = (
                question, choice
            )
        candidate["_targets"] = list(unique_targets.values())
    return merged


def _infer_scanned_visuals(questions, page_data):
    candidates = []
    open_documents = {}
    try:
        for page_number, page_data_item in page_data.items():
            reference = page_data_item["page_image_reference"]
            if page_data_item["source_type"] != "ocr" or not reference:
                continue
            path = reference.get("pdf_path")
            if not path:
                continue
            document = open_documents.setdefault(path, pymupdf.open(path))
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(
                dpi=120, colorspace=pymupdf.csGRAY, alpha=False
            )
            page_width = page.rect.width
            page_height = page.rect.height
            page_lines = _line_bounds_by_index(page_data_item["text_lines"])

            def add_zone(zone, question, choice=None):
                found = _scan_ink_bounds(pixmap, page, zone)
                if found is None:
                    return
                bounds, clipped = found
                candidates.append({
                    "page_number": page_number,
                    "type": "ocr_gap_crop",
                    "bounds": bounds,
                    "source_reference": {
                        "pdf_path": path,
                        "page_number": page_number,
                        "bounds": bounds,
                        "source": "rendered_scanned_page",
                        "dpi": reference.get("dpi", 200),
                    },
                    "_targets": [(question, choice)],
                    "_clipped": clipped,
                })

            for question in questions:
                stem_rows = [
                    bounds for row_page, bounds in question["stem_positions"]
                    if row_page == page_number
                ]
                choices_on_page = []
                for choice in question["choices"]:
                    choice_rows = [
                        bounds for row_page, bounds in choice["positions"]
                        if row_page == page_number
                    ]
                    if choice_rows:
                        choices_on_page.append((choice, _combined_bounds(choice_rows)))
                choices_on_page.sort(key=lambda item: item[1][1])

                if stem_rows and choices_on_page:
                    last_stem = max(stem_rows, key=lambda bounds: bounds[3])
                    first_choice = choices_on_page[0][1]
                    first_choice_margin = max(
                        8, (first_choice[3] - first_choice[1]) * 0.8
                    )
                    zone = [
                        3,
                        last_stem[3] + 3,
                        page_width - 3,
                        first_choice[1] - first_choice_margin,
                    ]
                    if zone[3] - zone[1] >= 12:
                        add_zone(zone, question)

                for choice_index, (choice, row) in enumerate(choices_on_page):
                    previous_bottom = max(
                        (bounds[3] for bounds in stem_rows if bounds[3] <= row[1]),
                        default=0,
                    )
                    if choice_index:
                        previous_bottom = choices_on_page[choice_index - 1][1][3]
                    next_top = min(
                        (bounds[1] for bounds in stem_rows if bounds[1] >= row[3]),
                        default=page_height,
                    )
                    if choice_index + 1 < len(choices_on_page):
                        next_top = choices_on_page[choice_index + 1][1][1]
                    if next_top < row[3]:
                        next_top = page_height

                    zone_top = max(0, (previous_bottom + row[1]) / 2)
                    zone_bottom = min(page_height, (row[3] + next_top) / 2)
                    line_bounds = [
                        bounds for row_page, bounds in choice["positions"]
                        if row_page == page_number
                    ]
                    if not line_bounds:
                        continue
                    text_bounds = _combined_bounds(line_bounds)
                    if zone_bottom - zone_top >= 12:
                        gap = 2
                        add_zone(
                            [3, zone_top, max(3, text_bounds[0] - gap), zone_bottom],
                            question,
                            choice,
                        )
                        add_zone(
                            [min(page_width - 3, text_bounds[2] + gap), zone_top,
                             page_width - 3, zone_bottom],
                            question,
                            choice,
                        )

                    if next_top - row[3] >= 12:
                        add_zone(
                            [3, row[3] + 3, page_width - 3, next_top - 3],
                            question,
                            choice,
                        )
        merged = _merge_scan_candidates(candidates)
    finally:
        for document in open_documents.values():
            document.close()

    for index, candidate in enumerate(merged, start=1):
        candidate["id"] = (
            f"page-{candidate['page_number']}-ocr-candidate-{index}"
        )
    return merged


def _associate_visuals(questions, pages, warnings):
    page_data = {
        page_number: {
            "regions": regions,
            "text_lines": text_lines,
            "page_bounds": page_bounds,
            "visual_detected": visual_detected,
            "source_type": source_type,
            "page_image_reference": page_image_reference,
        }
        for (
            page_number, _, visual_detected, regions, text_lines, page_bounds,
            source_type, page_image_reference,
        ) in pages
    }
    unassigned = []
    question_starts = {}
    for question in questions:
        for page_number, bounds in question["stem_positions"]:
            question_starts.setdefault(page_number, []).append(
                (bounds[1], question)
            )

    visual_records = []
    for candidate in _infer_scanned_visuals(questions, page_data):
        targets = candidate.pop("_targets")
        clipped = candidate.pop("_clipped")
        unique_targets = {
            (id(question), id(choice) if choice is not None else None): (question, choice)
            for question, choice in targets
        }
        implicated_questions = {
            id(question): question
            for question, _ in unique_targets.values()
        }
        if len(unique_targets) == 1 and not clipped:
            question, choice = next(iter(unique_targets.values()))
            if choice is None:
                question["question_visuals"].append(candidate)
            else:
                choice["visuals"].append(candidate)
            continue

        reason = (
            "The OCR visual candidate crosses a layout boundary."
            if clipped
            else "The OCR visual candidate fits more than one semantic region."
        )
        for question in implicated_questions.values():
            question["needs_review"] = True
        unassigned.append({
            **candidate,
            "reason": reason,
            "needs_review": True,
        })

    for page_number, page in page_data.items():
        if page["source_type"] != "ocr" or page["text_lines"]:
            continue
        affected = [
            question for question in questions
            if page_number in question["source_pages"]
        ]
        for question in affected:
            question["needs_review"] = True
        if affected:
            warnings.append(
                f"OCR positional geometry is unavailable on page {page_number}; "
                "visual association requires manual review."
            )
            unassigned.append({
                "id": f"page-{page_number}-unlocalized-scan",
                "page_number": page_number,
                "type": "unlocalized_scanned_page",
                "bounds": None,
                "source_reference": page["page_image_reference"],
                "reason": "OCR line geometry is unavailable; no visual crop was inferred.",
                "needs_review": True,
            })

    for page_number, page in page_data.items():
        for region in page["regions"]:
            if not isinstance(region, Mapping):
                continue
            record = dict(region)
            record.setdefault("page_number", page_number)
            visual_records.append(record)

        if (
            page["visual_detected"]
            and not page["regions"]
            and page["source_type"] != "ocr"
        ):
            unassigned.append({
                "page_number": page_number,
                "type": "unreferenced_visual_content",
                "bounds": None,
                "source_reference": {"page_number": page_number},
                "reason": "The reader detected visual content without a crop reference.",
                "needs_review": True,
            })

    for visual in visual_records:
        page_number = visual.get("page_number")
        bounds = visual.get("bounds")
        page = page_data.get(page_number)
        if (
            not isinstance(bounds, (list, tuple))
            or len(bounds) != 4
            or page is None
            or visual.get("type") == "scanned_page"
        ):
            reason = "Visual geometry is not specific enough for question association."
            unassigned.append({**visual, "reason": reason, "needs_review": True})
            continue

        bounds = [float(value) for value in bounds]
        choice_candidates = []
        for question in questions:
            for choice in question["choices"]:
                positions = [
                    item_bounds
                    for item_page, item_bounds in choice["positions"]
                    if item_page == page_number
                ]
                if not positions:
                    continue
                best_score = 0
                for row in positions:
                    row_height = max(1, row[3] - row[1])
                    overlap_y = max(0, min(bounds[3], row[3]) - max(bounds[1], row[1]))
                    horizontal_gap = max(bounds[0] - row[2], row[0] - bounds[2], 0)
                    if overlap_y / row_height >= 0.45 and horizontal_gap <= max(28, row_height * 2):
                        score = (overlap_y / row_height) / (1 + horizontal_gap / max(1, row_height))
                        best_score = max(best_score, score)
                if best_score:
                    choice_candidates.append((best_score, question, choice))

        if choice_candidates:
            choice_candidates.sort(key=lambda item: item[0], reverse=True)
            if (
                len(choice_candidates) == 1
                or choice_candidates[0][0] - choice_candidates[1][0] >= 0.2
            ):
                choice_candidates[0][2]["visuals"].append(visual)
                continue

            implicated = {id(candidate[1]): candidate[1] for candidate in choice_candidates}
            for question in implicated.values():
                question["needs_review"] = True
            unassigned.append({
                **visual,
                "reason": "The visual overlaps multiple answer-choice regions.",
                "needs_review": True,
            })
            continue

        center_y = (bounds[1] + bounds[3]) / 2
        stem_candidates = []
        page_bottom = (
            page["page_bounds"][3]
            if page["page_bounds"] is not None
            else float("inf")
        )
        starts = sorted(question_starts.get(page_number, []), key=lambda item: item[0])
        for question in questions:
            stem_rows = [
                row_bounds
                for row_page, row_bounds in question["stem_positions"]
                if row_page == page_number
            ]
            if not stem_rows:
                continue
            first_choice = [
                choice_bounds
                for choice in question["choices"]
                for choice_page, choice_bounds in choice["positions"]
                if choice_page == page_number
            ]
            top = min(row[1] for row in stem_rows)
            if first_choice:
                bottom = min(row[1] for row in first_choice)
            else:
                later_starts = [
                    start_y for start_y, other in starts
                    if start_y > top and other is not question
                ]
                bottom = min(later_starts, default=page_bottom)
            if top <= center_y <= bottom:
                stem_candidates.append(question)

        if len(stem_candidates) == 1:
            stem_candidates[0]["question_visuals"].append(visual)
            continue
        if len(stem_candidates) > 1:
            for question in stem_candidates:
                question["needs_review"] = True
            unassigned.append({
                **visual,
                "reason": "The visual falls within multiple question-stem regions.",
                "needs_review": True,
            })
            continue

        proximity_candidates = []
        visual_height = max(0, bounds[3] - bounds[1])
        max_distance = max(18, min(visual_height * 0.55, 72))
        for question in questions:
            for choice in question["choices"]:
                positions = [
                    item_bounds
                    for item_page, item_bounds in choice["positions"]
                    if item_page == page_number
                ]
                if not positions:
                    continue
                distance = _rect_distance(bounds, _combined_bounds(positions))
                if distance <= max_distance:
                    proximity_candidates.append((distance, question, choice))

        proximity_candidates.sort(key=lambda item: item[0])
        if proximity_candidates and (
            len(proximity_candidates) == 1
            or proximity_candidates[1][0] - proximity_candidates[0][0] >= 6
        ):
            proximity_candidates[0][2]["visuals"].append(visual)
            continue

        implicated = {
            id(candidate[1]): candidate[1]
            for candidate in proximity_candidates
        }
        for question in implicated.values():
            question["needs_review"] = True
        unassigned.append({
            **visual,
            "reason": "No unique nearby question stem or answer choice was found.",
            "needs_review": True,
        })

    for question in questions:
        for choice in question["choices"]:
            if not choice["text"].strip() and not choice["visuals"]:
                question["needs_review"] = True
                warnings.append(
                    f"Choice {choice['label']} for question {question['number']} "
                    "has neither extractable text nor an associated visual."
                )
            del choice["positions"]
        question["has_visual_content"] = bool(
            question["question_visuals"]
            or any(choice["visuals"] for choice in question["choices"])
        )
        del question["source_pages"]
        del question["stem_positions"]
        question["text"] = "\n".join(question.pop("text_parts"))
        question["correct_answer_label"] = None

    for visual in unassigned:
        warnings.append(
            f"Unassigned visual on page {visual['page_number']}: {visual['reason']}"
        )
    return unassigned


def _quality_status(questions, unassigned_visuals, warnings):
    analysis_warnings = []
    if not questions:
        analysis_warnings.append("No questions were detected.")

    previous_number = None
    for question in questions:
        number = question["number"]
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or number <= 0
        ):
            analysis_warnings.append(
                f"Question number {number!r} is missing or invalid."
            )
        elif previous_number is not None and number <= previous_number:
            analysis_warnings.append(
                "Detected question numbers are duplicated or not increasing."
            )
        if isinstance(number, int) and not isinstance(number, bool):
            previous_number = number

        choice_count = len(question["choices"])
        if choice_count == 0:
            analysis_warnings.append(
                f"Question {number!r} has no detected choices."
            )
        elif choice_count > _MAX_PLAUSIBLE_CHOICES:
            analysis_warnings.append(
                f"Question {number!r} has {choice_count} choices, exceeding the "
                f"plausible limit of {_MAX_PLAUSIBLE_CHOICES}."
            )

    review_count = sum(bool(question["needs_review"]) for question in questions)
    if review_count:
        analysis_warnings.append(
            f"{review_count} of {len(questions)} detected questions require review."
        )
        if any(
            question["needs_review"] and question["has_visual_content"]
            for question in questions
        ):
            analysis_warnings.append(
                "Visual associations include questions whose text/layout is not reliable."
            )

    if unassigned_visuals:
        analysis_warnings.append(
            f"{len(unassigned_visuals)} visual regions remain unassigned."
        )

    if warnings:
        ambiguous_count = sum(
            "Ambiguous numbered line" in warning
            or "Numbered content" in warning
            for warning in warnings
        )
        ocr_layout_count = sum(
            "OCR line" in warning or "OCR positional geometry" in warning
            for warning in warnings
        )
        if ambiguous_count:
            analysis_warnings.append(
                f"{ambiguous_count} numbered-line ambiguities remain unresolved."
            )
        if ocr_layout_count:
            analysis_warnings.append(
                f"{ocr_layout_count} OCR/layout warnings remain unresolved."
            )
        if not ambiguous_count and not ocr_layout_count:
            analysis_warnings.append(
                f"{len(warnings)} analyzer warnings remain unresolved."
            )

    safe_to_generate = not analysis_warnings
    return (
        "ready" if safe_to_generate else "needs_review",
        safe_to_generate,
        analysis_warnings,
    )


def analyze_exam(readings):
    """Structure extracted text and associate visual crops by page geometry."""
    if isinstance(readings, Mapping) or hasattr(readings, "to_dict"):
        readings = [readings]
    if not isinstance(readings, Sequence) or isinstance(readings, (str, bytes)):
        raise TypeError("readings must be a page record or a sequence of pages")

    pages = [_as_page_record(page) for page in readings]
    pages.sort(key=lambda page: page[0])
    if len({page[0] for page in pages}) != len(pages):
        raise ValueError("page_number values must be unique")

    questions = []
    ignored_content = []
    warnings = []
    current = None

    def start_question(number, text, page_number, bounds):
        nonlocal current
        if current is not None:
            if not current["choices"]:
                current["needs_review"] = True
                warnings.append(
                    f"Question {current['number']} on page "
                    f"{current['page_number']} has no detected choices."
                )
            questions.append(current)
        current = _new_question(number, text, page_number)
        if bounds is not None:
            current["stem_positions"].append((page_number, bounds))

    def flag_low_confidence_ocr(question, line, page_number, line_record):
        if source_type != "ocr" or not line_record:
            return
        words = line_record.get("words", [])
        if any(word.get("confidence", 100) < 70 for word in words):
            question["needs_review"] = True
            warnings.append(
                f"OCR line {line!r} on page {page_number} contains low-confidence "
                "words; the extracted text was preserved for review."
            )

    for page_number, page_text, _, _, text_lines, _, source_type, _ in pages:
        line_bounds = _line_bounds_by_index(text_lines)
        line_records = {
            item["line_index"]: item
            for item in text_lines
            if isinstance(item, Mapping)
            and isinstance(item.get("line_index"), int)
        }
        source_lines = [line for line in page_text.splitlines() if line.strip()]
        for line_index, line in enumerate(source_lines):
            bounds = line_bounds.get(line_index)
            line_record = line_records.get(line_index)
            if not line.strip():
                continue

            match = _NUMBERED_LINE.match(line)
            if current is None and match is None:
                ignored_content.append({
                    "page_number": page_number,
                    "text": line,
                    "type": _preamble_type(line),
                })
                continue

            if match:
                label = match.group(1)
                number = int(label) if label.isdigit() else None
                body = match.group(2)
                if current is None:
                    if number is None:
                        ignored_content.append({
                            "page_number": page_number,
                            "text": line,
                            "type": "ambiguous_numbered_content",
                        })
                        warnings.append(
                            f"Numbered content {line!r} on page {page_number} "
                            "has no preceding question and was left ignored."
                        )
                        continue
                    start_question(number, body, page_number, bounds)
                    flag_low_confidence_ocr(current, line, page_number, line_record)
                    continue

                current["source_pages"].add(page_number)
                expected_choice = len(current["choices"]) + 1
                next_question = (
                    number is not None
                    and current["number"] is not None
                    and number == current["number"] + 1
                )
                question_like = _looks_like_question(body)
                starts_question = next_question and (
                    expected_choice != number or question_like
                )
                if starts_question:
                    start_question(number, body, page_number, bounds)
                    continue

                if label.isdigit():
                    expected_label = _expected_choice_label(
                        expected_choice,
                        current["choices"][0]["label"]
                        if current["choices"] else label,
                    )
                else:
                    expected_label = _expected_choice_label(
                        expected_choice,
                        current["choices"][0]["label"]
                        if current["choices"] else label,
                    )
                if expected_label is not None and label.casefold() != expected_label.casefold():
                    current["needs_review"] = True
                    warnings.append(
                        f"Ambiguous numbered line {line!r} on page {page_number}; "
                        f"kept as a choice for question {current['number']}."
                    )

                current["choices"].append({
                    "label": label,
                    "text": body,
                    "visuals": [],
                    "positions": [(page_number, bounds)] if bounds else [],
                })
                flag_low_confidence_ocr(
                    current, line, page_number, line_record
                )
                continue

            if current is None:
                ignored_content.append({
                    "page_number": page_number,
                    "text": line,
                    "type": _preamble_type(line),
                })
                continue

            if source_type == "ocr" and bounds is None:
                current["needs_review"] = True
                warnings.append(
                    f"OCR line {line!r} on page {page_number} has no reliable "
                    "word bounds; its text was kept but is not used for layout."
                )
            current["source_pages"].add(page_number)
            if current["choices"]:
                current["choices"][-1]["text"] += "\n" + line
                if bounds is not None:
                    current["choices"][-1]["positions"].append((page_number, bounds))
            else:
                current["text_parts"].append(line)
                if bounds is not None:
                    current["stem_positions"].append((page_number, bounds))
            flag_low_confidence_ocr(current, line, page_number, line_record)

    if current is not None:
        if not current["choices"]:
            current["needs_review"] = True
            warnings.append(
                f"Question {current['number']} on page "
                f"{current['page_number']} has no detected choices."
            )
        questions.append(current)

    unassigned_visuals = _associate_visuals(questions, pages, warnings)
    analysis_status, safe_to_generate, analysis_warnings = _quality_status(
        questions, unassigned_visuals, warnings
    )

    return {
        "questions": questions,
        "ignored_content": ignored_content,
        "unassigned_visuals": unassigned_visuals,
        "warnings": warnings,
        "analysis_status": analysis_status,
        "safe_to_generate": safe_to_generate,
        "analysis_warnings": analysis_warnings,
    }