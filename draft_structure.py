"""
Try to guess from the CSV the structure of the questions,
as a draft to be edited manually
"""

import csv
import itertools
import sys

import yaml


NO_SECTION = "-שאלות נוספות-"


def main(argv: list[str]):
    # "arg parsing"
    if len(argv)!=1:
        raise InvocationError("Required single arg: csvfile-name")
    csvfile_name = argv[0]

    try:
        # Open the CSV file
        with open(csvfile_name, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            structure = guess_structure(reader)
            yaml.safe_dump(structure, sys.stdout, allow_unicode=True)

    except OSError:
        raise InvocationError(f"Cannot read csv file '{csvfile_name}'")


def guess_structure(reader):
    row1 = next(reader)
    row2 = next(reader)
    data_rows = list(reader)  # Rest of rows

    if len(row1)!=len(row2):
        raise InvocationError(f"header in CSV file is malformed")

    structure = {NO_SECTION: {}}
    for col_no, (t1, t2) in enumerate(zip(row1, row2)):
        t1 = onespace(t1)
        t2 = onespace(t2)
        
        if not t2 or "Response" in t2:
            # Question is in row 1
            if t1 in structure[NO_SECTION]:
                raise ValueError(f"Malformed CSV file: Two questions '{t1}'")
            if t1.isascii():
                # English marks technical fields
                continue
            responses = {row[col_no] for row in data_rows}
            structure[NO_SECTION][t1] = guess_type_from_responses(responses)
            continue
        
        if t1:
            if "אנא ענו על השאלות הבאות" in t1:
                t1 = last_t1 = ""
            else:
                last_t1 = t1
        else:
            t1 = last_t1
        # "בחר/י" marks a series of boolean fields - a "pick 3 options" question
        # Represented in structure as question with name t1, and type set to
        # a list of all the t2 values
        if "בחר/י" in t1:
            structure[NO_SECTION].setdefault(t1, [])
            structure[NO_SECTION][t1].append(t2)
        else:
            if t2.isascii():
                # English marks technical fields
                continue
            section = t1 or NO_SECTION
            structure.setdefault(section, {})
            if t2 in structure[section]:
                raise ValueError(f"Two questions '{t2}' under '{t1}'")
            responses = {row[col_no] for row in data_rows}
            structure[section][t2] = guess_type_from_responses(responses)

    return structure


def onespace(t: str):
    "Normalize whitespace within string t"
    if t:
        return " ".join(t.split())
    else:
        return t


def guess_type_from_responses(responses: set):
    # Guess question type from set of responses
    responses.discard(None)
    responses.discard("")
    try:
        # Numbers can appear as floats or ints, but come from CSV as strings
        responses = {float(r) for r in responses}
        if all(f==int(f) for f in responses):
            responses = {int(f) for f in responses}
    except ValueError:
        pass
    if responses <= {1, 2, 3}:
        return "שלוש"
    elif len(responses) <= 5:
        return "חמש"
    else:
        return "טקסט"


if __name__ == "__main__":
    main(sys.argv[1:])
