import copy
import csv
import itertools

import click
import yaml
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


@click.command()
@click.argument('csvfile', type=click.File('r', encoding='utf-8'))
@click.argument('metadata-name', default="metadata.yml")
@click.option('-P', '--meta-prefix',
              default="meta-", show_default=True,
              help="Prefix for file describing how to build metadata file")
@click.option('-t', '--table-name', default='sheelon', show_default=True,
              help="Name of table to create and place the data in")
@click.option('-D', '--db-name',
              type=click.Path(dir_okay=False, writable=True),
              default='sheelon.db',
              help="Name of database file to place the data in")
def main(csvfile, db_name, table_name, metadata_name, meta_prefix):
    # "arg parsing"

    try:
        db = Database(db_name, recreate=True)
    except OSError:
        raise InvocationError(f"Cannot use '{db_name}' as a database file")

    reader = csv.reader(csvfile)
    csv_table = read_sheelon(reader)
    csv_rows = write_db_table(db, table_name, csv_table)
    make_metadata_yml(csv_rows, name=metadata_name, prefix=meta_prefix)
    

def read_sheelon(reader):
    try:
        row1 = next(reader)
        row2 = next(reader)
    except OSError:
        # TODO: Bug, csvfile_name not available in this function
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

        if ("רכיבי" in t1 or "מדד" in t1) and "מדדים" not in t1:
            header_row.append(SPECIAL_SEP.join((t1, t2)))
        else:
            # Consider including t1 somehow... NON_SPECIAL_SEP?
            header_row.append(t2)
    return itertools.chain([header_row], reader)


def write_db_table(db, table_name, csv_table):
    table = db[table_name]
    header = next(csv_table)
    id_column = "row_number"
    id_provider = itertools.count(3)

    row_dicts = []
    for row in csv_table:
        d = {id_column: next(id_provider)}
        for name,val in zip(header,row):
            if name in KILL_COLUMNS:
                continue
            if val:
                val = float(val)
                if val.is_integer():
                    val = int(val)
            else:
                val = None
            d[name] = val
        row_dicts.append(d)
    
    table.insert_all(row_dicts, pk=id_column)
    return row_dicts


def make_metadata_yml(data_dicts, name="metadata.yml", prefix="meta-"):

    IMPUTE = 0
    CALC_SORTER = 1
    
    source_name = prefix+name
    try:
        with open(source_name) as f:
            meta_meta = yaml.safe_load(f)
    except IOError:
        raise InvocationError(f"Cannot read file '{source_name}' to make '{name}'")

    metadata = meta_meta['preamble']
    metadashboard = meta_meta['dashboard']
    dashboard = copy.deepcopy(metadashboard['static'] )
    dashgen = metadashboard['generate']
    cols = data_dicts[0].keys()
    metrics = [
        col for col in cols if SPECIAL_SEP not in col and col.startswith('מדד')
    ]
    metrics_query = " UNION ALL ".join(
        dashgen['query']['main_metric_clause_template'].format(field_name=metric)
        for metric in metrics
    )
    metrics_chart = copy.deepcopy(dashgen['metrics']['static'])
    metrics_chart['query'] = " ".join(
        (dashgen['query']['preamble'], metrics_query)
    )
    dashboard['charts']['main_metrics'] = metrics_chart
    
    for idx, metric in enumerate(metrics, start=1):
        sub_metrics = [
            col for col in cols 
            if SPECIAL_SEP in col and (
                col.startswith(metric) or
                col.startswith(metric.replace('מדד', 'רכיבי'))
            )
        ]
        sub_metrics_query = " UNION ALL ".join(
            dashgen['query']['sub_metric_clause_template'].format(
                # Note replaces to double the quotes -- this is very poor man's SQL quoting
                field_name=sub_metric.replace('"', '""'),
                sub_field_name=sub_metric.split(SPECIAL_SEP)[1].replace("'", "''")
            )
            for sub_metric in sub_metrics
        )
        sub_metrics_chart = copy.deepcopy(dashgen['metrics']['static'])
        sub_metrics_chart['title'] = metric
        sub_metrics_chart['query'] = " ".join(
            (dashgen['query']['preamble'], sub_metrics_query)
        )
        dashboard['charts'][f'm-{idx:02d}'] = sub_metrics_chart

    dashboard['layout'].extend(
        pairs(
            f'm-{j:02d}' for j in range(len(metrics)+1)
            if f'm-{j:02d}' in dashboard['charts']
        )
    )

        
    metadata['plugins']['datasette-dashboards'] = {
        metadashboard['name']: dashboard
    }
    with open(name, 'wt') as out:
        yaml.safe_dump(metadata, out, allow_unicode=True)

def pairs(seq, fill='.'):
    i = iter(seq)
    return itertools.zip_longest(i, i, fillvalue=fill)

if __name__ == "__main__":
    main()
