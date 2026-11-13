# Research agent for the Vultr Marketplace

A one-click app for a Vultr server: a research agent that runs on the buyer's own server. The buyer asks a question on a web page or on the command line, and the agent returns a written report from the live web with the page behind each cited sentence (`POST /v1/research` on the SpecStream API, with the buyer's own API key). Every report is kept on the server.

The app is free. A report costs $0.10 (quick), $0.30 (standard) or $1.00 (deep) on the buyer's SpecStream account, and a new account starts with $10 of credit.

## What is here

| Path | What it is |
| --- | --- |
| `app/research_agent.py` | The agent: the web page and the `ask` command. Python's standard library only. |
| `files/specstream-research.service` | The systemd service. The agent listens on `127.0.0.1:8080` as its own user. |
| `files/nginx.conf` | HTTPS on port 443 in front of the agent. Port 80 redirects. |
| `scripts/install.sh` | Build step: installs everything on a new Ubuntu 24.04 server. |
| `scripts/provision.sh` | First boot of each buyer's server: reads the application variables, writes the password and the certificate, starts the page. |
| `scripts/clean-image.sh` | Build step, last: cleans the build server before the snapshot. |
| `vendor-data/cloud-config.yaml` | The same build as one cloud-init document, written by `build.py`. |
| `listing/app.json` | The application profile: name, variables, ports, smallest plan. |
| `listing/readme.md` | The text of the app's page on the Marketplace. |
| `listing/instructions.md` | The text a buyer reads after deployment. It uses `{{ip}}`, `{{root_password}}` and `{{web_pass}}`. |

## Application variables

Create both in the vendor portal with these exact names. The first-boot script reads them from `http://169.254.169.254/v1/internal/app-<name>` with the header `METADATA-TOKEN: vultr`.

| Name | Type | Use |
| --- | --- | --- |
| `web_pass` | Password | The password of the research page. The user name is `research`. |
| `specstream_api_key` | User-supplied, optional | The buyer's SpecStream API key. When it is empty, the page asks for it. |

## Build from a snapshot

1. Deploy a server with Ubuntu 24.04 x64 on the smallest plan.
1. Copy this folder to the server and run `sudo bash scripts/install.sh`.
1. To test on the build server, run `sudo bash /var/lib/cloud/scripts/per-instance/provision.sh`. Read the password in `/root/research-password.txt` and open `https://<address>/`.
1. Run `sudo bash scripts/clean-image.sh`, power the server off and take the snapshot.
1. In the vendor portal, create a build from the snapshot.

## Build from vendor data

In the vendor portal, create a build with Ubuntu 24.04 x64 and paste `vendor-data/cloud-config.yaml` as the vendor data. It writes the same files and runs `install.sh` and `provision.sh` on the first boot. After a change to a file here, run `python3 build.py` to write it again.

## Test a build

Deploy the build from the Vultr console, with and without a value in `specstream_api_key`. Then check:

1. `https://<address>/` asks for a user name and a password, and accepts `research` with the value of `web_pass`.
1. Without a key, the page asks for one and saves it.
1. A quick report ends in about a minute and shows its sources.
1. `specstream-research "a question" --depth quick` prints the report as Markdown.

## Tests

`tests/distribution/test_vultr_research_agent.py` runs the agent against a scripted SpecStream API on the local machine, and runs `provision.sh` against a scripted metadata address. No test calls the SpecStream API.
