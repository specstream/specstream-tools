# SpecStream for lemlist

<!-- The opening and setup words wait for the writer agent; the facts below are checked against the code. -->

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

This folder holds an enrich step for [lemlist](https://www.lemlist.com). It reads the leads of one lemlist campaign, asks SpecStream Deep Search for the facts you name in plain words, and writes each fact it finds back on its lead as a lemlist custom variable. The page that prints the fact goes in a second variable, `<variable>Source`. Your sequence then uses `{{companyHeadcount}}` like any other variable.

- One file, Python 3.10 or later, standard library only.
- Deep Search is priced per delivered row. The step starts no work above the maximum you give: when the quote is higher, it stops and prints the quote.
- It never writes lemlist's own lead fields (`email`, `firstName`, `companyName` and the others), and a variable that already holds a value keeps it unless you pass `--overwrite`.
- What leaves lemlist: each lead's id, name, company name, company domain and LinkedIn URL. The lead's email address stays in lemlist.

## Set it up

1. In SpecStream, open **Agents & API** and create an API key. [Sign up](https://specstream.ai) if you don't have an account.
2. In lemlist, open **Settings > Integrations** and generate an API key.
3. Download the step:

   ```bash
   curl -fsSL -o specstream_lemlist.py https://raw.githubusercontent.com/specstream/specstream-tools/main/integrations/lemlist/specstream_lemlist.py
   ```

4. Run it on a campaign. Each `--fact` is the fact in words, `=`, and the lemlist variable to fill:

   ```bash
   export SPECSTREAM_API_KEY=...
   export LEMLIST_API_KEY=...
   python3 specstream_lemlist.py --campaign cam_XXXX \
     --fact "Company headcount=companyHeadcount" \
     --fact "Latest funding round=lastFundingRound" \
     --max-cents 500
   ```

The step prints the started find, waits for it, then prints what it wrote on each lead. Running it again with the same campaign and facts does not start the work a second time. To write the results of a find already started, pass `--find <find id>`.

## Test

```bash
python3 -m pytest test_specstream_lemlist.py
```

The tests script both services; they call neither.
