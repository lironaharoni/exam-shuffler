import json
from models import Choice, Question, Exam


def load_exam_data(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return data


def load_exam(file_path):
    data = load_exam_data(file_path)

    questions = []

    for question_data in data["questions"]:
        choices = []

        for choice_text in question_data["choices"]:
            choice = Choice(choice_text)
            choices.append(choice)

        correct_index = question_data["correct_choice_index"]
        correct_choice = choices[correct_index]

        question = Question(
            question_data["text"],
            choices,
            correct_choice
        )

        questions.append(question)

    return Exam(questions)