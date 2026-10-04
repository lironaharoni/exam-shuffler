import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_GENERATION_SETTINGS,
  applySharedAnswerPosition,
  buildReviewedGenerationExam,
  clearSharedAnswerPosition,
  getCommonAnswerPositions,
  getPreservablePreambleItems,
  getQuickShuffleEligibility,
} from "../src/examLogic.js";

function choice(id) {
  return { reviewId: id, label: id, text: id, visuals: [] };
}

function question(id, choiceCount, included = true) {
  return {
    reviewId: id,
    text: `question ${id}`,
    included,
    choices: Array.from({ length: choiceCount }, (_, index) => choice(`${id}-${index + 1}`)),
  };
}

function exam(questions, answerSource = { mode: "none", position: null }) {
  return { questions, answer_source: answerSource };
}

test("one version is the default", () => {
  assert.equal(DEFAULT_GENERATION_SETTINGS.number_of_versions, "1");
  assert.equal(DEFAULT_GENERATION_SETTINGS.multiple_versions, false);
  assert.equal(DEFAULT_GENERATION_SETTINGS.include_exam_details, false);
  assert.equal(DEFAULT_GENERATION_SETTINGS.include_instructions, false);
  assert.equal(DEFAULT_GENERATION_SETTINGS.shuffle_questions, false);
  assert.equal(DEFAULT_GENERATION_SETTINGS.shuffle_choices, true);
});

test("shared answer positions use the minimum included valid choice count", () => {
  const reviewed = exam([
    question("q1", 4),
    question("q2", 5),
    question("q3", 4),
  ]);

  assert.deepEqual(getCommonAnswerPositions(reviewed), [1, 2, 3, 4]);
});

test("shared answer range updates when included questions change", () => {
  const reviewed = exam([
    question("q1", 4),
    question("q2", 2, false),
  ]);
  assert.deepEqual(getCommonAnswerPositions(reviewed), [1, 2, 3, 4]);

  reviewed.questions[1].included = true;
  assert.deepEqual(getCommonAnswerPositions(reviewed), [1, 2]);
});

test("an invalid shared position can be cleared without inventing answers", () => {
  const selected = applySharedAnswerPosition(
    exam([question("q1", 4), question("q2", 4)]),
    4,
  );
  assert.equal(selected.questions[0].correct_choice_id, "q1-4");

  const cleared = clearSharedAnswerPosition(selected);
  assert.equal(cleared.answer_source.position, null);
  assert.ok(cleared.questions.every((item) => item.correct_choice_id === null));
});

test("quick shuffle requires a ready and safe analysis", () => {
  const reviewed = exam([question("q1", 4)]);
  assert.equal(getQuickShuffleEligibility({
    analysis_status: "needs_review",
    safe_to_generate: false,
  }, reviewed).eligible, false);
  assert.equal(getQuickShuffleEligibility({
    analysis_status: "ready",
    safe_to_generate: true,
  }, reviewed).eligible, true);
});

test("missing correct answers do not block quick shuffle", () => {
  const reviewed = exam([question("q1", 4)], { mode: "manual", position: null });
  assert.equal(reviewed.questions[0].correct_choice_id, undefined);
  assert.equal(getQuickShuffleEligibility({
    analysis_status: "ready",
    safe_to_generate: true,
  }, reviewed).eligible, true);
});

test("quick shuffle reaches settings before a shared position is selected", () => {
  const unresolved = exam(
    [question("q1", 4), question("q2", 4)],
    { mode: "same_position", position: null },
  );
  const analysis = { analysis_status: "ready", safe_to_generate: true };
  assert.equal(getQuickShuffleEligibility(analysis, unresolved).eligible, true);

  const selected = applySharedAnswerPosition(unresolved, 3);
  assert.equal(getQuickShuffleEligibility(analysis, selected).eligible, true);
});

test("generation content settings independently select reviewed details and instructions", () => {
  const reviewed = {
    ...exam([question("q1", 4)]),
    preamble: {
      enabled: true,
      lines: [
        { reviewId: "p1", type: "header", text: "University" },
        { reviewId: "p2", type: "metadata", text: "Course" },
        { reviewId: "p3", type: "instructions", text: "Choose one" },
      ],
    },
  };

  const questionsOnly = buildReviewedGenerationExam(reviewed, {
    include_exam_details: false,
    include_instructions: false,
  });
  assert.equal(questionsOnly.preamble.enabled, false);
  assert.deepEqual(questionsOnly.preamble.lines, []);

  const detailsOnly = buildReviewedGenerationExam(reviewed, {
    include_exam_details: true,
    include_instructions: false,
  });
  assert.deepEqual(detailsOnly.preamble.lines.map((line) => line.text), [
    "University",
    "Course",
  ]);

  const instructionsOnly = buildReviewedGenerationExam(reviewed, {
    include_exam_details: false,
    include_instructions: true,
  });
  assert.deepEqual(instructionsOnly.preamble.lines.map((line) => line.text), [
    "Choose one",
  ]);
});

test("reviewed preamble survives generation adaptation and can be disabled", () => {
  const reviewed = {
    ...exam([question("q1", 4)]),
    preamble: {
      enabled: true,
      lines: [
        { reviewId: "p1", type: "header", text: "University" },
        { reviewId: "p2", type: "instructions", text: "Choose one" },
      ],
    },
  };
  const payload = buildReviewedGenerationExam(reviewed);
  assert.deepEqual(payload.preamble.lines, [
    { type: "header", text: "University" },
    { type: "instructions", text: "Choose one" },
  ]);

  reviewed.preamble.enabled = false;
  assert.equal(buildReviewedGenerationExam(reviewed).preamble.enabled, false);
});

test("only classified header, metadata, and instruction lines enter the preamble", () => {
  assert.deepEqual(getPreservablePreambleItems([
    { type: "header", text: "University" },
    { type: "metadata", text: "Course" },
    { type: "instructions", text: "Choose one" },
    { type: "ambiguous_numbered_content", text: "1. unclear" },
  ]).map((item) => item.text), ["University", "Course", "Choose one"]);
});
