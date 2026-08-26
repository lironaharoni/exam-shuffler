def export_exam(exam, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        for question_number, question in enumerate(exam.questions, start=1):
            file.write(f"{question_number}. {question.text}\n")

            for choice_number, choice in enumerate(question.choices, start=1):
                file.write(f"{choice_number}) {choice.text}\n")

            file.write("\n")


def export_answer_key(answer_key, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        for question_number, correct_position in enumerate(answer_key, start=1):
            file.write(
                f"Question {question_number}: {correct_position}\n"
            )