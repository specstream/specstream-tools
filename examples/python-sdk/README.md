# Python SDK example

Reads a request, shows the price and the maximum, waits for you to type `yes`, runs it, and prints the first results.

```sh
pip install specstream-client
export SPECSTREAM_API_KEY="ss_live_..."
python quickstart.py "Open-source vector databases on GitHub with more than 5,000 stars, with their license."
```

The key comes from **Agents & API** in the SpecStream workspace. Nothing is spent unless you approve. The request key is built from the quote, so a second run on the same quote returns the same work.

## A real browser

`browser.py` opens a browser on SpecStream, reads one page as Markdown and closes the browser.

```sh
python browser.py https://example.com
```

A session costs $0.10 an hour, charged by the second, plus $1 per 1,000 steps. This script runs 2 steps and a few seconds, so one run costs less than 1 cent.
