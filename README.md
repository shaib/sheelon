# Datasette-driven questionnaire reporting

This is written in Python (naturally, with Datasette), we're using
[`uv`](https://docs.astral.sh/uv/) to manage the technicalities.

Usage here:

We read the CSV file, and from it (and our meta-metadata.yml) generate a
database and a metadata file.
```console
$ uv run read_data.py <csv-file>
```
Then we use these generated files to present things

```console
$ uv run datasette sheelon.db -m metadata.yml
```

This will work if you [set up a user](https://datasette.io/plugins/datasette-auth-passwords) properly.
But for development, you can use

```console
$ uv run datasette --root sheelon.db -m metadata.yml
```
to log in as root with a token instead.

<hr/>

This project was started from the Datasette example for Glitch projects,
but we're not going to use Glitch and we're moving further away.

(we're still including Glitch's `install.sh` and `start.sh` for reference)

For more on where we started, you can start a remix of your own from
the original project. Hit this Remix button to get your own copy:

[![Remix on Glitch](https://cdn.glitch.com/2703baf2-b643-4da7-ab91-7ee2a2d00b5b%2Fremix-button.svg)](https://glitch.com/edit/#!/remix/datasette-csvs)

<hr/>
