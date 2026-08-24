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
    [1, 2, 3, 4],
    c4
)

exam = Exam([question1, question2])

for question in exam.questions:
    print(question.text)
    print("Correct answer:", question.correct_choice.text)
    print()