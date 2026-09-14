from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _choice_label(position):
    return chr(64 + position)


def export_exam(exam, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        for question_number, question in enumerate(exam.questions, start=1):
            file.write(f"{question_number}. {question.text}\n")

            for choice_number, choice in enumerate(question.choices, start=1):
                file.write(f"{_choice_label(choice_number)}) {choice.text}\n")

            file.write("\n")


def export_answer_key(answer_key, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        for question_number, correct_position in enumerate(answer_key, start=1):
            label = _choice_label(correct_position)
            file.write(
                f"Question {question_number}: {label}\n"
            )


def export_exam_pdf(exam, file_path):
    pdf = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter
    y = height - 40

    pdf.setTitle("Shuffled Exam")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "Shuffled Exam")
    y -= 30

    for question_number, question in enumerate(exam.questions, start=1):
        if y < 60:
            pdf.showPage()
            y = height - 40

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, f"{question_number}. {question.text}")
        y -= 18

        for choice_number, choice in enumerate(question.choices, start=1):
            if y < 60:
                pdf.showPage()
                y = height - 40

            label = _choice_label(choice_number)
            pdf.setFont("Helvetica", 11)
            pdf.drawString(72, y, f"{label}) {choice.text}")
            y -= 16

        y -= 10

    pdf.save()


def export_answer_key_pdf(answer_key, file_path):
    pdf = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter
    y = height - 40

    pdf.setTitle("Answer Key")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "Answer Key")
    y -= 30

    for question_number, correct_position in enumerate(answer_key, start=1):
        if y < 60:
            pdf.showPage()
            y = height - 40

        pdf.setFont("Helvetica", 12)
        label = _choice_label(correct_position)
        pdf.drawString(50, y, f"Question {question_number}: {label}")
        y -= 18

    pdf.save()