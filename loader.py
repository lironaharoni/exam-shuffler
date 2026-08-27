import json
from models import Choice, Question, Exam


def load_exam_data(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return data


def load_exam(file_path):
    data = load_exam_data(file_path)

    if len(data["questions"]) == 0:
        raise ValueError("Exam must contain at least one question")

    questions = []

    for question_data in data["questions"]:
        choices = []

        for choice_text in question_data["choices"]:
            choice = Choice(choice_text)
            choices.append(choice)

        if len(choices) == 0:
            raise ValueError("Question must contain at least one choice")

        correct_index = question_data["correct_choice_index"]

        if correct_index < 0 or correct_index >= len(choices):
            raise ValueError("Invalid correct_choice_index")

        correct_choice = choices[correct_index]

        question = Question(
            question_data["text"],
            choices,
            correct_choice
        )

        questions.append(question)

    return Exam(questions)