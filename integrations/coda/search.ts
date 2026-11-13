// The WebSearch formula's request and answer, apart from the Coda SDK so they can be tested.

// The Search API's speeds: "fast" is $1 per 1,000 searches, "default" $5 per 1,000.
export const SPEEDS = ["fast", "default"];

// The query string of one search. No speed is sent when none is chosen: the API's default runs.
export function searchQuery(question: string, speed?: string): { q: string; speed?: string } {
  const choice = String(speed || "").trim().toLowerCase();
  if (choice && !SPEEDS.includes(choice)) throw new Error('Speed must be "fast" or "default".');
  return choice ? { q: question, speed: choice } : { q: question };
}

// The answer, else the top matching row. A fast search reads no answer from the pages,
// so its top ranked result is its answer: the page's title and address.
export function searchAnswer(data: any): string {
  if (data?.answer?.value != null && data.answer.value !== "") return String(data.answer.value);
  const rows = data?.rows || [];
  if (rows.length) return String(rows[0].name || "");
  const top = (data?.sources || [])[0];
  if (!top?.url) return "";
  return top.title ? `${top.title} (${top.url})` : String(top.url);
}
