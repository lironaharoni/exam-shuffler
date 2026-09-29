# Exam Shuffler

Exam Shuffler is a system for shuffling questions and answer choices in multiple-choice exams while preserving the correct answers.

The current focus is building the core MVP.

## Local document analysis

Start the FastAPI backend from the repository root:

```powershell
\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

In a second terminal, start the React frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The frontend sends native-text PDF uploads to `http://127.0.0.1:8000/analyze-exam`.