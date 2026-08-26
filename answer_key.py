def generate_answer_key(exam):
    answers = []

    for question in exam.questions:
        correct_position = question.choices.index(question.correct_choice) + 1
        answers.append(correct_position)

    return answers
