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

function QuestionCard({ question }) {
  return (
    <article className="question-card">
      <header className="question-heading">
        <span className="question-number">שאלה {question.number}</span>
        <span className="question-page">עמוד {question.page_number}</span>
        {question.needs_review && (
          <span className="review-flag">נדרשת בדיקה</span>
        )}
      </header>

      <p className="question-text" dir="auto">{question.text}</p>
      <Visuals
        visuals={question.question_visuals}
        label={`שאלה ${question.number}`}
      />

      {question.choices?.length > 0 && (
        <ol className="choice-list">
          {question.choices.map((choice, index) => (
            <li className="choice-row" key={`${choice.label}-${index}`}>
              <span className="choice-label">{choice.label}</span>
              <div className="choice-content">
                {choice.text ? <p dir="auto">{choice.text}</p> : null}
                <Visuals
                  visuals={choice.visuals}
                  label={`שאלה ${question.number}, תשובה ${choice.label}`}
                />
              </div>
            </li>
          ))}
        </ol>
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
  const [error, setError] = useState("");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("exam-shuffler-theme", theme);
  }, [theme]);

  function selectFile(event) {
    const selected = event.target.files?.[0] || null;
    setFile(selected);
    setAnalysis(null);
    setError("");
    setStatus("idle");
  }

  async function analyze() {
    if (!file) return;

    setStatus("loading");
    setError("");
    setAnalysis(null);
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

        {analysis && (
          <section className="results-section" aria-labelledby="results-title">
            <div className="results-heading">
              <div>
                <p className="eyebrow">תוצאות הניתוח</p>
                <h2 id="results-title">המבחן שזוהה</h2>
              </div>
              <span className="question-count">
                {analysis.questions.length === 1
                  ? "שאלה אחת"
                  : `${analysis.questions.length} שאלות`}
              </span>
            </div>

            <div className="summary-strip">
              <div className="summary-item">
                <span className="summary-label">סטטוס הניתוח</span>
                <span className={`status-value ${analysis.analysis_status === "ready" ? "is-ready" : "is-review"}`}>
                  {analysis.analysis_status === "ready" ? "מוכן" : "נדרשת בדיקה"}
                </span>
              </div>
              <div className="summary-item">
                <span className="summary-label">מוכן ליצירת גרסאות</span>
                <span className="summary-value">{analysis.safe_to_generate ? "כן" : "לא"}</span>
              </div>
              <div className="summary-item">
                <span className="summary-label">שאלות שזוהו</span>
                <span className="summary-value">{analysis.questions.length}</span>
              </div>
            </div>

            {warnings.length > 0 && (
              <aside className="warning-panel" aria-label="הערות לניתוח">
                <h3>הערות לבדיקה</h3>
                <ul>{warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>
              </aside>
            )}

            <div className="question-list">
              {analysis.questions.map((question, index) => (
                <QuestionCard
                  question={question}
                  key={`${question.number}-${question.page_number}-${index}`}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}