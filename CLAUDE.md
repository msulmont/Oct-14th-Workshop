# Research system rules

This project is a small research database. Claude does the reading. A plain
script, verify.py, decides which facts count. Follow these rules every time.

## How the project is laid out

- `questions.md`: the topic and the questions this database is meant to answer.
- `sources/`: original files exactly as fetched (PDFs, saved pages). Never edit,
  rename or delete anything in here.
- `captures/`: the text extracted from each original. Never edit these by hand.
- `sources.json`: one entry per source, with its title, address, fingerprint
  (SHA-256) of the original and of its text, and the tool that extracted its text. Only `verify.py add` writes entries.
- `claims.json`: the facts. This is the only data file Claude writes.
- `verify.py`: the checker. Plain Python, no AI.
- `REPORT.md`: written by verify.py. Never edit by hand.

## Adding a source

The user gives you an address (a public web page or PDF). Use verify.py for
every step so the fingerprint is taken by the script, not by you.

1. Run `python3 verify.py fetch <address> --title "<title>"`.
2. If it says no PDF extractor is installed, run `pip install pypdf` and run
   `python3 verify.py add sources/<file> --title "..." --url "..."` on the file
   it saved.
3. If the download is blocked, tell the user plainly. In a claude.ai/code
   session the fix is setting the environment's network access to Full; or the
   user can copy the page text into the chat, and you save it exactly as given
   with `python3 verify.py paste <name> --title "..." --url "..."`.
   Never rewrite, summarize or clean up pasted text before saving it.
4. Read the new file in `captures/` and tell the user if any pages, tables or
   footnotes came through badly. Do not fix the text by hand.

## Writing claims

Each claim in `claims.json` looks like this:

```json
{
  "claim_id": "c1",
  "source_id": "<id from sources.json>",
  "subject": "what the number measures, in plain words",
  "value": "2.6",
  "unit": "percent",
  "period": "August 2026",
  "quote": "the exact sentence from the capture that contains the number"
}
```

- Copy the quote character for character from the file in `captures/`. Never
  reword, shorten the middle of, or fix a quote.
- One number per claim. The value must appear in the quote.
- If a number only appears in a table, the quote is the table row exactly as it
  appears in the capture. If you can't quote it exactly, leave it out and say so.
- Give claims new IDs (c1, c2, ...). Never reuse or renumber an existing ID.
- After changing claims, run `python3 verify.py` and explain every held claim.

## What "verified" means

Verified means the source hasn't changed, the quote is really in it, and the
number is really in the quote. It does not mean the claim is the right fact.
When you summarize results, say which claims a person should still check, for
example because the sentence mentions more than one period or more than one number.

## Tests

If asked to run a tamper test, change one word in a file in `sources/` or
`captures/`, run the checker, show the report, then put the file back exactly as
it was and run the checker again.

## Growing the system

When adding features (charts, pages, new checks), build them on top of
`claims.json` and `REPORT.md`, show only verified claims unless asked otherwise,
and keep verify.py free of any AI calls.
