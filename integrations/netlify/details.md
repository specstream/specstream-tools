<!-- Draft words: wait for the writer agent before the extension is made public. -->

SpecStream gives the functions of your Netlify sites web search and page reading over one API. This extension connects a SpecStream API key to your team once, so every site reads it from the same environment variable.

## What the extension does

- You paste a SpecStream API key on this page. The extension checks it with SpecStream and saves it as the secret team environment variable `SPECSTREAM_API_KEY`, for builds, functions and runtime.
- Each build log shows one line that says the variable is set. The line never contains the key.
- **Disconnect** removes the variable.

The extension does not add functions or pages to your sites, and it cannot fail a build.

## Set up

1. Install the extension on your team.
2. Create an API key under Agents & API in your [SpecStream workspace](https://specstream.ai/workspace?utm_source=clouds-31). Give it the `finds:spend` scope and a spending limit. New accounts start with $10 of credit.
3. Paste the key under **Configuration** on this page and select **Connect**.
4. Deploy a site again so its functions get the variable.

## Use it in a function

```ts
// netlify/functions/search.mts
export default async (request: Request) => {
  const query = new URL(request.url).searchParams.get("q") ?? "";
  const answer = await fetch(
    `https://api.specstream.ai/v1/web-search?q=${encodeURIComponent(query)}`,
    { headers: { Authorization: `Bearer ${Netlify.env.get("SPECSTREAM_API_KEY")}` } },
  );
  return new Response(answer.body, { status: answer.status, headers: { "content-type": "application/json" } });
};
```

A function on a public address spends your credit for anyone who calls it. Put your own sign-in check in front of it, and set a spending limit on the key.

## Price

- Search API, `GET /v1/web-search`: $5 per 1,000 searches of up to 10 results, and $1 per 1,000 with `speed=fast`.
- Extract API, `POST /v1/extract`: $0.80 per 1,000 pages. A page with no text is not charged.

The extension is free. Netlify does not bill for SpecStream: use is charged to your SpecStream account.

## Environment variables

| Variable | Set by | Used for |
| --- | --- | --- |
| `SPECSTREAM_API_KEY` | this extension, at team level, as a secret | the `Authorization: Bearer` header of calls to `api.specstream.ai` |

## What leaves Netlify

When you select **Connect**, the extension sends the key to `https://api.specstream.ai/v1/me` once, to check it. That call runs no search and costs nothing. The extension keeps the last four characters of the key and the account's email address in its team configuration, to show which key is connected. It sends nothing else.

Documentation: https://specstream.ai/docs/search-api. Help: support@specstream.ai.
