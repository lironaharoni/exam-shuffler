from generator import generate_versions
from answer_key import generate_answer_key
from exporter import export_exam, export_answer_key
import display
import loader

exam = loader.load_exam("sample_exam.json")

versions = generate_versions(exam, 3)

print("ORIGINAL EXAM")
display.print_exam(exam)

for i, version in enumerate(versions, start=1):
    print("VERSION", i)
    display.print_exam(version)

    answer_key = generate_answer_key(version)
    display.print_answer_key(answer_key)

    export_exam(version, f"version_{i}.txt")
    export_answer_key(answer_key, f"version_{i}_answer_key.txt")