export const DEFAULT_GENERATION_SETTINGS = Object.freeze({
  number_of_versions: "1",
  multiple_versions: false,
  include_exam_details: false,
  include_instructions: false,
  shuffle_questions: false,
  shuffle_choices: true,
  answer_key_mode: "separate",
});

export function getPreservablePreambleItems(ignoredContent = []) {
  return ignoredContent.filter(
    (item) => ["header", "metadata", "instructions"].includes(item.type),
  );
}

export function getQuestionIssues(question) {
  const issues = [];
  if (!question.text.trim()) issues.push("יש למלא את נוסח השאלה.");
  if (question.choices.length < 2) issues.push("יש להוסיף לפחות שתי תשובות.");
  const labels = question.choices.map((choice) => String(choice.label));
  if (new Set(labels).size !== labels.length) {
    issues.push("תוויות התשובות חייבות להיות ייחודיות.");
  }
  if (question.choices.some((choice) => !choice.text.trim() && !choice.visuals?.length)) {
    issues.push("לכל תשובה חייב להיות תוכן או תמונה.");
  }
  return issues;
}

export function getIncludedQuestions(reviewExam) {
  return reviewExam?.questions.filter((question) => question.included) || [];
}

export function getCommonAnswerPositions(reviewExam) {
  const validIncluded = getIncludedQuestions(reviewExam).filter(
    (question) => getQuestionIssues(question).length === 0,
  );
  if (!validIncluded.length) return [];
  const minimumChoiceCount = Math.min(
    ...validIncluded.map((question) => question.choices.length),
  );
  return Array.from({ length: minimumChoiceCount }, (_, index) => index + 1);
}

export function applySharedAnswerPosition(reviewExam, position) {
  const numericPosition = Number(position);
  return {
    ...reviewExam,
    answer_source: { mode: "same_position", position: numericPosition },
    questions: reviewExam.questions.map((question) => {
      const choice = question.choices[numericPosition - 1];
      return {
        ...question,
        correct_choice_id: choice?.reviewId || null,
        correct_answer_label: choice?.label ?? null,
        answer_source_attention: null,
      };
    }),
  };
}

export function clearSharedAnswerPosition(reviewExam) {
  return {
    ...reviewExam,
    answer_source: { mode: "same_position", position: null },
    questions: reviewExam.questions.map((question) => ({
      ...question,
      correct_choice_id: null,
      correct_answer_label: null,
    })),
  };
}

export function getQuickShuffleEligibility(analysis, reviewExam) {
  if (!analysis || !reviewExam) {
    return { eligible: false, reason: "יש לנתח את המבחן תחילה." };
  }
  if (analysis.analysis_status !== "ready" || analysis.safe_to_generate !== true) {
    return {
      eligible: false,
      reason: "הניתוח דורש בדיקה לפני יצירת המבחן. יש לעבור לבדיקה ועריכה.",
    };
  }

  const included = getIncludedQuestions(reviewExam);
  if (!included.length || included.some((question) => getQuestionIssues(question).length > 0)) {
    return {
      eligible: false,
      reason: "לא נמצאו שאלות תקינות שניתן לכלול בערבול מהיר.",
    };
  }

  return { eligible: true, reason: "" };
}

export function buildReviewedGenerationExam(reviewExam, contentSettings = null) {
  const preambleLines = reviewExam.preamble.lines.filter((line) => {
    if (!contentSettings) return reviewExam.preamble.enabled;
    if (line.type === "instructions") return contentSettings.include_instructions;
    return contentSettings.include_exam_details;
  });
  return {
    answer_source: reviewExam.answer_source,
    preamble: {
      enabled: preambleLines.length > 0,
      lines: preambleLines.map(({ text, type }) => ({ text, type })),
    },
    questions: reviewExam.questions
      .filter((question) => question.included)
      .map((question) => ({
        reviewId: question.reviewId,
        number: question.number,
        text: question.text,
        page_number: question.page_number,
        question_visuals: question.question_visuals,
        correct_choice_id: question.correct_choice_id,
        included: true,
        choices: question.choices.map((choice) => ({
          reviewId: choice.reviewId,
          label: choice.label,
          text: choice.text,
          visuals: choice.visuals,
        })),
      })),
  };
}
