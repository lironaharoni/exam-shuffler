import base64
import binascii
import copy
import random
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AnswerSourceMode = Literal["none", "same_position", "manual"]
AnswerKeyMode = Literal["separate", "appended", "both"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class AnswerSource(InputModel):
    mode: AnswerSourceMode = "manual"
    position: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def validate_position(self):
        if (self.mode == "same_position") != (self.position is not None):
            raise ValueError("position is required only for same_position answer source")
        return self


class VisualInput(InputModel):
    data_url: str | None = Field(default=None, max_length=20_000_000)

    @field_validator("data_url")
    @classmethod
    def validate_image_data_url(cls, value):
        if value is None:
            return value
        match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})", value)
        if not match:
            raise ValueError("visual data must be a base64 PNG or JPEG data URL")
        try:
            image = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("visual data is not valid base64") from error
        if match.group(1) == "png" and not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("visual data does not contain a PNG image")
        if match.group(1) == "jpeg" and not image.startswith(b"\xff\xd8\xff"):
            raise ValueError("visual data does not contain a JPEG image")
        return value


class ReviewedChoice(InputModel):
    review_id: str = Field(alias="reviewId", min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=80)
    text: str = ""
    visuals: list[VisualInput] = Field(default_factory=list, max_length=100)


class ReviewedQuestion(InputModel):
    review_id: str = Field(alias="reviewId", min_length=1, max_length=200)
    number: int = Field(gt=0)
    text: str
    page_number: int | None = Field(default=None, gt=0)
    question_visuals: list[VisualInput] = Field(default_factory=list, max_length=100)
    choices: list[ReviewedChoice] = Field(default_factory=list, max_length=30)
    correct_choice_id: str | None = Field(default=None, max_length=200)
    included: bool = True


class PreambleLine(InputModel):
    text: str = Field(max_length=2_000)
    type: Literal["header", "metadata", "instructions"]


class ReviewedPreamble(InputModel):
    enabled: bool = True
    lines: list[PreambleLine] = Field(default_factory=list, max_length=200)


class ReviewedExam(InputModel):
    questions: list[ReviewedQuestion] = Field(max_length=500)
    answer_source: AnswerSource = Field(default_factory=AnswerSource)
    preamble: ReviewedPreamble = Field(default_factory=ReviewedPreamble)


class GenerationSettings(InputModel):
    number_of_versions: int = Field(ge=1, le=10)
    shuffle_questions: bool = True
    shuffle_choices: bool = True
    answer_key_mode: AnswerKeyMode = "separate"


class ReviewedGenerationRequest(InputModel):
    reviewed_exam: ReviewedExam
    settings: GenerationSettings


@dataclass
class GeneratedVersion:
    questions: list[ReviewedQuestion]
    answer_positions: list[int | None]
    preamble_lines: list[PreambleLine]


def apply_answer_source(analysis, mode, position=None):
    if mode not in {"none", "same_position", "manual"}:
        raise ValueError("unsupported answer source")
    if mode != "same_position" and position is not None:
        raise ValueError("position is supported only for same_position answer source")
    if position is not None and not 1 <= position <= 10:
        raise ValueError("same_position answer source requires a position from 1 to 10")

    for question in analysis["questions"]:
        question["answer_source_attention"] = None
        if mode == "none":
            question["correct_answer_label"] = None
        elif mode == "same_position" and position is not None:
            choices = question.get("choices", [])
            if position <= len(choices):
                question["correct_answer_label"] = choices[position - 1]["label"]
            else:
                question["correct_answer_label"] = None
                question["answer_source_attention"] = (
                    f"לא נמצאה תשובה במיקום {position}; אפשר לבחור תשובה ידנית."
                )

    analysis["answer_source"] = {"mode": mode, "position": position}
    return analysis


def build_generation_questions(reviewed_exam):
    included = [question for question in reviewed_exam.questions if question.included]
    if not included:
        raise ValueError("יש לכלול לפחות שאלה אחת.")

    question_ids = [question.review_id for question in included]
    if len(set(question_ids)) != len(question_ids):
        raise ValueError("question identities must be unique")

    generation_questions = []
    for question in included:
        if not question.text.strip():
            raise ValueError(f"שאלה {question.number}: יש למלא את נוסח השאלה.")
        if len(question.choices) < 2:
            raise ValueError(f"שאלה {question.number}: נדרשות לפחות שתי תשובות.")
        labels = [choice.label for choice in question.choices]
        if len(set(labels)) != len(labels):
            raise ValueError(f"שאלה {question.number}: תוויות התשובות חייבות להיות ייחודיות.")
        choice_ids = [choice.review_id for choice in question.choices]
        if len(set(choice_ids)) != len(choice_ids):
            raise ValueError(f"שאלה {question.number}: זהויות התשובות חייבות להיות ייחודיות.")
        if question.correct_choice_id is not None and question.correct_choice_id not in choice_ids:
            raise ValueError(f"שאלה {question.number}: התשובה הנכונה אינה קיימת.")
        if any(not choice.text.strip() and not choice.visuals for choice in question.choices):
            raise ValueError(f"שאלה {question.number}: לכל תשובה נדרש טקסט או תוכן חזותי.")
        if any(visual.data_url is None for visual in question.question_visuals):
            raise ValueError(f"שאלה {question.number}: לא ניתן להפיק תמונת שאלה שזוהתה.")
        if any(
            visual.data_url is None
            for choice in question.choices
            for visual in choice.visuals
        ):
            raise ValueError(f"שאלה {question.number}: לא ניתן להפיק תמונת תשובה שזוהתה.")
        generation_questions.append(question.model_copy(deep=True, update={"included": True}))

    return generation_questions


def generate_reviewed_versions(reviewed_exam, settings, rng=None):
    original_questions = build_generation_questions(reviewed_exam)
    preamble_lines = (
        copy.deepcopy(reviewed_exam.preamble.lines)
        if reviewed_exam.preamble.enabled
        else []
    )
    randomizer = rng or random.Random()
    versions = []

    for _ in range(settings.number_of_versions):
        questions = copy.deepcopy(original_questions)
        if settings.shuffle_choices:
            for question in questions:
                randomizer.shuffle(question.choices)
        if settings.shuffle_questions:
            randomizer.shuffle(questions)

        answer_positions = []
        for question in questions:
            if question.correct_choice_id is None:
                answer_positions.append(None)
                continue
            position = next(
                index
                for index, choice in enumerate(question.choices, start=1)
                if choice.review_id == question.correct_choice_id
            )
            answer_positions.append(position)

        versions.append(GeneratedVersion(
            questions,
            answer_positions,
            copy.deepcopy(preamble_lines),
        ))

    return versions
