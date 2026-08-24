class Choice:
    def __init__(self, text):
        self.text = text


class Question:
    def __init__(self, text, choices, correct_choice):
        self.text = text
        self.choices = choices
        self.correct_choice = correct_choice

class Exam:
    def __init__(self, questions):
        self.questions = questions