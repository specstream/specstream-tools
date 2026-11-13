# SpecStream for DonSeTch

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

This folder holds a search plugin for [DonSeTch](https://github.com/dondai44423/donsetch). DonSeTch sends each search to SpecStream through the Search API (`GET /v1/web-search`) and puts the results in its chain with its other providers.

- One file, Python 3.9 or later, standard library only.
- Fast tier by default: $1 per 1,000 searches of up to 10 results.
- New accounts start with $10 of credit, no card.

## Set it up

1. In SpecStream, open **Agents & API** and create an API key. [Sign up](https://specstream.ai) if you don't have an account.
2. Download the plugin:

   ```bash
   curl -fsSL -o "$HOME/specstream_donsetch.py" https://raw.githubusercontent.com/specstream/specstream-tools/main/integrations/donsetch/specstream_donsetch.py
   ```

3. Put the key in a file that only you can read:

   ```bash
   mkdir -p "$HOME/.config/specstream"
   (umask 077 && printf '%s' 'YOUR_API_KEY' > "$HOME/.config/specstream/api-key")
   ```

4. Register the plugin. `--test` runs one search:

   ```bash
   donsetch keys add plugin specstream --cmd "python3 $HOME/specstream_donsetch.py --key-file $HOME/.config/specstream/api-key" --test
   ```

`donsetch keys list` shows the plugin. The key stays out of DonSeTch's config: the plugin reads it from the file, or from `SPECSTREAM_API_KEY` in DonSeTch's environment.

## Options

| Option | What it does |
|---|---|
| `--key-file PATH` | Reads the API key from this file. `SPECSTREAM_API_KEY_FILE` does the same. |
| `--speed fast` | The fast tier, $1 per 1,000 searches. The default. |
| `--speed default` | The standard Search API, $5 per 1,000 searches. `SPECSTREAM_SPEED` does the same. |

A search with DonSeTch's `news` intent asks SpecStream for news results. The plugin returns up to 10 results a search.

## Errors

The plugin answers in DonSeTch's error format. A key that is missing or refused is reported as `invalid_key`. An empty balance is reported as `credit_depleted`. A rate limit is reported as `rate_limited`. In each case DonSeTch parks the plugin and uses its next provider.

## License

MIT
