import * as vscode from "vscode";
import { Backend, Match, Quote, TERMINAL, mcpAvailable, viaKey, viaMcp } from "./backend";
import { KEY_SECRET } from "./mcp";

const PENDING = "specstream.pendingQuotes";
const LAST_FIND = "specstream.lastFind";
const SHOWN_ROWS = 50;
const POLL_MS = 3000;
const WAIT_MS = 10 * 60 * 1000;

interface Pending {
  quote: Quote;
  request: string;
  at: number;
}

export function registerParticipant(context: vscode.ExtensionContext): vscode.Disposable {
  const store = {
    all: () => context.globalState.get<Record<string, Pending>>(PENDING, {}),
    async put(p: Pending) {
      const all = this.all();
      all[p.quote.quoteId] = p;
      const newest = Object.entries(all).sort((a, b) => b[1].at - a[1].at).slice(0, 10);
      await context.globalState.update(PENDING, Object.fromEntries(newest));
    },
    async drop(id: string) {
      const all = this.all();
      delete all[id];
      await context.globalState.update(PENDING, all);
    },
    latest: () => Object.values(store.all()).sort((a, b) => b.at - a.at)[0],
  };

  async function backendFor(request: vscode.ChatRequest, token: vscode.CancellationToken): Promise<Backend | undefined> {
    const key = await context.secrets.get(KEY_SECRET);
    if (key) return viaKey(key);
    if (mcpAvailable()) return viaMcp(request.toolInvocationToken, token);
    return undefined;
  }

  const handler: vscode.ChatRequestHandler = async (request, _ctx, stream, token) => {
    try {
      if (request.command === "approve") return await approve(request, stream, token);
      return await find(request, stream, token);
    } catch (err) {
      if (token.isCancellationRequested) return {};
      stream.markdown(`SpecStream stopped: ${message(err)}\n\nNothing was charged for anything that did not finish.`);
      return { errorDetails: { message: message(err) } };
    }
  };

  async function find(request: vscode.ChatRequest, stream: vscode.ChatResponseStream, token: vscode.CancellationToken) {
    const text = request.prompt.trim();
    if (!text) {
      stream.markdown(
        "Describe the list you need and I will show the price first. For example:\n\n" +
          "- `@specstream /find Companies that filed a Form D this week to raise $5M or more, with state and industry`\n" +
          "- `@specstream /find MCP servers on GitHub with more than 500 stars, pushed this month`",
      );
      return {};
    }
    const backend = await backendFor(request, token);
    if (!backend) {
      stream.markdown("Connect SpecStream first. Sign in once and VS Code keeps you signed in.");
      stream.button({ command: "specstream.connect", title: "Connect SpecStream" });
      return {};
    }

    stream.progress("Reading your request");
    const reading = await backend.compile(text);
    if (!reading.ok || !reading.astHash) {
      stream.markdown(
        "I could not turn that into a list yet. Say what each row is and how to tell it belongs, for example: " +
          "*companies that filed a Form D this week to raise $5M or more*.",
      );
      return {};
    }

    const units = vscode.workspace.getConfiguration("specstream").get<number>("maxMatches", 25);
    stream.progress("Getting the price");
    const quote = await backend.quote(reading.astHash, units);
    await store.put({ quote, request: text, at: Date.now() });

    const price = money(quote.maximumCents, quote.currency);
    stream.markdown(`**${reading.sentence ?? text}**\n\n`);
    stream.markdown(
      `Up to ${quote.units} matches for **at most ${price}**` +
        (quote.unitCents !== null ? ` (${money(quote.unitCents, quote.currency)} a match)` : "") +
        `. You pay for each result delivered, and a search that finds nothing costs nothing.\n\n` +
        `Nothing has run. Approve this price to start.\n`,
    );
    stream.button({ command: "specstream.approve", title: `Run for up to ${price}`, arguments: [quote.quoteId] });
    return { metadata: { command: "find", quoteId: quote.quoteId } };
  }

  async function approve(request: vscode.ChatRequest, stream: vscode.ChatResponseStream, token: vscode.CancellationToken) {
    const id = request.prompt.trim();
    const pending = id ? store.all()[id] : store.latest();
    if (!pending) {
      stream.markdown("There is no price waiting for your approval. Start with `@specstream /find` and the list you need.");
      return {};
    }
    const { quote } = pending;
    if (quote.expiresAt && Date.parse(quote.expiresAt) < Date.now()) {
      await store.drop(quote.quoteId);
      stream.markdown("That price has expired. Ask again with `@specstream /find` and you will see a fresh one.");
      return {};
    }
    const backend = await backendFor(request, token);
    if (!backend) {
      stream.markdown("Connect SpecStream first.");
      stream.button({ command: "specstream.connect", title: "Connect SpecStream" });
      return {};
    }

    const price = money(quote.maximumCents, quote.currency);
    stream.markdown(`Running **${pending.request}** for up to **${price}**, the price you approved.\n\n`);
    const findId = await backend.authorize(quote);
    await store.drop(quote.quoteId);
    await context.globalState.update(LAST_FIND, findId);

    const started = Date.now();
    let state = await backend.state(findId);
    while (!TERMINAL.has(state.status)) {
      if (token.isCancellationRequested) {
        stream.markdown("Stopped waiting. The list keeps running and will be in your workspace.");
        openButton(stream, findId);
        return {};
      }
      if (Date.now() - started > WAIT_MS) {
        stream.markdown("This one is taking longer than a chat should wait. It keeps running and will be in your workspace.");
        openButton(stream, findId);
        return {};
      }
      stream.progress(`Reading the live web, ${state.accepted} matches so far`);
      await sleep(POLL_MS, token);
      state = await backend.state(findId);
    }

    if (state.status === "failed" || state.status === "expired") {
      stream.markdown("That list did not finish, and you were not charged for what did not arrive.");
      return {};
    }

    const { matches, total } = await backend.matches(findId, SHOWN_ROWS);
    if (matches.length === 0) {
      stream.markdown("No matches this time, so nothing was charged.");
      return {};
    }
    stream.markdown(`**${total} matches.**\n\n`);
    stream.markdown(table(matches));
    if (total > matches.length) stream.markdown(`\n\n${total - matches.length} more in the workspace.`);
    if (state.chargedCents !== null) stream.markdown(`\n\nCharged ${money(state.chargedCents, state.currency)}.`);
    stream.markdown("\n\n");
    openButton(stream, findId);
    return { metadata: { command: "approve", findId } };
  }

  const participant = vscode.chat.createChatParticipant("specstream.chat", handler);
  participant.iconPath = vscode.Uri.joinPath(context.extensionUri, "media", "icon.png");
  participant.followupProvider = {
    provideFollowups(result) {
      const meta = result.metadata as { command?: string } | undefined;
      if (meta?.command === "approve") {
        return [{ label: "Ask for another list", prompt: "", command: "find" } satisfies vscode.ChatFollowup];
      }
      return [];
    },
  };

  return vscode.Disposable.from(
    participant,
    vscode.commands.registerCommand("specstream.approve", (quoteId?: string) => {
      // The click on the price button is the approval. It re-enters chat so results stream into the conversation.
      const query = `@specstream /approve ${quoteId ?? ""}`.trim();
      return vscode.commands.executeCommand("workbench.action.chat.open", { query, isPartialQuery: false });
    }),
    vscode.commands.registerCommand("specstream.askForList", () =>
      vscode.commands.executeCommand("workbench.action.chat.open", { query: "@specstream /find ", isPartialQuery: true }),
    ),
    vscode.commands.registerCommand("specstream.openList", (findId?: string) => {
      const id = findId ?? context.globalState.get<string>(LAST_FIND);
      const base = (vscode.workspace.getConfiguration("specstream").get<string>("workspaceUrl") || "https://specstream.ai").replace(/\/+$/, "");
      return vscode.env.openExternal(vscode.Uri.parse(id ? `${base}/workspace/collections/${encodeURIComponent(id)}` : `${base}/workspace`));
    }),
  );
}

