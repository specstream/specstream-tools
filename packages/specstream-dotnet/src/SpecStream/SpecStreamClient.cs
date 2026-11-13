using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace SpecStream
{
    /// <summary>
    /// Client for the SpecStream API: Deep Search (read a request, quote it, approve it, read the rows),
    /// monitors (approved recurring runs, their runs, their delivery and what a refresh reached),
    /// the Search API, the Extract API and browser sessions (a real browser that SpecStream runs).
    /// </summary>
    /// <remarks>
    /// Every call returns the <c>data</c> object of the API's answer as a <see cref="JsonElement"/>.
    /// Request bodies are any object <see cref="JsonSerializer"/> can write: an anonymous object,
    /// a dictionary or your own type. One client can be shared across threads. Redirects are not
    /// followed and no proxy from the environment is used, so the key goes only to the base address.
    /// </remarks>
    public sealed class SpecStreamClient : IDisposable
    {
        /// <summary>The public API.</summary>
        public const string DefaultBaseUrl = "https://api.specstream.ai";

        /// <summary>The package version, sent in the User-Agent.</summary>
        public const string Version = "0.1.0";

        /// <summary>A 503 that names a Retry-After of at most this many seconds is asked once more.</summary>
        public const double RetryAfterMaxSeconds = 10.0;

        private static readonly Regex QuoteHash = new Regex("^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
        private static readonly JsonSerializerOptions WriteOptions = new JsonSerializerOptions();

        private readonly string _authorization;
        private readonly HttpClient _http;
        private readonly bool _ownsHttp;
        private readonly Func<TimeSpan, CancellationToken, Task> _delay;

        /// <summary>Creates a client.</summary>
        /// <param name="apiKey">An API key from Agents &amp; API in your SpecStream workspace.</param>
        /// <param name="baseUrl">The API address; <see cref="DefaultBaseUrl"/> when null or empty.</param>
        /// <param name="timeout">Per request; 150 seconds when null.</param>
        /// <param name="handler">Optional HTTP handler, for tests and for apps that bring their own HTTP stack.</param>
        /// <param name="delay">Optional wait used before the one retry after a 503; for tests.</param>
        public SpecStreamClient(
            string apiKey,
            string? baseUrl = null,
            TimeSpan? timeout = null,
            HttpMessageHandler? handler = null,
            Func<TimeSpan, CancellationToken, Task>? delay = null)
        {
            var key = (apiKey ?? string.Empty).Trim();
            if (key.Length == 0)
            {
                throw new SpecStreamException("SPECSTREAM_API_KEY is required");
            }

            _authorization = key.StartsWith("bearer ", StringComparison.OrdinalIgnoreCase) ? key : "Bearer " + key;
            var root = string.IsNullOrEmpty(baseUrl) ? DefaultBaseUrl : baseUrl!;
            BaseUrl = new Uri(root.TrimEnd('/') + "/", UriKind.Absolute);
            Timeout = timeout ?? TimeSpan.FromSeconds(150);
            _delay = delay ?? ((wait, token) => Task.Delay(wait, token));

            if (handler == null)
            {
                handler = new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false };
                _ownsHttp = true;
            }
            else
            {
                _ownsHttp = false;
            }

            _http = new HttpClient(handler, disposeHandler: _ownsHttp) { Timeout = Timeout };
        }

        /// <summary>Creates a client with the key in the SPECSTREAM_API_KEY environment variable.</summary>
        public static SpecStreamClient FromEnvironment(string? baseUrl = null)
        {
            return new SpecStreamClient(Environment.GetEnvironmentVariable("SPECSTREAM_API_KEY") ?? string.Empty, baseUrl);
        }

        /// <summary>The API address every call goes to.</summary>
        public Uri BaseUrl { get; }

        /// <summary>The per-request timeout.</summary>
        public TimeSpan Timeout { get; }

        /// <summary>Never shows the key.</summary>
        public override string ToString() => "SpecStreamClient(" + BaseUrl + ")";

        /// <inheritdoc />
        public void Dispose()
        {
            _http.Dispose();
        }

        // --- Deep Search ---------------------------------------------------------------

        /// <summary>POST /v1/parse: read a request in everyday words into a reading (the spec).</summary>
        public Task<JsonElement> CompileAsync(string q, string locale = "en-US", CancellationToken cancellationToken = default)
            => SendAsync("POST", "/v1/parse", new Dictionary<string, object?> { ["q"] = q, ["locale"] = locale }, cancellationToken);

        /// <summary>POST /v1/parse/from-chips: change a condition or a fact of a reading.</summary>
        public Task<JsonElement> EditSpecAsync(object ast, object? operations = null, CancellationToken cancellationToken = default)
            => SendAsync("POST", "/v1/parse/from-chips", new Dictionary<string, object?> { ["ast"] = ast, ["operations"] = operations ?? Array.Empty<object>() }, cancellationToken);

        /// <summary>GET /v1/spec-options/{target}: the conditions and facts a kind of record supports.</summary>
        public Task<JsonElement> SpecOptionsAsync(string target, CancellationToken cancellationToken = default)
            => SendAsync("GET", "/v1/spec-options/" + Escape(target), null, cancellationToken);

        /// <summary>POST /v1/capacity/quotes: price a reading before anything runs. Nothing is charged.</summary>
        public Task<JsonElement> QuoteCapacityWorkAsync(object body, CancellationToken cancellationToken = default)
            => SendAsync("POST", "/v1/capacity/quotes", body, cancellationToken);

        /// <summary>GET /v1/capacity/quotes/{quote_id}</summary>
        public Task<JsonElement> GetCapacityQuoteAsync(string quoteId, CancellationToken cancellationToken = default)
            => SendAsync("GET", "/v1/capacity/quotes/" + Escape(quoteId), null, cancellationToken);

        /// <summary>
        /// POST /v1/capacity/executions: approve the exact quote and start the run. Sends nothing unless
        /// quote_id, quote_hash, confirm_max_cents and idempotency_key are all present and well formed.
        /// </summary>
        public Task<JsonElement> AuthorizeCapacityWorkAsync(object body, CancellationToken cancellationToken = default)
        {
            RequireWorkAuthorization(body);
            return SendAsync("POST", "/v1/capacity/executions", body, cancellationToken);
        }

        /// <summary>GET /v1/capacity/requests/{request_key}: the run already started with this key.</summary>
        public Task<JsonElement> GetCapacityRequestAsync(string requestKey, string? projectId = null, CancellationToken cancellationToken = default)
            => SendAsync("GET", WithQuery("/v1/capacity/requests/" + Escape(requestKey), ("project_id", projectId)), null, cancellationToken);

        /// <summary>GET /v1/capacity/balance</summary>
        public Task<JsonElement> GetCapacityBalanceAsync(string? projectId = null, CancellationToken cancellationToken = default)
            => SendAsync("GET", WithQuery("/v1/capacity/balance", ("project_id", projectId)), null, cancellationToken);

        /// <summary>GET /v1/finds/{find_id}: progress of a run.</summary>
        public Task<JsonElement> GetFindAsync(string findId, CancellationToken cancellationToken = default)
            => SendAsync("GET", "/v1/finds/" + Escape(findId), null, cancellationToken);

        /// <summary>POST /v1/finds/{find_id}/cancel</summary>
        public Task<JsonElement> CancelFindAsync(string findId, CancellationToken cancellationToken = default)
            => SendAsync("POST", "/v1/finds/" + Escape(findId) + "/cancel", new Dictionary<string, object?>(), cancellationToken);

        /// <summary>GET /v1/finds/{find_id}/rows: one page of delivered rows. Follow next_cursor.</summary>
        public Task<JsonElement> RowsAsync(string findId, string? cursor = null, int limit = 100, CancellationToken cancellationToken = default)
        {
            if (limit < 1 || limit > 100)
            {
                throw new ArgumentOutOfRangeException(nameof(limit), "Row page limit must be an integer from 1 to 100");
            }
            if (cursor != null && (cursor.Length == 0 || cursor.Length > 2048))
            {
                throw new ArgumentException("Use the opaque next_cursor returned by this Delivery", nameof(cursor));
            }

            return SendAsync("GET", WithQuery("/v1/finds/" + Escape(findId) + "/rows", ("limit", limit.ToString(CultureInfo.InvariantCulture)), ("cursor", cursor)), null, cancellationToken);
        }

        /// <summary>Every delivered row of a run, page after page until next_cursor is null. Reading rows you own costs nothing.</summary>
        public async IAsyncEnumerable<JsonElement> EachRowAsync(string findId, int limit = 100, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            string? cursor = null;
            while (true)
            {
                var page = await RowsAsync(findId, cursor, limit, cancellationToken).ConfigureAwait(false);
                if (page.TryGetProperty("rows", out var rows) && rows.ValueKind == JsonValueKind.Array)
                {
                    foreach (var row in rows.EnumerateArray())
                    {
                        yield return row;
                    }
                }

                cursor = page.TryGetProperty("next_cursor", out var next) && next.ValueKind == JsonValueKind.String ? next.GetString() : null;
                if (string.IsNullOrEmpty(cursor))
                {
                    yield break;
                }
            }
        }

        /// <summary>POST /v1/finds/{find_id}/export: format is csv, xlsx, json or html.</summary>
        public Task<JsonElement> ExportAsync(string findId, string format = "csv", CancellationToken cancellationToken = default)
            => SendAsync("POST", "/v1/finds/" + Escape(findId) + "/export", new Dictionary<string, object?> { ["format"] = format }, cancellationToken);

        // --- Monitors --------------------------------------------------------------------

        /// <summary>
        /// POST /v1/capacity/schedules: approve future runs of an exact request within set spending limits.
        /// The body holds idempotency_key, scope (the quote request), cadence_seconds (3600 or more),
        /// first_due_at, per_run_cents, period_cents and valid_until, and may hold calendar_schedule.
        /// Sends nothing unless the key and both spending limits are present and well formed.
        /// </summary>
        public Task<JsonElement> CreateMonitorAsync(object body, CancellationToken cancellationToken = default)
        {
            RequireMonitorAuthorization(body);
            return SendAsync("POST", "/v1/capacity/schedules", body, cancellationToken);
        }

        /// <summary>GET /v1/capacity/schedules: your monitors and their current state.</summary>
        public Task<JsonElement> ListMonitorsAsync(string? projectId = null, string? after = null, int? limit = null, CancellationToken cancellationToken = default)
            => SendAsync("GET", WithQuery("/v1/capacity/schedules", ("project_id", projectId), ("after", after), ("limit", limit?.ToString(CultureInfo.InvariantCulture))), null, cancellationToken);

        /// <summary>PATCH /v1/capacity/schedules/{schedule_id}: pause a monitor. Missed runs are never bought later.</summary>
        public Task<JsonElement> PauseMonitorAsync(string scheduleId, int expectedVersion, CancellationToken cancellationToken = default)
            => SetMonitorStateAsync(scheduleId, "paused", expectedVersion, cancellationToken);

        /// <summary>PATCH /v1/capacity/schedules/{schedule_id}: resume a paused monitor.</summary>
        public Task<JsonElement> ResumeMonitorAsync(string scheduleId, int expectedVersion, CancellationToken cancellationToken = default)
            => SetMonitorStateAsync(scheduleId, "active", expectedVersion, cancellationToken);

        /// <summary>PATCH /v1/capacity/schedules/{schedule_id}: delete a monitor.</summary>
        public Task<JsonElement> DeleteMonitorAsync(string scheduleId, int expectedVersion, CancellationToken cancellationToken = default)
            => SetMonitorStateAsync(scheduleId, "deleted", expectedVersion, cancellationToken);

        /// <summary>GET /v1/capacity/schedules/{schedule_id}/occurrences: completed, blocked and missed runs of a monitor.</summary>
        public Task<JsonElement> ListMonitorRunsAsync(string scheduleId, string? before = null, int? limit = null, CancellationToken cancellationToken = default)
            => SendAsync("GET", WithQuery("/v1/capacity/schedules/" + Escape(scheduleId) + "/occurrences", ("before", before), ("limit", limit?.ToString(CultureInfo.InvariantCulture))), null, cancellationToken);

        /// <summary>POST /v1/capacity/schedules/{schedule_id}/run: run an active monitor once now, inside its own limits, without moving its schedule.</summary>
        public Task<JsonElement> RunMonitorNowAsync(string scheduleId, CancellationToken cancellationToken = default)
            => SendAsync("POST", "/v1/capacity/schedules/" + Escape(scheduleId) + "/run", null, cancellationToken);

        /// <summary>
        /// PATCH /v1/workspace/schedules/{schedule_id}/delivery: where a monitor's changes go (notify, slack,
        /// sendTo, webhook). The body holds expected_version. Starts no work.
        /// </summary>
        public Task<JsonElement> SetMonitorDeliveryAsync(string scheduleId, object body, CancellationToken cancellationToken = default)
            => SendAsync("PATCH", "/v1/workspace/schedules/" + Escape(scheduleId) + "/delivery", body, cancellationToken);

        /// <summary>GET /v1/finds/{id}/revisit: which saved results a refresh reached, and which it did not. Follow next_after.</summary>
        public Task<JsonElement> GetRevisitAsync(string findId, string? after = null, int? limit = null, CancellationToken cancellationToken = default)
            => SendAsync("GET", WithQuery("/v1/finds/" + Escape(findId) + "/revisit", ("after", after), ("limit", limit?.ToString(CultureInfo.InvariantCulture))), null, cancellationToken);

        // --- Search API and Extract API --------------------------------------------------

        /// <summary>GET /v1/web-search</summary>
        public Task<JsonElement> WebSearchAsync(string q, bool? passages = null, CancellationToken cancellationToken = default)
            => SendAsync("GET", WithQuery("/v1/web-search", ("q", q), ("passages", passages == null ? null : (passages.Value ? "true" : "false"))), null, cancellationToken);

        /// <summary>POST /v1/extract, for example <c>new { urls = new[] { "https://example.com" } }</c>.</summary>
        public Task<JsonElement> ExtractPagesAsync(object body, CancellationToken cancellationToken = default)
            => SendAsync("POST", "/v1/extract", body, cancellationToken);

        // --- Browser sessions ------------------------------------------------------------

        /// <summary>
        /// POST /v1/browser/sessions: open a real browser that SpecStream runs. Every field of the body is
        /// optional (timeout_s, idle_timeout_s, keep_alive, headless, viewport, allowed_domains, block_media,
        /// metadata). The answer holds the session's id, its connect_url for Playwright or Puppeteer and its
        /// price. With an <paramref name="idempotencyKey"/> of 1 to 128 characters, a repeated call returns the
        /// same session and opens no second browser.
        /// </summary>
        public Task<JsonElement> CreateBrowserSessionAsync(object? body = null, string? idempotencyKey = null, CancellationToken cancellationToken = default)
        {
            if (idempotencyKey != null && !IsHeaderKey(idempotencyKey))
            {
                throw new ArgumentException("Use an idempotency key of 1 to 128 printable ASCII characters", nameof(idempotencyKey));
            }

            return SendAsync("POST", "/v1/browser/sessions", body ?? new Dictionary<string, object?>(), idempotencyKey, cancellationToken);
        }

        /// <summary>GET /v1/browser/sessions: your sessions, newest first. status is starting, running or ended. Follow next_cursor.</summary>
        public Task<JsonElement> ListBrowserSessionsAsync(string? status = null, int? limit = null, string? cursor = null, CancellationToken cancellationToken = default)
        {
            if (limit != null && (limit < 1 || limit > 100))
            {
                throw new ArgumentOutOfRangeException(nameof(limit), "Session page limit must be an integer from 1 to 100");
            }

            return SendAsync("GET", WithQuery("/v1/browser/sessions", ("status", status), ("limit", limit?.ToString(CultureInfo.InvariantCulture)), ("cursor", cursor)), null, cancellationToken);
        }

        /// <summary>GET /v1/browser/sessions/{id}: the session now, with its seconds, steps and what it has cost so far.</summary>
        public Task<JsonElement> GetBrowserSessionAsync(string sessionId, CancellationToken cancellationToken = default)
            => SendAsync("GET", "/v1/browser/sessions/" + Segment(sessionId, nameof(sessionId)), null, cancellationToken);

        /// <summary>POST /v1/browser/sessions/{id}/release: close the browser. Time stops being charged. Safe to call twice.</summary>
        public Task<JsonElement> ReleaseBrowserSessionAsync(string sessionId, CancellationToken cancellationToken = default)
            => SendAsync("POST", "/v1/browser/sessions/" + Segment(sessionId, nameof(sessionId)) + "/release", null, cancellationToken);

        /// <summary>
        /// POST /v1/browser/sessions/{id}/actions: one step in the browser. <paramref name="tool"/> is a
        /// Playwright MCP tool name (browser_navigate, browser_snapshot, browser_click, browser_type,
        /// browser_take_screenshot and the others) or browser_read for the page's text;
        /// <paramref name="arguments"/> are that tool's arguments. A step the page refuses comes back in the
        /// answer's <c>error</c>, not as an exception.
        /// </summary>
        public Task<JsonElement> BrowserActionAsync(string sessionId, string tool, object? arguments = null, CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(tool))
            {
                throw new ArgumentException("Name the tool, for example browser_navigate", nameof(tool));
            }

            return SendAsync("POST", "/v1/browser/sessions/" + Segment(sessionId, nameof(sessionId)) + "/actions", new Dictionary<string, object?> { ["tool"] = tool, ["arguments"] = arguments ?? new Dictionary<string, object?>() }, cancellationToken);
        }

        /// <summary>
        /// GET /v1/browser/sessions/{id}/downloads: the files the browser downloaded, as the bytes of one zip.
        /// Served while the session runs and for ten minutes after it ends.
        /// </summary>
        public async Task<byte[]> BrowserDownloadsAsync(string sessionId, CancellationToken cancellationToken = default)
        {
            const string method = "GET";
            var path = "/v1/browser/sessions/" + Segment(sessionId, nameof(sessionId)) + "/downloads";
            HttpResponseMessage? response = null;
            try
            {
                response = await SendOnceAsync(method, new Uri(BaseUrl, path.TrimStart('/')), null, null, cancellationToken, "application/zip").ConfigureAwait(false);
                var status = (int)response.StatusCode;
                if (status >= 200 && status <= 299)
                {
                    return response.Content == null ? Array.Empty<byte>() : await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
                }

                var text = response.Content == null ? string.Empty : await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
                Parse(method, path, status, text);
                throw new SpecStreamException(method + " " + path + " failed with HTTP " + status, status, rawBody: text);
            }
            catch (SpecStreamException)
            {
                throw;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex) when (ex is HttpRequestException || ex is TaskCanceledException || ex is System.IO.IOException)
            {
                throw new SpecStreamException(method + " " + path + " transport failed (" + ex.GetType().Name + ")", inner: ex);
            }
            finally
            {
                response?.Dispose();
            }
        }

        // --- shared ----------------------------------------------------------------------

        /// <summary>Checks an approval body before it is sent; throws <see cref="ArgumentException"/> when it is not exact.</summary>
        public static void RequireWorkAuthorization(object body)
        {
            var value = ToElement(body);
            var required = new[] { "quote_id", "quote_hash", "idempotency_key", "confirm_max_cents" };
            if (value.ValueKind != JsonValueKind.Object || !HasExactly(value, required, new[] { "authority_id" }))
            {
                throw new ArgumentException("Provide the exact quote identity, signature, maximum cents and request key");
            }

            if (!IsNonEmptyString(value, "quote_id"))
            {
                throw new ArgumentException("An explicit quote identity is required");
            }
            if (!(value.GetProperty("quote_hash").ValueKind == JsonValueKind.String && QuoteHash.IsMatch(value.GetProperty("quote_hash").GetString()!)))
            {
                throw new ArgumentException("The reviewed quote signature is required");
            }
            RequireRequestKey(value);
            if (!(value.GetProperty("confirm_max_cents").ValueKind == JsonValueKind.Number
                  && value.GetProperty("confirm_max_cents").TryGetInt64(out var maximum) && maximum >= 0))
            {
                throw new ArgumentException("The approved maximum must be an explicit nonnegative integer in cents");
            }
            if (value.TryGetProperty("authority_id", out var authority) && authority.ValueKind != JsonValueKind.String && authority.ValueKind != JsonValueKind.Null)
            {
                throw new ArgumentException("Authority must be an explicit existing identifier");
            }
        }

        /// <summary>Checks a monitor approval before it is sent: a request key and positive per-run and period limits in cents.</summary>
        public static void RequireMonitorAuthorization(object body)
        {
            var value = ToElement(body);
            if (value.ValueKind != JsonValueKind.Object)
            {
                throw new ArgumentException("Provide the monitor's request key, scope, cadence and spending limits");
            }
            foreach (var name in new[] { "idempotency_key", "scope", "cadence_seconds", "first_due_at", "per_run_cents", "period_cents", "valid_until" })
            {
                if (!value.TryGetProperty(name, out _))
                {
                    throw new ArgumentException("A monitor needs " + name);
                }
            }
            RequireRequestKey(value);
            foreach (var name in new[] { "per_run_cents", "period_cents" })
            {
                var limit = value.GetProperty(name);
                if (!(limit.ValueKind == JsonValueKind.Number && limit.TryGetInt64(out var cents) && cents > 0))
                {
                    throw new ArgumentException(name + " must be an explicit positive integer in cents");
                }
            }
            var cadence = value.GetProperty("cadence_seconds");
            if (!(cadence.ValueKind == JsonValueKind.Number && cadence.TryGetInt64(out var seconds) && seconds >= 3600))
            {
                throw new ArgumentException("cadence_seconds must be an integer of at least 3600");
            }
        }

        private Task<JsonElement> SetMonitorStateAsync(string scheduleId, string state, int expectedVersion, CancellationToken cancellationToken)
        {
            if (expectedVersion < 1)
            {
                throw new ArgumentOutOfRangeException(nameof(expectedVersion), "Use the monitor's current version, 1 or more");
            }

            return SendAsync("PATCH", "/v1/capacity/schedules/" + Escape(scheduleId), new Dictionary<string, object?> { ["expected_version"] = expectedVersion, ["state"] = state }, cancellationToken);
        }

        /// <summary>Sends one request and returns the answer's data object. Retries once after a short 503 Retry-After.</summary>
        public Task<JsonElement> SendAsync(string method, string path, object? body, CancellationToken cancellationToken = default)
            => SendAsync(method, path, body, null, cancellationToken);

        private async Task<JsonElement> SendAsync(string method, string path, object? body, string? idempotencyKey, CancellationToken cancellationToken)
        {
            var uri = new Uri(BaseUrl, path.TrimStart('/'));
            var payload = body == null ? null : (body is JsonElement e ? e.GetRawText() : JsonSerializer.Serialize(body, body.GetType(), WriteOptions));
            HttpResponseMessage? response = null;
            try
            {
                response = await SendOnceAsync(method, uri, payload, idempotencyKey, cancellationToken).ConfigureAwait(false);
                var wait = RetryAfter(response);
                if (wait != null)
                {
                    // The server did nothing and names when to ask again: ask once more.
                    response.Dispose();
                    await _delay(wait.Value, cancellationToken).ConfigureAwait(false);
                    response = await SendOnceAsync(method, uri, payload, idempotencyKey, cancellationToken).ConfigureAwait(false);
                }

                var text = response.Content == null ? string.Empty : await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
                return Parse(method, path, (int)response.StatusCode, text);
            }
            catch (SpecStreamException)
            {
                throw;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex) when (ex is HttpRequestException || ex is TaskCanceledException || ex is System.IO.IOException)
            {
                throw new SpecStreamException(method + " " + path + " transport failed (" + ex.GetType().Name + ")", inner: ex);
            }
            finally
            {
                response?.Dispose();
            }
        }

        private Task<HttpResponseMessage> SendOnceAsync(string method, Uri uri, string? payload, string? idempotencyKey, CancellationToken cancellationToken, string accept = "application/json")
        {
            var request = new HttpRequestMessage(new HttpMethod(method), uri);
            request.Headers.TryAddWithoutValidation("Authorization", _authorization);
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue(accept));
            if (accept != "application/json")
            {
                // A refusal still comes as JSON.
                request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            }
            if (idempotencyKey != null)
            {
                request.Headers.TryAddWithoutValidation("Idempotency-Key", idempotencyKey);
            }
            request.Headers.TryAddWithoutValidation("User-Agent", "specstream-dotnet/" + Version);
            if (payload != null)
            {
                request.Content = new StringContent(payload, Encoding.UTF8, "application/json");
            }

            return _http.SendAsync(request, HttpCompletionOption.ResponseContentRead, cancellationToken);
        }

        private static JsonElement Parse(string method, string path, int status, string text)
        {
            var ok = status >= 200 && status <= 299;
            JsonElement loaded;
            try
            {
                using var doc = JsonDocument.Parse(text);
                loaded = doc.RootElement.Clone();
            }
            catch (JsonException)
            {
                throw new SpecStreamException(method + " " + path + (ok ? " returned invalid JSON" : " failed with HTTP " + status), status, rawBody: text);
            }

            if (!ok)
            {
                throw new SpecStreamException(method + " " + path + " failed with HTTP " + status, status, loaded);
            }
            if (loaded.ValueKind != JsonValueKind.Object)
            {
                throw new SpecStreamException(method + " " + path + " returned non-object JSON", status, loaded);
            }
            var hasError = loaded.TryGetProperty("error", out var error) && error.ValueKind != JsonValueKind.Null;
            if (hasError || !loaded.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object)
            {
                throw new SpecStreamException(method + " " + path + " returned an invalid success envelope", status, loaded);
            }

            return data;
        }

        private static TimeSpan? RetryAfter(HttpResponseMessage response)
        {
            if (response.StatusCode != HttpStatusCode.ServiceUnavailable || response.Headers.RetryAfter == null)
            {
                return null;
            }

            var header = response.Headers.RetryAfter;
            TimeSpan? wait = header.Delta ?? (header.Date != null ? header.Date.Value - DateTimeOffset.UtcNow : (TimeSpan?)null);
            if (wait == null || wait.Value < TimeSpan.Zero || wait.Value.TotalSeconds > RetryAfterMaxSeconds)
            {
                return null;
            }

            return wait;
        }

        private static string Escape(string value) => Uri.EscapeDataString(value ?? string.Empty);

        /// <summary>An id as one path segment; an empty id would turn a call on one session into a call on all of them.</summary>
        private static string Segment(string value, string name)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                throw new ArgumentException("A session id is required", name);
            }

            return Uri.EscapeDataString(value);
        }

        private static bool IsHeaderKey(string value)
        {
            if (value.Length < 1 || value.Length > 128)
            {
                return false;
            }
            foreach (var c in value)
            {
                if (c < 0x21 || c > 0x7e)
                {
                    return false;
                }
            }

            return true;
        }

        private static string WithQuery(string path, params (string Name, string? Value)[] pairs)
        {
            var parts = new List<string>();
            foreach (var (name, value) in pairs)
            {
                if (value != null)
                {
                    parts.Add(Uri.EscapeDataString(name) + "=" + Uri.EscapeDataString(value));
                }
            }

            return parts.Count == 0 ? path : path + "?" + string.Join("&", parts);
        }

        private static JsonElement ToElement(object body)
        {
            if (body is JsonElement element)
            {
                return element;
            }
            if (body == null)
            {
                return default;
            }

            using var doc = JsonDocument.Parse(JsonSerializer.Serialize(body, body.GetType(), WriteOptions));
            return doc.RootElement.Clone();
        }

        private static bool HasExactly(JsonElement value, string[] required, string[] optional)
        {
            var seen = new HashSet<string>();
            foreach (var property in value.EnumerateObject())
            {
                if (Array.IndexOf(required, property.Name) < 0 && Array.IndexOf(optional, property.Name) < 0)
                {
                    return false;
                }
                seen.Add(property.Name);
            }

            foreach (var name in required)
            {
                if (!seen.Contains(name))
                {
                    return false;
                }
            }

            return true;
        }

        private static bool IsNonEmptyString(JsonElement value, string name)
            => value.TryGetProperty(name, out var item) && item.ValueKind == JsonValueKind.String && item.GetString()!.Length > 0;

        private static void RequireRequestKey(JsonElement value)
        {
            if (!(value.TryGetProperty("idempotency_key", out var key) && key.ValueKind == JsonValueKind.String
                  && key.GetString()!.Length >= 8 && key.GetString()!.Length <= 128))
            {
                throw new ArgumentException("Use a stable request key containing 8 to 128 characters");
            }
        }
    }
}
