import copy


def generate_versions(exam, number_of_versions):
    versions = []

    for _ in range(number_of_versions):
        version = copy.deepcopy(exam)
        version.shuffle_all_choices()
        version.shuffle_questions()
        versions.append(version)

    return versions