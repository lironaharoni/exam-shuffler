import { useEffect, useRef, useState } from "react";
import {
  DEFAULT_GENERATION_SETTINGS,
  applySharedAnswerPosition,
  buildReviewedGenerationExam,
  clearSharedAnswerPosition,
  getCommonAnswerPositions,
  getIncludedQuestions,
  getPreservablePreambleItems,
  getQuestionIssues,
  getQuickShuffleEligibility,
} from "./examLogic.js";
import {
  createGeneratedPdfDownloads,
  revokeGeneratedPdfUrls,
} from "./generatedFiles.js";

const API_URL = "http://127.0.0.1:8000/analyze-exam";
const GENERATE_URL = "http://127.0.0.1:8000/generate-versions";

function formatError(response, payload) {
  const reason = payload?.detail?.reason;
  if (reason === "scanned_pdf_not_supported") {
    return "נראה שזהו מסמך סרוק או PDF שמורכב מתמונות. יש לבחור PDF עם טקסט שניתן לסמן.";
  }
  if (reason === "invalid_pdf") {
    return "לא ניתן לקרוא את הקובץ כ-PDF תקין. יש לבדוק את הקובץ ולנסות שוב.";
  }
  if (response.status >= 500) {
    return "אירעה שגיאה בשירות הניתוח. כדאי לנסות שוב בעוד רגע.";
  }
  return "לא ניתן לנתח את קובץ ה-PDF. יש לבדוק את הקובץ ולנסות שוב.";
}

function Visuals({ visuals, label }) {
  if (!visuals?.length) return null;

  return (
    <div className="visual-list">
      {visuals.map((visual, index) => (
        visual.data_url ? (
          <img
            className="visual-image"
            key={visual.id || `${label}-${index}`}
            src={visual.data_url}
            alt={`${label}, תמונה ${index + 1}`}
          />
        ) : null
      ))}
    </div>
  );
}

function createReviewExam(payload) {
  const clonedPayload = structuredClone(payload);
  const preambleLines = getPreservablePreambleItems(clonedPayload.ignored_content)
    .map((item) => ({
      reviewId: crypto.randomUUID(),
      type: item.type,
      text: item.text,
    }));
  return {
    ...clonedPayload,
    preamble: {
      enabled: preambleLines.length > 0,
      lines: preambleLines,
    },
    questions: clonedPayload.questions.map((question) => {
      const choices = (question.choices || []).map((choice) => ({
        ...choice,
        reviewId: crypto.randomUUID(),
        visuals: choice.visuals || [],
      }));
      const matchingChoice = choices.find(
        (choice) => choice.label === question.correct_answer_label,
      );
      return {
        ...question,
        reviewId: crypto.randomUUID(),
        included: true,
        userReviewed: false,
        correct_choice_id: matchingChoice?.reviewId || null,
        choices,
        question_visuals: question.question_visuals || [],
      };
    }),
  };
}

function nextChoiceLabel(choices) {
  const used = new Set(choices.map((choice) => String(choice.label)));
  const labels = choices.map((choice) => String(choice.label));
  if (labels.length && labels.every((label) => /^\d+$/.test(label))) {
    for (let index = 1; index <= 99; index += 1) {
      if (!used.has(String(index))) return String(index);
    }
  }
  if (labels.length && labels.every((label) => /^[A-Z]$/.test(label))) {
    for (let code = 65; code <= 90; code += 1) {
      const label = String.fromCharCode(code);
      if (!used.has(label)) return label;
    }
  }
  let suffix = choices.length + 1;
  while (used.has(`תשובה ${suffix}`)) suffix += 1;
  return `תשובה ${suffix}`;
}

