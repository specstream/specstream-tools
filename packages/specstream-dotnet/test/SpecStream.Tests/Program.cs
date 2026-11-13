using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using SpecStream;

namespace SpecStream.Tests
{
    /// <summary>A scripted handler: records each request and answers from a list. Nothing leaves the process.</summary>
    internal sealed class FakeHandler : HttpMessageHandler
    {
        private readonly Queue<(int Status, string Body, string? RetryAfter)> _replies;

        public FakeHandler(params (int Status, object Body, string? RetryAfter)[] replies)
        {
            _replies = new Queue<(int, string, string?)>(replies.Select(r => (r.Status, r.Body as string ?? JsonSerializer.Serialize(r.Body), r.RetryAfter)));
        }

        public List<(string Method, string Uri, Dictionary<string, string> Headers, JsonElement? Body)> Calls { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            JsonElement? body = null;
            if (request.Content != null)
            {
                using var doc = JsonDocument.Parse(await request.Content.ReadAsStringAsync(cancellationToken));
                body = doc.RootElement.Clone();
            }
            var headers = request.Headers.ToDictionary(h => h.Key, h => string.Join(",", h.Value));
            Calls.Add((request.Method.Method, request.RequestUri!.AbsoluteUri, headers, body));
            if (_replies.Count == 0)
            {
                throw new InvalidOperationException("no scripted reply left");
            }
            var (status, text, retryAfter) = _replies.Dequeue();
            var response = new HttpResponseMessage((HttpStatusCode)status) { Content = new StringContent(text) };
            if (retryAfter != null)
            {
                response.Headers.TryAddWithoutValidation("Retry-After", retryAfter);
            }
            return response;
        }
    }

    internal static class Program
    {
        private static readonly string QuoteHash = new string('a', 64);
        private static int _passed;
        private static readonly List<string> Failures = new();

        private static (int, object, string?) Ok(object data) => (200, new { data }, null);

        private static SpecStreamClient Client(FakeHandler handler, string? baseUrl = null, List<TimeSpan>? waits = null)
            => new SpecStreamClient("ss_test_key", baseUrl, handler: handler, delay: (wait, _) => { waits?.Add(wait); return Task.CompletedTask; });

        private static void Equal<T>(T expected, T actual, string what)
        {
            if (!EqualityComparer<T>.Default.Equals(expected, actual))
            {
                throw new Exception(what + ": expected <" + expected + "> but was <" + actual + ">");
            }
        }

        private static void True(bool condition, string what)
        {
            if (!condition)
            {
                throw new Exception(what);
            }
        }

        private static async Task<TException> ThrowsAsync<TException>(Func<Task> action) where TException : Exception
        {
            try
            {
                await action();
            }
            catch (TException ex)
            {
                return ex;
            }
            catch (Exception ex)
            {
                throw new Exception("expected " + typeof(TException).Name + " but got " + ex.GetType().Name + ": " + ex.Message);
            }
            throw new Exception("expected " + typeof(TException).Name + " but nothing was thrown");
        }

        private static async Task Run(string name, Func<Task> test)
        {
            try
            {
                await test();
                _passed++;
                Console.WriteLine("ok   " + name);
            }
            catch (Exception ex)
            {
                Failures.Add(name);
                Console.WriteLine("FAIL " + name + ": " + ex.Message);
            }
        }

        private static object MonitorBody(object? perRun = null, object? key = null, object? cadence = null) => new Dictionary<string, object?>
        {
            ["idempotency_key"] = key ?? "monitor-key-0001",
            ["scope"] = new { ast_hash = "h1", operation = "find", requested_units = 25 },
            ["cadence_seconds"] = cadence ?? 86400,
            ["first_due_at"] = "2026-12-01T08:00:00Z",
            ["per_run_cents"] = perRun ?? 500,
            ["period_cents"] = 5000,
            ["valid_until"] = "2027-06-01T00:00:00Z",
        };

