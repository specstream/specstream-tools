import { generateText, stepCountIs } from "ai";
import { specstreamTools, SpecStreamClient } from "../src/index.js";

export async function readme() {
  const { text } = await generateText({
    model: "openai/gpt-5-mini",
    tools: specstreamTools({ maxPriceUsd: 5 }),
    stopWhen: stepCountIs(5),
    prompt: "x",
  });
  const client = new SpecStreamClient({ apiKey: process.env.SPECSTREAM_API_KEY });
  const list = await client.findList("Breweries", { maxResults: 25, maxPriceUsd: 3 });
  if ("rows" in list) console.log(list.row_count, list.rows[0].source_url);
  else console.log(list.message);
  const monitor = await new SpecStreamClient().monitorList("fnd_gk5y3d0r97bvyz0t08zzh75kr6", {
    every: "week",
    maxPricePerRunUsd: 2,
    maxPricePerMonthUsd: 8,
  });
  if (monitor.status === "saved") console.log(monitor.monitor_id, monitor.next_run_at);
  else console.log(monitor.message);
  const tools = specstreamTools({ maxPriceUsd: 5, monitorMaxPricePerRunUsd: 2, monitorMaxPricePerMonthUsd: 20 });
  await generateText({ model: "openai/gpt-5-mini", tools, prompt: "x" });
  return tools.specstream_monitor_list && text;
}