function QuestionCard({ question, issues, showValidation, sharedAnswerMode, onChange }) {
  const [editing, setEditing] = useState(false);

  function updateChoice(reviewId, patch) {
    onChange((current) => ({
      ...current,
      choices: current.choices.map((choice) => (
        choice.reviewId === reviewId ? { ...choice, ...patch } : choice
      )),
    }));
  }

  function selectCorrectAnswer(reviewId) {
    const selected = question.choices.find((choice) => choice.reviewId === reviewId);
    onChange((current) => ({
      ...current,
      correct_choice_id: reviewId,
      correct_answer_label: selected?.label ?? null,
      answer_source_attention: null,
    }));
  }

  function addChoice() {
    const label = nextChoiceLabel(question.choices);
    onChange((current) => ({
      ...current,
      choices: [...current.choices, {
        label,
        text: "",
        visuals: [],
        reviewId: crypto.randomUUID(),
      }],
    }));
  }

  function removeChoice(reviewId) {
    onChange((current) => ({
      ...current,
      choices: current.choices.filter((choice) => choice.reviewId !== reviewId),
      ...(current.correct_choice_id === reviewId ? {
        correct_choice_id: null,
        correct_answer_label: null,
      } : {}),
    }));
  }

  return (
    <article className={`question-card${question.included ? "" : " is-excluded"}`}>
      <header className="question-heading">
        <span className="question-number">שאלה {question.number}</span>
        <span className="question-page">עמוד {question.page_number}</span>
        {question.needs_review && <span className="review-flag">נדרשת בדיקה</span>}
        {question.userReviewed && <span className="confirmed-flag">נבדקה ואושרה</span>}
        <div className="question-actions">
          <button className="text-button" type="button" onClick={() => setEditing(!editing)} aria-pressed={editing}>
            {editing ? "סיום עריכה" : "עריכה"}
          </button>
          <button
            className="text-button include-button"
            type="button"
            onClick={() => onChange((current) => ({ ...current, included: !current.included }))}
            aria-pressed={question.included}
          >
            {question.included ? "הוצאה מהמבחן" : "החזרה למבחן"}
          </button>
        </div>
      </header>

      {editing ? (
        <textarea
          className="edit-field question-edit-field"
          value={question.text}
          onChange={(event) => onChange((current) => ({ ...current, text: event.target.value }))}
          aria-label={`עריכת נוסח שאלה ${question.number}`}
          dir="auto"
          rows={2}
        />
      ) : (
        <p className="question-text" dir="auto">{question.text || "לא זוהה נוסח לשאלה"}</p>
      )}
      <Visuals visuals={question.question_visuals} label={`שאלה ${question.number}`} />
      {question.answer_source_attention && (
        <p className="source-review-note" role="status">{question.answer_source_attention}</p>
      )}

      <fieldset className="correct-answer-group">
        <legend>בחירת תשובה נכונה <span>(אפשר להשאיר ללא בחירה)</span></legend>
        <ol className="choice-list">
          {question.choices.map((choice) => (
            <li className="choice-row" key={choice.reviewId}>
              <span className="choice-label">{choice.label}</span>
              <div className="choice-content">
                {editing ? (
                  <textarea
                    className="edit-field choice-edit-field"
                    value={choice.text}
                    onChange={(event) => updateChoice(choice.reviewId, { text: event.target.value })}
                    aria-label={`עריכת תשובה ${choice.label} בשאלה ${question.number}`}
                    dir="auto"
                    rows={1}
                    placeholder="תוכן התשובה"
                  />
                ) : choice.text ? <p dir="auto">{choice.text}</p> : null}
                <Visuals
                  visuals={choice.visuals}
                  label={`שאלה ${question.number}, תשובה ${choice.label}`}
                />
              </div>
              <label className="correct-answer-control">
                <input
                  type="radio"
                  name={`correct-${question.reviewId}`}
                  checked={question.correct_choice_id === choice.reviewId}
                  onChange={() => selectCorrectAnswer(choice.reviewId)}
                  disabled={sharedAnswerMode}
                  aria-label={`סימון תשובה ${choice.label} כנכונה`}
                />
                <span>{sharedAnswerMode ? "לפי המיקום המשותף" : "נכונה"}</span>
              </label>
              {editing && (
                <button
                  className="remove-choice-button"
                  type="button"
                  onClick={() => removeChoice(choice.reviewId)}
                  aria-label={`הסרת תשובה ${choice.label}`}
                  title={`הסרת תשובה ${choice.label}`}
                >×</button>
              )}
            </li>
          ))}
        </ol>
        {editing && <button className="text-button add-choice-button" type="button" onClick={addChoice}>+ הוספת תשובה</button>}
      </fieldset>

      <label className="review-confirm-control">
        <input
          type="checkbox"
          checked={question.userReviewed}
          onChange={(event) => onChange((current) => ({ ...current, userReviewed: event.target.checked }))}
        />
        <span>בדקתי ואישרתי את השאלה</span>
      </label>
      {showValidation && question.included && issues.length > 0 && (
        <ul className="question-validation" aria-label={`בעיות בשאלה ${question.number}`}>
          {issues.map((issue) => <li key={issue}>{issue}</li>)}
        </ul>
      )}
    </article>
  );
}

