import copy


from models import Choice, Question, Exam
london = Choice("London")
paris = Choice("Paris")
madrid = Choice("Madrid")
rome = Choice("Rome")

question1 = Question(
    "What is the capital of France?",
    [london, paris, madrid, rome],
    paris
)

c1 = Choice("1")
c2 = Choice("2")
c3 = Choice("3")
c4 = Choice("4")

question2 = Question(
    "2*2 is:",
    [c1, c2, c3, c4],
    c4
)

exam = Exam([question1, question2])

versions = []

for i in range(3):
    version = copy.deepcopy(exam)
    version.shuffle_all_choices()
    version.shuffle_questions()
    versions.append(version)

print("ORIGINAL EXAM")

for question in exam.questions:
    print(question.text)

    for choice in question.choices:
        print(choice.text)

    print("Correct answer:", question.correct_choice.text)
    print()

for i, version in enumerate(versions, start=1):
    print("VERSION", i)

    for question in version.questions:
        print(question.text)

        for choice in question.choices:
            print(choice.text)

        print("Correct answer:", question.correct_choice.text)
        print()

    # רק אחרי שסיימנו את כל השאלות
    print("ANSWER KEY")

    for question_number, question in enumerate(version.questions, start=1):
        correct_position = question.choices.index(question.correct_choice) + 1
        print("Question", question_number, ":", correct_position)

    print()
