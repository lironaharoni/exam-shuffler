import random

class Choice:
    def __init__(self, text):
        self.text = text


class Question:
    def __init__(self, text, choices, correct_choice):
        self.text = text
        self.choices = choices
        self.correct_choice = correct_choice

    def shuffle_choices(self):
        random.shuffle(self.choices)

class Exam:
    def __init__(self, questions):
        self.questions = questions

    def shuffle_all_choices(self):
        for question in self.questions:
            question.shuffle_choices()

    def shuffle_questions(self):
        random.shuffle(self.questions)