function SharedAnswerPositionControl({
  positions,
  value,
  notice,
  onChange,
}) {
  return (
    <div className="shared-position-panel">
      <label className="answer-position-control">
        <span>מיקום התשובה הנכונה בכל השאלות</span>
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-label="מיקום התשובה הנכונה בכל שאלה"
        >
          <option value="">בחירת מיקום</option>
          {positions.map((position) => (
            <option value={String(position)} key={position}>תשובה {position}</option>
          ))}
        </select>
      </label>
      <p className="field-hint">
        האפשרויות מבוססות על מספר התשובות המשותף לכל השאלות הכלולות.
      </p>
      {notice && <p className="source-review-note" role="status">{notice}</p>}
    </div>
  );
}

function PreambleEditor({ preamble, onChange }) {
  function updateLine(reviewId, text) {
    onChange({
      ...preamble,
      lines: preamble.lines.map((line) => (
        line.reviewId === reviewId ? { ...line, text } : line
      )),
    });
  }

  function removeLine(reviewId) {
    onChange({
      ...preamble,
      lines: preamble.lines.filter((line) => line.reviewId !== reviewId),
    });
  }

  return (
    <section className="preamble-editor" aria-labelledby="preamble-title">
      <div className="preamble-editor-heading">
        <div>
          <h3 id="preamble-title">פרטי המבחן והנחיות</h3>
          <p>אפשר לערוך או להסיר שורות. ההחלטה מה לכלול נעשית במסך יצירת המבחן.</p>
        </div>
      </div>
      {preamble.lines.length > 0 ? (
        <div className="preamble-lines">
          {preamble.lines.map((line) => (
            <div className="preamble-line-editor" key={line.reviewId}>
              <input
                type="text"
                value={line.text}
                onChange={(event) => updateLine(line.reviewId, event.target.value)}
                aria-label="עריכת שורת פרטי מבחן או הנחיות"
                dir="auto"
              />
              <button
                className="remove-choice-button"
                type="button"
                onClick={() => removeLine(line.reviewId)}
                aria-label="הסרת שורת פרטי מבחן או הנחיות"
                title="הסרת שורה"
              >×</button>
            </div>
          ))}
        </div>
      ) : <p className="field-hint">לא נשארו פרטים או הנחיות להצגה.</p>}
    </section>
  );
}

