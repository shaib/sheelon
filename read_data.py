import copy
import csv
import itertools
from pathlib import Path

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
CLICK_CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])



@click.command(context_settings=CLICK_CONTEXT_SETTINGS)
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
    meta_maker = MetadataWriter(
        name=metadata_name, prefix=meta_prefix,
        db_name=Path(db_name).stem, table_name=table_name
    )
    meta_maker.make_for_columns(csv_rows[0].keys())
    

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


class MetadataWriter:
    """
    Write a metadata file for datasette based on meta-metadata
    definitions, and the data itself
    """
    def __init__(self,
                 name="metadata.yml", prefix="meta-",
                 db_name="sheelon", table_name="sheelon"):
        # Read and prepare meta-metadata for use later
        meta_meta = read_meta_meta(prefix, name)
        metadashboard = meta_meta['dashboard']
        dashgen = self.dashgen = metadashboard['generate']
        self.chart_base = dashgen['metrics']['static']
        self.chart_base['db'] = db_name  # install db_name in source to be copied
        self.query_preamble = (
            dashgen['query']['preamble_template'].format(table_name=table_name)
        )
        self.out_file_name = name
        self.dashboard_name = metadashboard['name']
        # Start creating metadata
        self.metadata = meta_meta['preamble']
        self.metadata['databases'] = {
            db_name: {
                'tables': {
                    table_name: {
                        'allow': False
        }}}}
        self.dashboard = copy.deepcopy(metadashboard['static'] )

    def make_for_columns(self, cols):
        self.generate_charts(cols)
        self.extend_layout()
        self.set_dashboard(self.dashboard_name)
        self.write_file()

    def generate_charts(self, cols):
        metrics = [
            col for col in cols if SPECIAL_SEP not in col and col.startswith('מדד')
        ]
        self.dashboard['charts']['main_metrics'] = self.make_metric_chart(
            metrics, self.dashgen['query']['main_metric_clause_template'],
        )

        for idx, metric in enumerate(metrics, start=1):
            sub_metrics = [
                col for col in cols
                if SPECIAL_SEP in col and (
                    col.startswith(metric) or
                    col.startswith(metric.replace('מדד', 'רכיבי'))
                )
            ]
            sub_metrics_chart = self.make_sub_metric_chart(
                sub_metrics, self.dashgen['query']['sub_metric_clause_template'],
            )
            sub_metrics_chart['title'] = metric
            self.dashboard['charts'][f'm-{idx:02d}'] = sub_metrics_chart

    def extend_layout(self):
        self.dashboard['layout'].extend(
            pairs(
                f'm-{j:02d}' for j in range(len(self.dashboard['charts']))
                if f'm-{j:02d}' in self.dashboard['charts']
            )
        )

    def set_dashboard(self, dashboard_name):
        dashboards = self.metadata['plugins'].setdefault('datasette-dashboards', {})
        dashboards[dashboard_name] = self.dashboard

    def write_file(self):
        with open(self.out_file_name, 'wt') as out:
            yaml.safe_dump(self.metadata, out, allow_unicode=True)


    def make_metric_chart(self, metrics, metric_clause_template):
        metrics_query = " UNION ALL ".join(
            metric_clause_template.format(field_name=metric)
            for metric in metrics
        )
        metrics_chart = copy.deepcopy(self.chart_base)
        metrics_chart['query'] = " ".join((self.query_preamble, metrics_query))
        return metrics_chart


    def make_sub_metric_chart(self, sub_metrics, sub_metric_clause_template):
        sub_metrics_query = " UNION ALL ".join(
            sub_metric_clause_template.format(
                # Note replaces to double the quotes -- this is very poor man's SQL quoting
                field_name=sub_metric.replace('"', '""'),
                sub_field_name=sub_metric.split(SPECIAL_SEP)[1].replace("'", "''")
            )
            for sub_metric in sub_metrics
        )
        sub_metrics_chart = copy.deepcopy(self.chart_base)
        sub_metrics_chart['query'] = " ".join((self.query_preamble, sub_metrics_query))
        return sub_metrics_chart


def read_meta_meta(prefix, name):
    source_name = prefix+name
    try:
        with open(source_name) as f:
            meta_meta = yaml.safe_load(f)
            return meta_meta
    except IOError:
        raise InvocationError(f"Cannot read file '{source_name}' to make '{name}'")


def pairs(seq, fill='.'):
    i = iter(seq)
    return itertools.zip_longest(i, i, fillvalue=fill)


if __name__ == "__main__":
    main()
