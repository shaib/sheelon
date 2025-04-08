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
    column_defs = write_db_table(db, table_name, csv_table)
    meta_maker = MetadataWriter(
        name=metadata_name, prefix=meta_prefix,
        db_name=Path(db_name).stem, table_name=table_name
    )
    meta_maker.make_for_columns(column_defs)
    

def read_sheelon(reader):
    try:
        row1 = next(reader)
        row2 = next(reader)
        row3 = next(reader)
    except OSError:
        # TODO: Bug, csvfile_name not available in this function
        raise InvocationError(f"Cannot read header from '{csvfile_name}'")

    if not (len(row1) == len(row2) == len(row3)):
        raise InvocationError(f"header from '{csvfile_name}' is malformed")

    last_t1 = None
    header_row = []
    column_types = []
    for (t1, t2, question_type) in zip(row1, row2, row3):
        # No question type -> not a question we care about
        if not question_type:
            header_row.append(None)
            column_types.append(None)
            continue
        
        column_types.append(question_type)

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

        if t1:
            header_row.append(SPECIAL_SEP.join((t1, t2)))
        else:
            header_row.append(t2)
    return itertools.chain([header_row, column_types], reader)


def write_db_table(db, table_name, csv_table):
    table = db[table_name]
    column_names = next(csv_table)
    column_types = next(csv_table)
    id_column = "row_number"
    id_provider = itertools.count(3)

    row_dicts = []
    for row in csv_table:
        indices = {}
        row_number = next(id_provider)
        d = {id_column: row_number}
        for name,typ,val in zip(column_names, column_types, row):
            if name is None or typ is None:
                continue
            if val:
                try:
                    match typ:
                        case "עולה5":
                            val = int(val)
                            assert 1 <= val <= 5
                            add_to_index(indices, name, val)
                            val = five_to_three(val)
                        case "יורד5":
                            val = int(val)
                            assert 1 <= val <= 5
                            val = 6-val
                            add_to_index(indices, name, val)
                            val = five_to_three(val)
                        case "בחירה":
                            val = bool(val)
                        case "טקסט":
                            pass
                        case "סינון":
                            try:
                                val = int(val)
                            except ValueError:
                                pass  # leave as text
                        case _:
                            raise Exception(f"Invalid question type '{typ}'")
                except (ValueError, AssertionError):
                    raise Exception(f"Invalid value '{val}', Row {row_number}, at {name}")
            else:
                val = None
            d[name] = val
        add_indices_to_row(d, indices)
        row_dicts.append(d)

    table.insert_all(row_dicts, pk=id_column)
    return dict((n,t) for n,t in zip(column_names, column_types) if t is not None)


def add_to_index(indices, name, val):
    if SPECIAL_SEP in name:
        idx = name.split(SPECIAL_SEP, 1)[0]
        indices.setdefault(idx, []).append(val)


def add_indices_to_row(row, indices):
    for idx, values in indices.items():
        value = sum(values)/len(values)
        row[idx] = five_to_three(round(value))


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
        self.choice_chart_base = dashgen['option_set']['static']
        self.choice_chart_base['db'] = db_name  # maybe do something about repetition
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

        composites = order_keeping_unique(
            col.split(SPECIAL_SEP)[0] for col in cols if SPECIAL_SEP in col
        )
        
        metrics = [
            # Metrics are those titles where all sub-questions are 1-5
            comp for comp in composites
            if all(
                implies(col.startswith(comp + SPECIAL_SEP), typ in ('עולה5', 'יורד5'))
                for col, typ in cols.items()
            )
        ]
        self.dashboard['charts']['main_metrics'] = self.make_metric_chart(
            metrics, self.dashgen['query']['main_metric_clause_template'],
        )

        for idx, metric in enumerate(metrics, start=1):
            # TODO: fold more of this block into make_sub_metric_chart()
            sub_metrics = [
                col for col in cols
                if col.startswith(metric + SPECIAL_SEP)
            ]
            sub_metrics_chart = self.make_sub_metric_chart(
                sub_metrics, self.dashgen['query']['sub_metric_clause_template'],
            )
            sub_metrics_chart['title'] = metric
            self.dashboard['charts'][f'm-{idx:02d}'] = sub_metrics_chart

        multichoices = [
            comp for comp in composites
            if all(
                implies(
                    col.startswith(comp + SPECIAL_SEP),
                    typ == 'בחירה' or (typ == 'טקסט' and 'אחר' in col)
                )
                for col, typ in cols.items()
            )
        ]
        for idx, multi in enumerate(multichoices, start=1):
            multichoice_chart = self.make_choice_chart(cols, multi)
            self.dashboard['charts'][f'c-{idx:02d}'] = multichoice_chart
            
    def extend_layout(self):
        self.dashboard['layout'].extend(
            pairs(
                f'm-{j:02d}' for j in range(len(self.dashboard['charts']))
                if f'm-{j:02d}' in self.dashboard['charts']
            )
        )
        self.dashboard['layout'].extend(
            [f'c-{j:02d}', '.']
            for j in range(len(self.dashboard['charts']))
            if f'c-{j:02d}' in self.dashboard['charts']
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

    def make_choice_chart(self, cols, choice):
        options = [
            col for col,typ in cols.items()
            if col.startswith(choice + SPECIAL_SEP) and typ == 'בחירה'
        ]
        query = " UNION ALL ".join(
            self.dashgen['query']['option_set_clause_template'].format(
                field_title=option.split(SPECIAL_SEP, 1)[1],
                field_name=option,
            )
            for option in options
        )
        chart = copy.deepcopy(self.choice_chart_base)
        chart['query'] = " ".join((self.query_preamble, query))
        chart['title'] = title = choice + '\N{RLM}'
        chart['display']['encoding']['color']['title'] = title
        chart['display']['encoding']['x']['title'] = title
        return chart

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


def order_keeping_unique(iterable):
    return list(dict.fromkeys(iterable))


def implies(p, q):
    return (not p) or q


def five_to_three(val):
    """Take an int in range 1-5, and turn 1,2=>1, 3=>2, 4,5=>3"""
    d = {1:1, 2:1, 3:2, 4:3, 5:3}
    return d[val]


if __name__ == "__main__":
    main()
