from models import Choice, Question, Exam


def read_exam_text(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        text = file.read()

    return text


def is_question_line(line):
    parts = line.split(". ", 1)

    return len(parts) == 2 and parts[0].isdigit()


def is_choice_line(line):
    return (
        len(line) >= 3
        and line[0].isalpha()
        and line[1:3] == ". "
    )


def classify_line(line):
    if line == "":
        return "EMPTY"

    if line.startswith("Correct:"):
        return "CORRECT"

    if is_question_line(line):
        return "QUESTION"

    if is_choice_line(line):
        return "CHOICE"

    return "OTHER"


def parse_questions(text):
    lines = text.splitlines()

    questions = []
    current_question = None

    for line in lines:
        line = line.strip()
        line_type = classify_line(line)

        if line_type == "QUESTION":
            question_text = line.split(". ", 1)[1]

            current_question = {
                "text": question_text,
                "choices": [],
                "correct_label": None
            }

            questions.append(current_question)

        elif line_type == "CHOICE" and current_question is not None:
            label, choice_text = line.split(". ", 1)

            current_question["choices"].append(
                (label, choice_text)
            )

        elif line_type == "CORRECT" and current_question is not None:
            correct_label = line.split(":", 1)[1].strip()
            current_question["correct_label"] = correct_label

    return questions


def parse_exam(text):
    parsed_questions = parse_questions(text)

    questions = []

    for parsed_question in parsed_questions:
        choices = []
        choices_by_label = {}

        for label, choice_text in parsed_question["choices"]:
            choice = Choice(choice_text)

            choices.append(choice)
            choices_by_label[label] = choice

        correct_label = parsed_question["correct_label"]

        if correct_label not in choices_by_label:
            raise ValueError(
                "Correct answer label does not match any choice"
            )

        correct_choice = choices_by_label[correct_label]

        question = Question(
            parsed_question["text"],
            choices,
            correct_choice
        )

        questions.append(question)

    return Exam(questions)