        public static async Task<int> Main()
        {
            await Run("requires a key", async () =>
            {
                await ThrowsAsync<SpecStreamException>(() => Task.FromResult(new SpecStreamClient("  ")));
                await ThrowsAsync<SpecStreamException>(() => Task.FromResult(new SpecStreamClient(null!)));
            });

            await Run("ToString hides the key", () =>
            {
                using var c = new SpecStreamClient("ss_secret_value");
                True(!c.ToString().Contains("ss_secret_value"), "key shown");
                return Task.CompletedTask;
            });

            await Run("compile posts the request with bearer key and user agent", async () =>
            {
                var h = new FakeHandler(Ok(new { ast_hash = "h1", ast = new { } }));
                var data = await Client(h).CompileAsync("Open-source vector databases", "en-GB");
                Equal("h1", data.GetProperty("ast_hash").GetString(), "data");
                var call = h.Calls.Single();
                Equal("POST", call.Method, "method");
                Equal("https://api.specstream.ai/v1/parse", call.Uri, "uri");
                Equal("Open-source vector databases", call.Body!.Value.GetProperty("q").GetString(), "q");
                Equal("en-GB", call.Body!.Value.GetProperty("locale").GetString(), "locale");
                Equal("Bearer ss_test_key", call.Headers["Authorization"], "auth");
                Equal("specstream-dotnet/" + SpecStreamClient.Version, call.Headers["User-Agent"], "ua");
            });

            await Run("base url override keeps its path and ids are escaped", async () =>
            {
                var h = new FakeHandler(Ok(new { }));
                await Client(h, "http://127.0.0.1:9/api/").GetFindAsync("f 1/x");
                Equal("http://127.0.0.1:9/api/v1/finds/f%201%2Fx", h.Calls.Single().Uri, "uri");
            });

            await Run("quote, authorize, then every row page by page", async () =>
            {
                var h = new FakeHandler(
                    Ok(new { quote_id = "q1", quote_hash = QuoteHash, maximum_cents = 125 }),
                    Ok(new { find_id = "f1" }),
                    Ok(new { rows = new[] { new { id = 1 } }, next_cursor = "c2" }),
                    Ok(new { rows = new[] { new { id = 2 } }, next_cursor = (string?)null }));
                var c = Client(h);
                var offer = await c.QuoteCapacityWorkAsync(new { ast_hash = "h1", operation = "find", requested_units = 5 });
                var run = await c.AuthorizeCapacityWorkAsync(new
                {
                    quote_id = offer.GetProperty("quote_id").GetString(),
                    quote_hash = offer.GetProperty("quote_hash").GetString(),
                    confirm_max_cents = 125,
                    idempotency_key = "saved-key-123",
                });
                var ids = new List<int>();
                await foreach (var row in c.EachRowAsync(run.GetProperty("find_id").GetString()!, 50))
                {
                    ids.Add(row.GetProperty("id").GetInt32());
                }
                Equal("1,2", string.Join(",", ids), "rows");
                Equal("https://api.specstream.ai/v1/capacity/executions", h.Calls[1].Uri, "authorize uri");
                Equal("https://api.specstream.ai/v1/finds/f1/rows?limit=50", h.Calls[2].Uri, "page 1");
                Equal("https://api.specstream.ai/v1/finds/f1/rows?limit=50&cursor=c2", h.Calls[3].Uri, "page 2");
            });

            await Run("authorize sends nothing without the exact approval", async () =>
            {
                var h = new FakeHandler();
                var c = Client(h);
                await ThrowsAsync<ArgumentException>(() => c.AuthorizeCapacityWorkAsync(new { quote_id = "q1", quote_hash = QuoteHash, idempotency_key = "saved-key-123" }));
                await ThrowsAsync<ArgumentException>(() => c.AuthorizeCapacityWorkAsync(new { quote_id = "q1", quote_hash = "short", confirm_max_cents = 1, idempotency_key = "saved-key-123" }));
                await ThrowsAsync<ArgumentException>(() => c.AuthorizeCapacityWorkAsync(new { quote_id = "q1", quote_hash = QuoteHash, confirm_max_cents = -1, idempotency_key = "saved-key-123" }));
                await ThrowsAsync<ArgumentException>(() => c.AuthorizeCapacityWorkAsync(new { quote_id = "q1", quote_hash = QuoteHash, confirm_max_cents = 1, idempotency_key = "short" }));
                await ThrowsAsync<ArgumentException>(() => c.AuthorizeCapacityWorkAsync(new { quote_id = "q1", quote_hash = QuoteHash, confirm_max_cents = 1, idempotency_key = "saved-key-123", extra = 1 }));
                Equal(0, h.Calls.Count, "calls sent");
            });

            await Run("row page limit and cursor are checked", async () =>
            {
                var c = Client(new FakeHandler());
                await ThrowsAsync<ArgumentOutOfRangeException>(() => c.RowsAsync("f1", null, 0));
                await ThrowsAsync<ArgumentException>(() => c.RowsAsync("f1", ""));
            });

            await Run("create monitor posts the approved schedule", async () =>
            {
                var h = new FakeHandler(Ok(new { schedule_id = "s1", version = 1, state = "active" }));
                var data = await Client(h).CreateMonitorAsync(MonitorBody());
                Equal("s1", data.GetProperty("schedule_id").GetString(), "schedule");
                var call = h.Calls.Single();
                Equal("POST", call.Method, "method");
                Equal("https://api.specstream.ai/v1/capacity/schedules", call.Uri, "uri");
                Equal(500, call.Body!.Value.GetProperty("per_run_cents").GetInt32(), "per run");
                Equal("h1", call.Body!.Value.GetProperty("scope").GetProperty("ast_hash").GetString(), "scope");
            });

            await Run("create monitor sends nothing without limits, key or a cadence of an hour", async () =>
            {
                var h = new FakeHandler();
                var c = Client(h);
                await ThrowsAsync<ArgumentException>(() => c.CreateMonitorAsync(MonitorBody(perRun: 0)));
                await ThrowsAsync<ArgumentException>(() => c.CreateMonitorAsync(MonitorBody(perRun: "500")));
                await ThrowsAsync<ArgumentException>(() => c.CreateMonitorAsync(MonitorBody(key: "short")));
                await ThrowsAsync<ArgumentException>(() => c.CreateMonitorAsync(MonitorBody(cadence: 60)));
                await ThrowsAsync<ArgumentException>(() => c.CreateMonitorAsync(new { idempotency_key = "monitor-key-0001" }));
                Equal(0, h.Calls.Count, "calls sent");
            });

            await Run("list monitors and their runs with paging", async () =>
            {
                var h = new FakeHandler(Ok(new { schedules = Array.Empty<object>() }), Ok(new { occurrences = Array.Empty<object>() }));
                var c = Client(h);
                await c.ListMonitorsAsync(projectId: "p 1", limit: 10);
                await c.ListMonitorRunsAsync("s1", before: "2026-11-01T00:00:00Z", limit: 5);
                Equal("https://api.specstream.ai/v1/capacity/schedules?project_id=p%201&limit=10", h.Calls[0].Uri, "list");
                Equal("https://api.specstream.ai/v1/capacity/schedules/s1/occurrences?before=2026-11-01T00%3A00%3A00Z&limit=5", h.Calls[1].Uri, "runs");
            });

            await Run("pause, resume and delete send the state and expected version", async () =>
            {
                var h = new FakeHandler(Ok(new { state = "paused" }), Ok(new { state = "active" }), Ok(new { state = "deleted" }));
                var c = Client(h);
                await c.PauseMonitorAsync("s1", 1);
                await c.ResumeMonitorAsync("s1", 2);
                await c.DeleteMonitorAsync("s1", 3);
                var states = h.Calls.Select(x => x.Body!.Value.GetProperty("state").GetString() + "@" + x.Body!.Value.GetProperty("expected_version").GetInt32());
                Equal("paused@1,active@2,deleted@3", string.Join(",", states), "states");
                True(h.Calls.All(x => x.Method == "PATCH" && x.Uri == "https://api.specstream.ai/v1/capacity/schedules/s1"), "patch uri");
                await ThrowsAsync<ArgumentOutOfRangeException>(() => c.PauseMonitorAsync("s1", 0));
            });

            await Run("run now, delivery and revisit use their addresses", async () =>
            {
                var h = new FakeHandler(Ok(new { find_id = "f9" }), Ok(new { version = 2 }), Ok(new { items = Array.Empty<object>(), next_after = (string?)null }));
                var c = Client(h);
                await c.RunMonitorNowAsync("s1");
                await c.SetMonitorDeliveryAsync("s1", new { expected_version = 1, notify = true, webhook = "https://example.com/hook" });
                await c.GetRevisitAsync("f9", after: "a1", limit: 20);
                Equal("POST https://api.specstream.ai/v1/capacity/schedules/s1/run", h.Calls[0].Method + " " + h.Calls[0].Uri, "run now");
                True(h.Calls[0].Body == null, "run now has no body");
                Equal("PATCH https://api.specstream.ai/v1/workspace/schedules/s1/delivery", h.Calls[1].Method + " " + h.Calls[1].Uri, "delivery");
                Equal("https://example.com/hook", h.Calls[1].Body!.Value.GetProperty("webhook").GetString(), "webhook");
                Equal("GET https://api.specstream.ai/v1/finds/f9/revisit?after=a1&limit=20", h.Calls[2].Method + " " + h.Calls[2].Uri, "revisit");
            });

            await Run("web search and extract", async () =>
            {
                var h = new FakeHandler(Ok(new { sources = Array.Empty<object>() }), Ok(new { results = Array.Empty<object>() }));
                var c = Client(h);
                await c.WebSearchAsync("population of Japan", passages: true);
                await c.ExtractPagesAsync(new { urls = new[] { "https://example.com" } });
                Equal("https://api.specstream.ai/v1/web-search?q=population%20of%20Japan&passages=true", h.Calls[0].Uri, "search");
                Equal("https://example.com", h.Calls[1].Body!.Value.GetProperty("urls")[0].GetString(), "extract");
            });

            await Run("an API error carries status, code and details", async () =>
            {
                var h = new FakeHandler((402, new { error = new { code = "insufficient_balance", details = new { needed_cents = 40 } } }, null));
                var ex = await ThrowsAsync<SpecStreamException>(() => Client(h).GetCapacityBalanceAsync());
                Equal(402, ex.Status, "status");
                Equal("insufficient_balance", ex.Code, "code");
                Equal(40, ex.Details!.Value.GetProperty("needed_cents").GetInt32(), "details");
            });

            await Run("invalid answers are errors", async () =>
            {
                var h = new FakeHandler((200, "not json", null), (200, new { data = new[] { 1 } }, null), (500, "boom", null));
                var c = Client(h);
                Equal(200, (await ThrowsAsync<SpecStreamException>(() => c.GetFindAsync("f1"))).Status, "invalid json");
                await ThrowsAsync<SpecStreamException>(() => c.GetFindAsync("f1"));
                var ex = await ThrowsAsync<SpecStreamException>(() => c.GetFindAsync("f1"));
                Equal(500, ex.Status, "status");
                Equal("boom", ex.RawBody, "raw");
            });

            await Run("a short 503 Retry-After is asked once more", async () =>
            {
                var waits = new List<TimeSpan>();
                var h = new FakeHandler((503, new { error = new { code = "busy" } }, "2"), Ok(new { status = "running" }));
                var data = await Client(h, waits: waits).GetFindAsync("f1");
                Equal("running", data.GetProperty("status").GetString(), "data");
                Equal(2, h.Calls.Count, "calls");
                Equal(TimeSpan.FromSeconds(2), waits.Single(), "wait");
            });

            await Run("a long 503 Retry-After and other failures are not retried", async () =>
            {
                var h = new FakeHandler((503, new { error = new { code = "busy" } }, "60"), (429, new { error = new { code = "rate" } }, "1"));
                var c = Client(h);
                Equal(503, (await ThrowsAsync<SpecStreamException>(() => c.GetFindAsync("f1"))).Status, "503");
                Equal(429, (await ThrowsAsync<SpecStreamException>(() => c.GetFindAsync("f1"))).Status, "429");
                Equal(2, h.Calls.Count, "calls");
            });

            await Run("a transport failure becomes a SpecStreamException without the key", async () =>
            {
                var c = new SpecStreamClient("ss_secret_value", "http://127.0.0.1:1/", TimeSpan.FromSeconds(5));
                var ex = await ThrowsAsync<SpecStreamException>(() => c.GetFindAsync("f1"));
                Equal(0, ex.Status, "status");
                True(!ex.Message.Contains("ss_secret_value"), "key in message");
            });

            await Run("create browser session posts the settings with the idempotency key", async () =>
            {
                var h = new FakeHandler((201, new { data = new { id = "bs_1", status = "running" } }, null), (201, new { data = new { id = "bs_2" } }, null));
                var c = Client(h);
                var data = await c.CreateBrowserSessionAsync(new { timeout_s = 300, allowed_domains = new[] { "example.com" } }, idempotencyKey: "open-0001");
                Equal("bs_1", data.GetProperty("id").GetString(), "id");
                var call = h.Calls[0];
                Equal("POST", call.Method, "method");
                Equal("https://api.specstream.ai/v1/browser/sessions", call.Uri, "uri");
                Equal("open-0001", call.Headers["Idempotency-Key"], "key header");
                Equal(300, call.Body!.Value.GetProperty("timeout_s").GetInt32(), "timeout_s");
                await c.CreateBrowserSessionAsync();
                Equal("{}", h.Calls[1].Body!.Value.GetRawText(), "empty body");
                True(!h.Calls[1].Headers.ContainsKey("Idempotency-Key"), "no key header without a key");
                await ThrowsAsync<ArgumentException>(() => c.CreateBrowserSessionAsync(idempotencyKey: "two words"));
                await ThrowsAsync<ArgumentException>(() => c.CreateBrowserSessionAsync(idempotencyKey: new string('k', 129)));
                Equal(2, h.Calls.Count, "a bad key sends nothing");
            });

            await Run("browser session reads, steps and release go to the session's own paths", async () =>
            {
                var h = new FakeHandler(
                    Ok(new { sessions = new[] { new { id = "bs_1" } }, next_cursor = (string?)null }),
                    Ok(new { id = "bs_1", status = "running" }),
                    Ok(new { result = new[] { new { type = "text", text = "Example Domain" } }, price_usd = 0.001 }),
                    Ok(new { result = Array.Empty<object>(), took_ms = 3 }),
                    Ok(new { id = "bs_1", status = "ended", ended_reason = "released" }));
                var c = Client(h);
                await c.ListBrowserSessionsAsync(status: "running", limit: 5, cursor: "c 1");
                Equal("https://api.specstream.ai/v1/browser/sessions?status=running&limit=5&cursor=c%201", h.Calls[0].Uri, "list uri");
                await c.GetBrowserSessionAsync("bs_1");
                Equal("https://api.specstream.ai/v1/browser/sessions/bs_1", h.Calls[1].Uri, "get uri");
                var step = await c.BrowserActionAsync("bs_1", "browser_navigate", new { url = "https://example.com" });
                Equal("Example Domain", step.GetProperty("result")[0].GetProperty("text").GetString(), "step text");
                Equal("https://api.specstream.ai/v1/browser/sessions/bs_1/actions", h.Calls[2].Uri, "actions uri");
                Equal("browser_navigate", h.Calls[2].Body!.Value.GetProperty("tool").GetString(), "tool");
                Equal("https://example.com", h.Calls[2].Body!.Value.GetProperty("arguments").GetProperty("url").GetString(), "arguments");
                await c.BrowserActionAsync("bs_1", "browser_snapshot");
                Equal("{}", h.Calls[3].Body!.Value.GetProperty("arguments").GetRawText(), "no arguments is an empty object");
                var ended = await c.ReleaseBrowserSessionAsync("bs_1");
                Equal("released", ended.GetProperty("ended_reason").GetString(), "ended");
                Equal("POST", h.Calls[4].Method, "release method");
                Equal("https://api.specstream.ai/v1/browser/sessions/bs_1/release", h.Calls[4].Uri, "release uri");
                await ThrowsAsync<ArgumentException>(() => c.ReleaseBrowserSessionAsync(""));
                await ThrowsAsync<ArgumentException>(() => c.BrowserActionAsync("bs_1", " "));
                await ThrowsAsync<ArgumentOutOfRangeException>(() => c.ListBrowserSessionsAsync(limit: 101));
                Equal(5, h.Calls.Count, "a bad call sends nothing");
            });

            await Run("browser downloads returns the zip's bytes and a refusal carries the API's code", async () =>
            {
                var h = new FakeHandler((200, "PK-zip-bytes", null), (410, new { error = new { code = "gone", message = "deleted" } }, null));
                var c = Client(h);
                var bytes = await c.BrowserDownloadsAsync("bs_1");
                Equal("PK-zip-bytes", System.Text.Encoding.UTF8.GetString(bytes), "bytes");
                Equal("https://api.specstream.ai/v1/browser/sessions/bs_1/downloads", h.Calls[0].Uri, "uri");
                Equal("Bearer ss_test_key", h.Calls[0].Headers["Authorization"], "authorization");
                var ex = await ThrowsAsync<SpecStreamException>(() => c.BrowserDownloadsAsync("bs_1"));
                Equal(410, ex.Status, "status");
                Equal("gone", ex.Code, "code");
            });

            Console.WriteLine(_passed + " passed, " + Failures.Count + " failed");
            return Failures.Count == 0 ? 0 : 1;
        }
    }
}
