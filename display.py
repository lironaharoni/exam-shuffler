def print_exam(exam):
    for question in exam.questions:
        print(question.text)

        for choice in question.choices:
            print(choice.text)

        print("Correct answer:", question.correct_choice.text)
        print()

def print_answer_key(answer_key):
    print("ANSWER KEY")

    for question_number, correct_position in enumerate(answer_key, start=1):
        print("Question", question_number, ":", correct_position)

    print()