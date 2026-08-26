from generator import generate_versions
from answer_key import generate_answer_key
import display
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

versions = generate_versions(exam, 3)

print("ORIGINAL EXAM")
display.print_exam(exam)

for i, version in enumerate(versions, start=1):
    print("VERSION", i)
    display.print_exam(version)

    answer_key = generate_answer_key(version)
    display.print_answer_key(answer_key)
