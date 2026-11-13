# SpecStream package for Automation Anywhere

SpecStream is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

This package adds two actions to Automation 360. A bot or an API task uses them like any other action.

| Action | What it does | Result | Price |
| --- | --- | --- | --- |
| **Search the web** | Answers a question from the live web in seconds with the Search API, the most accurate web search API in the world ([benchmarks](https://specstream.ai/benchmarks)). | A dictionary. The key `answer` holds the answer. The key `json` holds the complete reply, with every result and its source. | $5 per 1,000 searches of up to 10 results, or $1 per 1,000 on the fast tier |
| **Read a page** | Reads the text of a web page, PDF, Word or Excel file live with the Extract API. | The text as Markdown, in a string variable. | $0.80 per 1,000 pages. A page with no text is not charged. |

## Connect

1. Sign in at [specstream.ai](https://specstream.ai) and open **Agents & API**. Create a key. A new account has $10 of credit and needs no card.
2. In the Control Room, open **Manage > Credentials** and keep the key in a locker.
3. In each action, select that credential in the field **SpecStream API key**.

The actions call `https://api.specstream.ai` only. If your network uses an allowlist, add that address.

## Build

The build uses the Automation Anywhere Package SDK 2.13.0 and JDK 11.

```bash
./get-sdk.sh
./gradlew clean build shadowJar
```

`get-sdk.sh` downloads the SDK from Automation Anywhere and copies its two jars and its Gradle wrapper into this folder. The package is `build/libs/SpecStream-1.0.0.jar`.

## Install

In the Control Room, open **Manage > Packages**, select **Add package** and upload the jar. This needs the permission to upload packages.

## Test

`test/Driver.java` runs the client without the SDK. The tests in `tests/distribution/test_automation_anywhere_package.py` start it against a local server, so they use no key and no credit.

## Errors

When SpecStream refuses a call, the action stops with the message that the API gave, for example a key that is not valid or a balance that is empty. A call that gets no reply stops after 120 seconds.
