# TypeScript SDK example

Reads a request, shows the price and the maximum, waits for you to type `yes`, runs it, and prints the first results. Node 22.6 or newer.

```sh
npm install
export SPECSTREAM_API_KEY="ss_live_..."
npm start -- "Open-source vector databases on GitHub with more than 5,000 stars, with their license."
```

The key comes from **Agents & API** in the SpecStream workspace. Nothing is spent unless you approve. The request key is built from the quote, so a second run on the same quote returns the same work.
