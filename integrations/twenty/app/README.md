# SpecStream for Twenty

Fill in a company record from the live web. You say which facts you want in plain words, SpecStream finds them, and each fact is written to the company with the page it was read from.

## What it does

- **Research a company on request.** Use the workflow action "Research company with SpecStream", or ask Twenty's AI to research a company. The app is also an AI tool.
- **Writes to the company record.** Four fields are added to Company: Web research, Web research status, Web research note and SpecStream list ID. No other field is changed, so nothing you typed is overwritten.
- **A price limit you set.** SpecStream quotes the most a company can cost before it starts. Research above your maximum does not start and nothing is bought.
- **New companies, if you want.** Turn on "Research every new company" and each company added to the workspace is researched without a click. It is off by default.

## Set it up

1. Install the app in your Twenty workspace.
2. Create an API key at https://specstream.ai/workspace, under Agents & API. New accounts start with $10 of credit.
3. In the app settings, paste the key in **SpecStream API key**.
4. Optional: change **Facts to find** (default: what the company does, number of employees, headquarters city, year founded, LinkedIn page) and **Maximum price per company** (default: $1).

## Example

In a workflow, add a manual trigger on Company and the action **Research company with SpecStream** with the record's ID. Run it on a company that has a name or a website. The status shows Running, and a few minutes later it shows Done and **Web research** reads:

```
Employees: 120 (https://acme-robotics.com/about)
Headquarters: Lyon, France (https://acme-robotics.com/contact)
Checked by SpecStream on 2026-11-12
```

When nothing is found or something needs you (no credit, a refused key, a price above your maximum), the status says so and **Web research note** says what to do.

## Price

The app is free. The research runs on your SpecStream account: each company delivered is charged 5¢, 15¢ or $1, depending on how much the facts you ask for need. See https://specstream.ai/pricing.

## What leaves your workspace

For each company researched, the app sends the company's name, its website and your list of facts to `api.specstream.ai`, with your API key. Nothing else is sent: no people, no notes, no deals. The result is kept as a list in your SpecStream account, where you can open it. SpecStream's privacy policy: https://specstream.ai/privacy.

The app's role reads and updates companies only.

## Support

support@specstream.ai