function openButton(stream: vscode.ChatResponseStream, findId: string) {
  stream.button({ command: "specstream.openList", title: "Open in workspace", arguments: [findId] });
}

function money(cents: number, currency: string): string {
  const symbol = currency === "EUR" ? "€" : "$";
  const amount = cents / 100;
  return `${symbol}${cents % 100 === 0 ? amount.toFixed(0) : amount.toFixed(2)}`;
}

function cell(text: string): string {
  return text.replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " ").trim();
}

function table(matches: Match[]): string {
  const labels = matches[0].cells.map((c) => c.label).slice(0, 5);
  const header = [...labels, "Source"];
  const lines = [`| ${header.map(cell).join(" | ")} |`, `| ${header.map(() => "---").join(" | ")} |`];
  for (const m of matches) {
    const values = labels.map((label) => cell(m.cells.find((c) => c.label === label)?.text ?? ""));
    let source = "";
    if (m.sourceUrl) {
      try {
        source = `[${new URL(m.sourceUrl).hostname.replace(/^www\./, "")}](${m.sourceUrl})`;
      } catch {
        source = "";
      }
    }
    lines.push(`| ${[...values, source].join(" | ")} |`);
  }
  return lines.join("\n");
}

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function sleep(ms: number, token: vscode.CancellationToken): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(done, ms);
    const sub = token.onCancellationRequested(done);
    function done() {
      clearTimeout(timer);
      sub.dispose();
      resolve();
    }
  });
}
