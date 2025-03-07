# Datasette-driven questionnaire reporting

This project was started from the Datasette example for Glitch projects,
but we're not going to use Glitch and we're moving further away.

Usage here:

We read the CSV file, and from it (and our meta-metadata.yml) generate a
database and a metadata file.
```console
$ python read_data.py <csv-file>
```
Then we use these generated files to present things

```console
$ datasette sheelon.db -m metadata.yml
```

This will work if you [set up a user](https://datasette.io/plugins/datasette-auth-passwords) properly.
But for development, you can use

```console
$ datasette --root sheelon.db -m metadata.yml
```
to log in as root with a token instead.

<hr/>

Text below this is the original Readme, and it includes references
to the sources where this started -- of historical interest only.

(we're still including Glitch's `install.sh` and `start.sh` for reference)

<hr/>

# Datasette for CSV files

Drag and drop any CSV files you like to this project root and they will be converted into a SQLite database and loaded into a Datasette instance.

Hit this Remix button to get your own copy of this project:

[![Remix on Glitch](https://cdn.glitch.com/2703baf2-b643-4da7-ab91-7ee2a2d00b5b%2Fremix-button.svg)](https://glitch.com/edit/#!/remix/datasette-csvs)

You can uncomment lines in `requirements.txt` to install extra plugins.

See [Running Datasette on Glitch](https://simonwillison.net/2019/Apr/23/datasette-glitch/) for more about this project.

## Configuring full-text search

Datasette supports SQLite full-text search. You can configure it for a table using the `sqlite-utils` command-line tool.

In the Glitch editor select Tools -> Full Page Console, then run the following:

    $ cd .data
    $ sqlite-utils tables data.db --table --columns
    table    columns
    -------  ------------------------------------
    example  ['headline', 'body', 'url', 'extra']

This shows you the tables and columns in your database.

If you want to make the `example` table searchable by `headline` and `body`, run the following command:

    $ sqlite-utils enable-fts data.db example headline body --fts4

Your Datasette instance will now display a search box that can be used to search the text in those columns.
