import csv
import itertools

from sqlite_utils import Database


class InvocationError(ValueError):
    pass

SPECIAL_SEP = "÷"  # Consider \n instead
KILL_COLUMNS = (
    "Collector ID",
    "Start Date",
    "End Date",
    "IP Address",
    "Email Address",
    "First Name",
    "Last Name",
    "Custom Data 1",
)


def main(argv: list[str], db_name="sheelon.db", table_name="sheelon"):
    # "arg parsing"
    if len(argv)!=1:
        raise InvocationError("Required single arg: csvfile-name")
    csvfile_name = argv[0]
    
    try:
        # Open the CSV file
        f = open(csvfile_name, newline='', encoding='utf-8')
    except OSError:
        raise InvocationError(f"Cannot read csv file '{csvfile_name}'")

    with f:
        try:
            db = Database(db_name, recreate=True)
        except OSError:
            raise InvocationError(f"Cannot use '{db_name}' as a database file")

        reader = csv.reader(f)
        csv_table = read_sheelon(reader)
        write_db_table(db, table_name, csv_table)
    

def read_sheelon(reader):
    try:
        row1 = next(reader)
        row2 = next(reader)
    except OSError:
        raise InvocationError(f"Cannot read header from '{csvfile_name}'")

    if len(row1)!=len(row2):
        raise InvocationError(f"header from '{csvfile_name}' is malformed")

    last_t1 = None
    header_row = []
    for (t1, t2) in zip(row1, row2):
        if not t2 or "Response" in t2:
            header_row.append(t1)
            continue
        
        if t1:
            if "אנא ענו על השאלות הבאות" in t1:
                t1 = last_t1 = ""
            else:
                last_t1 = t1
        else:
            t1 = last_t1
        # "בחר/י" marks a series of boolean fields
        if "בחר/י" in t1:
            header_row.append(SPECIAL_SEP.join((t1, t2)))
        else:
            # Consider including t1 somehow... NON_SPECIAL_SEP?
            header_row.append(t2)
    return itertools.chain([header_row], reader)


def write_db_table(db, table_name, csv_table):
    table = db[table_name]
    header = next(csv_table)
    id_column = header[0]

    # This is quite patchy...
    bool_columns = {
        name: bool
        for name in header
        if SPECIAL_SEP in name
    }
    int_columns = {
        name: int
        for name in header
        if name.startswith('שנות')
    }
    
    table.insert_all(
        (
            {
                name: bool(val) if name in bool_columns else val
                for name,val in zip(header,row)
                if name not in KILL_COLUMNS
            }
            for row in csv_table
        ),
        pk=id_column, columns={**bool_columns, **int_columns}
    )


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
