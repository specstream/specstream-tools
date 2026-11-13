import { strict as assert } from "node:assert";
import { test } from "node:test";
import { searchAnswer, searchQuery } from "../search";

// WebSearch passes the Search API's speed: fast at $1 per 1,000, the API's default when left empty.

test("a fast search sends speed=fast; left empty, no speed is sent", () => {
  assert.deepEqual(searchQuery("capital of Portugal", "fast"), { q: "capital of Portugal", speed: "fast" });
  assert.deepEqual(searchQuery("capital of Portugal"), { q: "capital of Portugal" });
  assert.deepEqual(searchQuery("capital of Portugal", ""), { q: "capital of Portugal" });
});

test("an unknown speed is refused", () => {
  assert.throws(() => searchQuery("q", "turbo"), /Speed/);
});

test("a fast search, which reads no answer, returns its top ranked result", () => {
  const fast = { answer: null, rows: [], sources: [{ url: "https://pt.example/lisbon", title: "Lisbon" }] };
  assert.equal(searchAnswer(fast), "Lisbon (https://pt.example/lisbon)");
  assert.equal(searchAnswer({ answer: { value: "Lisbon" }, sources: fast.sources }), "Lisbon");
  assert.equal(searchAnswer({}), "");
});
