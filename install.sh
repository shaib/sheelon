pip3 install -U --no-cache-dir -r requirements.txt --user && \
  mkdir -p .data && \
  rm .data/data.db || true && \
  for f in *.csv
    do
      # Add --encoding=latin-1 to the following if your CSVs use a different encoding:
      sqlite-utils insert .data/data.db ${f%.*} $f --csv
    done
