import { useEffect, useState } from "react";

const API_URL = "http://127.0.0.1:8000/analyze-exam";

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
  return {
    ...clonedPayload,
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

function validateQuestion(question) {
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

function QuestionCard({ question, issues, showValidation, onChange }) {
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
                  aria-label={`סימון תשובה ${choice.label} כנכונה`}
                />
                <span>נכונה</span>
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
  const [reviewStage, setReviewStage] = useState("review");
  const [showValidation, setShowValidation] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("exam-shuffler-theme", theme);
  }, [theme]);

  function selectFile(event) {
    const selected = event.target.files?.[0] || null;
    setFile(selected);
    setAnalysis(null);
    setReviewExam(null);
    setReviewStage("review");
    setShowValidation(false);
    setError("");
    setStatus("idle");
  }

  async function analyze() {
    if (!file) return;

    setStatus("loading");
    setError("");
    setAnalysis(null);
    setReviewExam(null);
    setReviewStage("review");
    setShowValidation(false);
    const formData = new FormData();
    formData.append("file", file);

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
  const includedQuestions = reviewExam?.questions.filter((question) => question.included) || [];
  const includedCount = includedQuestions.length;
  const totalCount = reviewExam?.questions.length || 0;
  const validationByQuestion = new Map(
    (reviewExam?.questions || []).map((question) => [question.reviewId, validateQuestion(question)]),
  );
  const correctCount = includedQuestions.filter((question) => question.correct_choice_id).length;

  function updateQuestion(reviewId, updater) {
    setReviewExam((current) => ({
      ...current,
      questions: current.questions.map((question) => (
        question.reviewId === reviewId
          ? { ...question, ...updater(question) }
          : question
      )),
    }));
  }

  function confirmReview() {
    setShowValidation(true);
    const hasIssues = includedQuestions.some((question) => (
      validationByQuestion.get(question.reviewId).length > 0
    ));
    if (!hasIssues) setReviewStage("confirmed");
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
                <p className="eyebrow">{reviewStage === "review" ? "בדיקה ועריכה" : "הבדיקה הושלמה"}</p>
                <h2 id="results-title">{reviewStage === "review" ? "סקירת המבחן" : "המבחן מוכן לשלב הבא"}</h2>
              </div>
              <span className="question-count">{includedCount} מתוך {totalCount} שאלות ייכללו</span>
            </div>

            {reviewStage === "confirmed" ? (
              <div className="completion-panel" role="status">
                <h3>המבחן מוכן לשלב יצירת הגרסאות</h3>
                <p>{includedCount} שאלות ייכללו</p>
                <p>{correctCount} תשובות נכונות הוגדרו</p>
                <p>{includedCount - correctCount} תשובות עדיין לא הוגדרו</p>
                <button className="text-button" type="button" onClick={() => setReviewStage("review")}>חזרה לעריכה</button>
              </div>
            ) : (
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
            )}

            {warnings.length > 0 && (
              <aside className="warning-panel" aria-label="הערות לניתוח">
                <h3>הערות לבדיקה</h3>
                <ul>{warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>
              </aside>
            )}

            {reviewStage === "review" && (
              <>
                <div className="question-list">
                  {reviewExam.questions.map((question) => (
                    <QuestionCard
                      question={question}
                      issues={validationByQuestion.get(question.reviewId)}
                      showValidation={showValidation}
                      onChange={(updater) => updateQuestion(question.reviewId, updater)}
                      key={question.reviewId}
                    />
                  ))}
                </div>
                <div className="review-footer">
                  <span>{includedCount} מתוך {totalCount} שאלות ייכללו</span>
                  <button className="analyze-button confirm-button" type="button" onClick={confirmReview}>
                    אישור המבחן והמשך
                  </button>
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </main>
  );
}