function getInitialTheme() {
  const savedTheme = window.localStorage.getItem("exam-shuffler-theme");
  if (savedTheme === "light" || savedTheme === "dark") return savedTheme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle");
  const [analysis, setAnalysis] = useState(null);
  const [reviewExam, setReviewExam] = useState(null);
  const [reviewStage, setReviewStage] = useState("choice");
  const [showValidation, setShowValidation] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [answerSource, setAnswerSource] = useState("none");
  const [sameAnswerPosition, setSameAnswerPosition] = useState("");
  const [sharedPositionNotice, setSharedPositionNotice] = useState("");
  const [pathError, setPathError] = useState("");
  const [generationBackStage, setGenerationBackStage] = useState("choice");
  const [generationSettings, setGenerationSettings] = useState(
    () => ({ ...DEFAULT_GENERATION_SETTINGS }),
  );
  const [generationStatus, setGenerationStatus] = useState("idle");
  const [generationError, setGenerationError] = useState("");
  const [generatedFiles, setGeneratedFiles] = useState([]);
  const mountedRef = useRef(true);
  const [error, setError] = useState("");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("exam-shuffler-theme", theme);
  }, [theme]);

  useEffect(() => (
    () => revokeGeneratedPdfUrls(generatedFiles)
  ), [generatedFiles]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  function selectFile(event) {
    const selected = event.target.files?.[0] || null;
    setFile(selected);
    setAnalysis(null);
    setReviewExam(null);
    setReviewStage("choice");
    setShowValidation(false);
    setReviewError("");
    setSameAnswerPosition("");
    setSharedPositionNotice("");
    setPathError("");
    setGenerationStatus("idle");
    setGenerationError("");
    setGeneratedFiles([]);
    setError("");
    setStatus("idle");
  }

  async function analyze() {
    if (!file) return;

    setStatus("loading");
    setError("");
    setAnalysis(null);
    setReviewExam(null);
    setReviewStage("choice");
    setShowValidation(false);
    setReviewError("");
    setSameAnswerPosition("");
    setSharedPositionNotice("");
    setPathError("");
    setGenerationStatus("idle");
    setGenerationError("");
    setGeneratedFiles([]);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("answer_source", answerSource);

    try {
      const response = await fetch(API_URL, { method: "POST", body: formData });
      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new Error("השרת החזיר תשובה שלא ניתן לקרוא. יש לנסות שוב.");
      }

      if (!response.ok) {
        throw new Error(formatError(response, payload));
      }
      if (!Array.isArray(payload.questions)) {
        throw new Error("תשובת השרת אינה כוללת ניתוח מבחן תקין.");
      }

      setAnalysis(payload);
      setReviewExam(createReviewExam(payload));
      setStatus("success");
    } catch (requestError) {
      setError(
        requestError instanceof TypeError
          ? "לא ניתן להתחבר לשירות הניתוח. יש לוודא שהשרת פועל ולנסות שוב."
          : requestError.message || "אירעה שגיאה לא צפויה. יש לנסות שוב.",
      );
      setStatus("error");
    }
  }

  const warnings = [
    ...(analysis?.analysis_warnings || []),
    ...(analysis?.warnings || []),
  ];
  const includedQuestions = getIncludedQuestions(reviewExam);
  const includedCount = includedQuestions.length;
  const totalCount = reviewExam?.questions.length || 0;
  const validationByQuestion = new Map(
    (reviewExam?.questions || []).map((question) => [question.reviewId, getQuestionIssues(question)]),
  );
  const correctCount = includedQuestions.filter((question) => question.correct_choice_id).length;
  const commonAnswerPositions = getCommonAnswerPositions(reviewExam);
  const commonPositionKey = commonAnswerPositions.join(",");
  const examDetailCount = reviewExam?.preamble.lines.filter(
    (line) => line.type !== "instructions",
  ).length || 0;
  const instructionCount = reviewExam?.preamble.lines.filter(
    (line) => line.type === "instructions",
  ).length || 0;
  const sharedPositionIsValid = answerSource !== "same_position"
    || commonAnswerPositions.includes(Number(sameAnswerPosition));
  const quickShuffleEligibility = getQuickShuffleEligibility(analysis, reviewExam);
  const generatedVersionCount = generationSettings.multiple_versions
    ? Number(generationSettings.number_of_versions)
    : 1;
  const stageCopy = {
    choice: ["הניתוח הושלם", "איך תרצו להמשיך?"],
    review: ["בדיקה ועריכה", "סקירת המבחן"],
    generation: ["הגדרות יצירה", "יצירת המבחן"],
    complete: ["היצירה הושלמה", "המבחן מוכן"],
  }[reviewStage];

  useEffect(() => {
    if (
      answerSource === "same_position"
      && sameAnswerPosition
      && !commonAnswerPositions.includes(Number(sameAnswerPosition))
    ) {
      setSameAnswerPosition("");
      setSharedPositionNotice(
        "המיקום שנבחר אינו קיים עוד בכל השאלות הכלולות. יש לבחור מיקום משותף חדש.",
      );
      setReviewExam((current) => (
        current ? clearSharedAnswerPosition(current) : current
      ));
    }
  }, [answerSource, sameAnswerPosition, commonPositionKey]);

  function changeSharedAnswerPosition(value) {
    setSharedPositionNotice("");
    if (!value) {
      setSameAnswerPosition("");
      setReviewExam((current) => (
        current ? clearSharedAnswerPosition(current) : current
      ));
      return;
    }
    const position = Number(value);
    if (!commonAnswerPositions.includes(position)) {
      setSharedPositionNotice("המיקום אינו זמין בכל השאלות הכלולות.");
      return;
    }
    setSameAnswerPosition(value);
    setReviewExam((current) => applySharedAnswerPosition(current, position));
  }

  function updateQuestion(reviewId, updater) {
    setReviewExam((current) => {
      const updated = {
        ...current,
        questions: current.questions.map((question) => (
        question.reviewId === reviewId
          ? { ...question, ...updater(question) }
          : question
        )),
      };
      return answerSource === "same_position" && sameAnswerPosition
        ? applySharedAnswerPosition(updated, Number(sameAnswerPosition))
        : updated;
    });
  }

  function confirmReview() {
    setShowValidation(true);
    setReviewError("");
    if (includedCount === 0) {
      setReviewError("יש לכלול לפחות שאלה אחת לפני האישור.");
      return;
    }
    const hasIssues = includedQuestions.some((question) => (
      validationByQuestion.get(question.reviewId).length > 0
    ));
    if (hasIssues) {
      setReviewError("יש לתקן את הבעיות המסומנות בשאלות הכלולות לפני ההמשך.");
      return;
    }
    setGenerationBackStage("review");
    setReviewStage("generation");
  }

  function openQuickShuffle() {
    const currentEligibility = getQuickShuffleEligibility(analysis, reviewExam);
    if (!currentEligibility.eligible) {
      setPathError(currentEligibility.reason);
      return;
    }
    setPathError("");
    setGenerationBackStage("choice");
    setReviewStage("generation");
  }

  function openReview() {
    setPathError("");
    setReviewStage("review");
  }

  async function generateVersions() {
    if (!sharedPositionIsValid) {
      setGenerationError("יש לבחור מיקום משותף תקין לתשובה הנכונה.");
      return;
    }
    setGenerationStatus("loading");
    setGenerationError("");
    setGeneratedFiles([]);
    try {
      const response = await fetch(GENERATE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewed_exam: buildReviewedGenerationExam(reviewExam, generationSettings),
          settings: {
            number_of_versions: generationSettings.multiple_versions
              ? Number(generationSettings.number_of_versions)
              : 1,
            shuffle_questions: generationSettings.shuffle_questions,
            shuffle_choices: generationSettings.shuffle_choices,
            answer_key_mode: generationSettings.answer_key_mode,
          },
        }),
      });
      if (!response.ok) {
        let payload;
        try {
          payload = await response.json();
        } catch {
          payload = null;
        }
        throw new Error(
          payload?.detail?.message ||
          "לא ניתן ליצור את קובצי המבחן. יש לבדוק את המבחן ולנסות שוב.",
        );
      }

      const pdfFiles = createGeneratedPdfDownloads(await response.arrayBuffer());
      if (!pdfFiles.length) {
        throw new Error("השרת לא החזיר קובצי PDF להורדה.");
      }
      if (!mountedRef.current) {
        revokeGeneratedPdfUrls(pdfFiles);
        return;
      }
      setGeneratedFiles(pdfFiles);
      setGenerationStatus("success");
      setReviewStage("complete");
    } catch (generationRequestError) {
      setGenerationError(
        generationRequestError instanceof TypeError
          ? "לא ניתן להתחבר לשירות יצירת הגרסאות. יש לוודא שהשרת פועל ולנסות שוב."
          : generationRequestError.message || "אירעה שגיאה ביצירת הגרסאות.",
      );
      setGenerationStatus("error");
    }
  }

  return (
    <main className="app-shell">
      <div className="content-wrap">
        <header className="app-header">
          <div>
            <p className="eyebrow">ניתוח מסמכים</p>
            <h1>מערבל מבחנים</h1>
          </div>
          <button
            className="theme-toggle"
            type="button"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            aria-label={`מעבר לתצוגה ${theme === "light" ? "כהה" : "בהירה"}`}
            aria-pressed={theme === "dark"}
            title={`מעבר לתצוגה ${theme === "light" ? "כהה" : "בהירה"}`}
          >
            <span aria-hidden="true">{theme === "light" ? "☾" : "☀"}</span>
            <span>תצוגה {theme === "light" ? "כהה" : "בהירה"}</span>
          </button>
        </header>

        <p className="intro">העלאת מבחן PDF עם טקסט זמין, ניתוח השאלות והצגת המבנה שזוהה.</p>

        <section className="upload-panel" aria-labelledby="upload-title">
          <div className="section-heading">
            <div>
              <h2 id="upload-title">בחירת מבחן</h2>
              <p>ניתן לנתח קובצי PDF הכוללים טקסט שניתן לסמן.</p>
            </div>
          </div>

          <fieldset className="answer-source-panel" disabled={Boolean(analysis) || status === "loading"}>
            <legend>מקור התשובות הנכונות</legend>
            <div className="answer-source-options">
              <label className="answer-source-option">
                <input
                  type="radio"
                  name="answer-source"
                  value="none"
                  checked={answerSource === "none"}
                  onChange={() => setAnswerSource("none")}
                />
                <span>אין תשובות נכונות מוגדרות</span>
              </label>
              <label className="answer-source-option">
                <input
                  type="radio"
                  name="answer-source"
                  value="same_position"
                  checked={answerSource === "same_position"}
                  onChange={() => setAnswerSource("same_position")}
                />
                <span>אותה תשובה נכונה בכל השאלות</span>
              </label>
              <label className="answer-source-option">
                <input
                  type="radio"
                  name="answer-source"
                  value="manual"
                  checked={answerSource === "manual"}
                  onChange={() => setAnswerSource("manual")}
                />
                <span>אגדיר תשובות לפי הצורך</span>
              </label>
            </div>
            {answerSource === "same_position" && (
              <p className="field-hint answer-source-hint">
                מיקום התשובה ייבחר לאחר הניתוח, לפי מספר התשובות שזוהה בפועל.
              </p>
            )}
          </fieldset>

          <div className="upload-controls">
            <label className="file-picker">
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={selectFile}
                aria-label="בחירת קובץ PDF"
              />
              <span className="file-picker-icon" aria-hidden="true">↑</span>
              <span>בחירת קובץ PDF</span>
            </label>
            <span className={`selected-file${file ? " has-file" : ""}`}>
              {file ? file.name : "לא נבחר קובץ"}
            </span>
            <button
              className="analyze-button"
              type="button"
              onClick={analyze}
              disabled={!file || status === "loading"}
            >
              {status === "loading" ? (
                <><span className="spinner" aria-hidden="true" />מנתח את המבחן...</>
              ) : "ניתוח המבחן"}
            </button>
          </div>
          {status === "idle" && !file && (
            <p className="field-hint">יש לבחור קובץ PDF כדי להתחיל בניתוח.</p>
          )}
          {status === "loading" && (
            <p className="loading-note" role="status">קורא את העמודים ומארגן את השאלות...</p>
          )}
          {status === "error" && (
            <div className="error-message" role="alert">{error}</div>
          )}
        </section>

        {analysis && reviewExam && (
          <section className="results-section" aria-labelledby="results-title">
            <div className="results-heading">
              <div>
                <p className="eyebrow">{stageCopy[0]}</p>
                <h2 id="results-title">{stageCopy[1]}</h2>
              </div>
              <span className="question-count">{includedCount} מתוך {totalCount} שאלות ייכללו</span>
            </div>

            {reviewStage === "complete" ? (
              <div className="completion-panel" role="status">
                <h3>קובצי המבחן נוצרו</h3>
                <p>נוצרו {generatedVersionCount} {generatedVersionCount === 1 ? "גרסה" : "גרסאות"}.</p>
                <p>{includedCount} שאלות בכל גרסה · {correctCount} תשובות ידועות · {includedCount - correctCount} לא הוגדרו</p>
                <div className="generated-file-list" aria-label="קובצי PDF להורדה">
                  {generatedFiles.map((generatedFile) => (
                    <article className="generated-file" key={generatedFile.filename}>
                      <span className="pdf-badge" aria-hidden="true">PDF</span>
                      <div className="generated-file-details">
                        <strong>{generatedFile.label}</strong>
                        <span dir="ltr">{generatedFile.filename}</span>
                      </div>
                      <a
                        className="generated-download"
                        href={generatedFile.url}
                        download={generatedFile.filename}
                      >הורדה</a>
                    </article>
                  ))}
                </div>
                <button className="text-button" type="button" onClick={() => setReviewStage("generation")}>חזרה להגדרות</button>
              </div>
            ) : reviewStage === "review" || reviewStage === "choice" ? (
              <div className="summary-strip">
                <div className="summary-item">
                  <span className="summary-label">סטטוס הניתוח</span>
                  <span className={`status-value ${analysis.analysis_status === "ready" ? "is-ready" : "is-review"}`}>
                    {analysis.analysis_status === "ready" ? "מוכן" : "נדרשת בדיקה"}
                  </span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">שאלות שייכללו</span>
                  <span className="summary-value">{includedCount} / {totalCount}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">תשובות נכונות שסומנו</span>
                  <span className="summary-value">{correctCount}</span>
                </div>
              </div>
            ) : null}

            {reviewStage === "choice" && (
              <div className="path-choice-panel">
                <div className="path-actions">
                  <div className="path-action">
                    <button
                      className="analyze-button"
                      type="button"
                      onClick={openQuickShuffle}
                      disabled={!quickShuffleEligibility.eligible}
                    >ערבול מהיר</button>
                    {!quickShuffleEligibility.eligible && (
                      <p className="path-explanation">{quickShuffleEligibility.reason}</p>
                    )}
                  </div>
                  <div className="path-action">
                    <button className="secondary-action" type="button" onClick={openReview}>
                      בדיקה ועריכה
                    </button>
                    <p className="path-explanation">מעבר על השאלות, התשובות והפרטים לפני היצירה.</p>
                  </div>
                </div>
                {pathError && <p className="error-message" role="alert">{pathError}</p>}
              </div>
            )}

            {reviewStage === "review" && warnings.length > 0 && (
              <aside className="warning-panel" aria-label="הערות לניתוח">
                <h3>הערות לבדיקה</h3>
                <ul>{warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>
              </aside>
            )}

            {reviewStage === "review" && (
              <>
                <div className="review-top-actions">
                  <span>אפשר להמשיך להגדרות בכל שלב; בעיות בשאלות יוצגו לפני המעבר.</span>
                  <button className="analyze-button confirm-button" type="button" onClick={confirmReview}>
                    אישור המבחן והמשך
                  </button>
                </div>
                {reviewError && <p className="question-validation review-top-validation" role="alert">{reviewError}</p>}
                <PreambleEditor
                  preamble={reviewExam.preamble}
                  onChange={(preamble) => setReviewExam((current) => ({ ...current, preamble }))}
                />
                <div className="question-list">
                  {reviewExam.questions.map((question) => (
                    <QuestionCard
                      question={question}
                      issues={validationByQuestion.get(question.reviewId)}
                      showValidation={showValidation}
                      sharedAnswerMode={answerSource === "same_position"}
                      onChange={(updater) => updateQuestion(question.reviewId, updater)}
                      key={question.reviewId}
                    />
                  ))}
                </div>
                <div className="review-footer">
                  <span>{includedCount} מתוך {totalCount} שאלות ייכללו</span>
                  <div className="review-actions-footer">
                    <button className="analyze-button confirm-button" type="button" onClick={confirmReview}>
                    אישור המבחן והמשך
                    </button>
                  </div>
                </div>
              </>
            )}

            {reviewStage === "generation" && (
              <div className="generation-panel">
                <p className="generation-lead">{includedCount} שאלות ייכללו</p>
                <p className="generation-detail">{correctCount} תשובות ידועות · {includedCount - correctCount} לא ידועות</p>
                <div className="generation-controls">
                  <section className="generation-setting-section" aria-labelledby="content-settings-title">
                    <h3 id="content-settings-title">1. תוכן</h3>
                    <div className="included-content-row">
                      <span aria-hidden="true">✓</span>
                      <strong>שאלות ותשובות</strong>
                      <small>נכלל תמיד</small>
                    </div>
                    <label className="setting-toggle">
                      <input
                        type="checkbox"
                        checked={generationSettings.include_exam_details}
                        disabled={examDetailCount === 0}
                        onChange={(event) => setGenerationSettings((current) => ({ ...current, include_exam_details: event.target.checked }))}
                      />
                      <span>פרטי המבחן</span>
                      <small>{examDetailCount ? `${examDetailCount} שורות זמינות` : "לא זוהו פרטים"}</small>
                    </label>
                    <label className="setting-toggle">
                      <input
                        type="checkbox"
                        checked={generationSettings.include_instructions}
                        disabled={instructionCount === 0}
                        onChange={(event) => setGenerationSettings((current) => ({ ...current, include_instructions: event.target.checked }))}
                      />
                      <span>הוראות המבחן</span>
                      <small>{instructionCount ? `${instructionCount} שורות זמינות` : "לא זוהו הוראות"}</small>
                    </label>
                    {answerSource === "same_position" && (
                      <SharedAnswerPositionControl
                        positions={commonAnswerPositions}
                        value={sameAnswerPosition}
                        notice={sharedPositionNotice}
                        onChange={changeSharedAnswerPosition}
                      />
                    )}
                  </section>
                  <section className="generation-setting-section" aria-labelledby="shuffle-settings-title">
                    <h3 id="shuffle-settings-title">2. ערבוב</h3>
                    <label className="setting-toggle">
                      <input
                        type="checkbox"
                        checked={generationSettings.shuffle_questions}
                        onChange={(event) => setGenerationSettings((current) => ({ ...current, shuffle_questions: event.target.checked }))}
                      />
                      <span>ערבוב סדר השאלות</span>
                    </label>
                    <label className="setting-toggle">
                      <input
                        type="checkbox"
                        checked={generationSettings.shuffle_choices}
                        onChange={(event) => setGenerationSettings((current) => ({ ...current, shuffle_choices: event.target.checked }))}
                      />
                      <span>ערבוב סדר התשובות</span>
                    </label>
                  </section>
                  <section className="generation-setting-section" aria-labelledby="version-settings-title">
                    <h3 id="version-settings-title">3. גרסאות</h3>
                    <label className="setting-toggle">
                      <input
                        type="radio"
                        name="version-mode"
                        checked={!generationSettings.multiple_versions}
                        onChange={() => setGenerationSettings((current) => ({
                          ...current,
                          multiple_versions: false,
                          number_of_versions: "1",
                        }))}
                      />
                      <span>גרסה אחת</span>
                    </label>
                    <label className="setting-toggle">
                      <input
                        type="radio"
                        name="version-mode"
                        checked={generationSettings.multiple_versions}
                        onChange={() => setGenerationSettings((current) => ({
                          ...current,
                          multiple_versions: true,
                          number_of_versions: current.number_of_versions === "1" ? "2" : current.number_of_versions,
                        }))}
                      />
                      <span>מספר גרסאות</span>
                    </label>
                    {generationSettings.multiple_versions && (
                      <label className="version-count-control">
                        <span>מספר גרסאות</span>
                        <input
                          type="number"
                          min="2"
                          max="10"
                          step="1"
                          value={generationSettings.number_of_versions}
                          onChange={(event) => setGenerationSettings((current) => ({ ...current, number_of_versions: event.target.value }))}
                        />
                      </label>
                    )}
                  </section>
                  <fieldset className="generation-setting-section answer-key-settings">
                    <legend>4. מפתח תשובות</legend>
                    <label className="setting-toggle">
                      <input
                        type="radio"
                        name="answer-key-mode"
                        value="separate"
                        checked={generationSettings.answer_key_mode === "separate"}
                        onChange={(event) => setGenerationSettings((current) => ({ ...current, answer_key_mode: event.target.value }))}
                      />
                      <span>קובץ נפרד</span>
                    </label>
                    <label className="setting-toggle">
                      <input
                        type="radio"
                        name="answer-key-mode"
                        value="appended"
                        checked={generationSettings.answer_key_mode === "appended"}
                        onChange={(event) => setGenerationSettings((current) => ({ ...current, answer_key_mode: event.target.value }))}
                      />
                      <span>בסוף המבחן</span>
                    </label>
                    <label className="setting-toggle">
                      <input
                        type="radio"
                        name="answer-key-mode"
                        value="both"
                        checked={generationSettings.answer_key_mode === "both"}
                        onChange={(event) => setGenerationSettings((current) => ({ ...current, answer_key_mode: event.target.value }))}
                      />
                      <span>גם וגם</span>
                    </label>
                  </fieldset>
                </div>
                {generationError && <p className="error-message generation-error" role="alert">{generationError}</p>}
                <div className="generation-actions">
                  <button className="text-button" type="button" onClick={() => setReviewStage(generationBackStage)} disabled={generationStatus === "loading"}>
                    {generationBackStage === "review" ? "חזרה לבדיקה" : "חזרה לבחירת מסלול"}
                  </button>
                  <button
                    className="analyze-button confirm-button"
                    type="button"
                    onClick={generateVersions}
                    disabled={generationStatus === "loading" || generatedVersionCount < 1 || generatedVersionCount > 10 || !sharedPositionIsValid}
                  >
                    {generationStatus === "loading" ? <><span className="spinner" aria-hidden="true" />יוצר את המבחן...</> : "יצירת המבחן"}
                  </button>
                </div>
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
