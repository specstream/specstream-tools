## SpecStream: a research agent on your own server

Ask a question in plain words and get a written report from the live web. Each cited sentence links to the page it came from, with the time that page was read. The agent runs on your own Vultr server, and every report is kept on that server.

## What the app installs

* A web page on your server, over HTTPS and behind a password that Vultr makes for each server.
* A command, `specstream-research "your question"`, that prints one report as Markdown. Use it in a cron job or a script.
* A list of the reports written on this server, each with a Markdown download.

The agent is one Python file that uses the standard library only, behind nginx. The source is public: https://github.com/specstream/specstream-tools/tree/main/integrations/vultr

## How it works

1. You type a question and choose a depth: quick, standard or deep.
1. The agent sends the question to the SpecStream API with your own API key.
1. SpecStream searches the web, reads the pages and writes the report.
1. The agent saves the report on your server and shows it with its sources.

## Price

The app is free. You pay Vultr for the server, and SpecStream for each delivered report:

| Depth | Price of a report | Time |
| --- | --- | --- |
| quick | $0.10 | about a minute |
| standard | $0.30 | about four minutes |
| deep | $1.00 | about five minutes |

A new SpecStream account starts with $10 of credit. A stopped or failed report is not charged.

## What you need

* A SpecStream API key. Create an account at https://specstream.ai/workspace?utm_source=vultr and copy a key from the workspace.
* The smallest Vultr plan is enough: the searching, reading and writing run at SpecStream.

## What leaves your server

The agent sends your questions to `api.specstream.ai` and to no other address. Your API key is kept in a file that only the agent reads.
