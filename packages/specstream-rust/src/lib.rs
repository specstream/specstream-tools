//! Rust client for the SpecStream API: Deep Search (read a request, quote it,
//! approve it, read the rows), the Search API and the Extract API.
//!
//! ```no_run
//! use specstream::Client;
//! use serde_json::json;
//!
//! let client = Client::new(std::env::var("SPECSTREAM_API_KEY").unwrap())?;
//! let reading = client.compile("Open-source vector databases on GitHub, with their license.")?;
//! let offer = client.quote_capacity_work(&json!({
//!     "ast_hash": reading["ast_hash"],
//!     "operation": "find",
//!     "requested_units": reading["ast"]["limit"]["max"],
//! }))?;
//! println!("{} cents at most", offer["maximum_cents"]);
//! # Ok::<(), specstream::Error>(())
//! ```
//!
//! Every call returns the `data` object of the API's reply as a [`serde_json::Value`].

mod error;
mod transport;

use std::fmt;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{Map, Value};

pub use error::{Error, ErrorKind};
pub use serde_json;
pub use transport::{HttpRequest, HttpResponse, Transport, UreqTransport};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const DEFAULT_BASE_URL: &str = "https://api.specstream.ai";
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(150);
/// A 503 that names a `Retry-After` of at most this many seconds is asked once more.
pub const RETRY_AFTER_MAX_SECS: f64 = 10.0;

fn user_agent() -> String {
    format!("specstream-rust/{VERSION}")
}

type Sleeper = Arc<dyn Fn(Duration) + Send + Sync>;

/// Builds a [`Client`] with a base address, a timeout or a transport of your own.
pub struct ClientBuilder {
    api_key: String,
    base_url: String,
    timeout: Duration,
    transport: Option<Arc<dyn Transport>>,
    sleeper: Option<Sleeper>,
}

impl ClientBuilder {
    pub fn base_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = base_url.into();
        self
    }

    /// The whole-call timeout of the default transport (150 seconds unless set).
    pub fn timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    pub fn transport(mut self, transport: impl Transport + 'static) -> Self {
        self.transport = Some(Arc::new(transport));
        self
    }

    /// How the client waits before its one retry after a short `Retry-After`.
    pub fn sleeper(mut self, sleeper: impl Fn(Duration) + Send + Sync + 'static) -> Self {
        self.sleeper = Some(Arc::new(sleeper));
        self
    }

    pub fn build(self) -> Result<Client, Error> {
        let key = self.api_key.trim().to_owned();
        if key.is_empty() {
            return Err(Error::new(
                ErrorKind::Config,
                "SPECSTREAM_API_KEY is required",
            ));
        }
        let base = self.base_url.trim();
        let base = if base.is_empty() {
            DEFAULT_BASE_URL
        } else {
            base
        };
        if !(base.starts_with("https://") || base.starts_with("http://")) {
            return Err(Error::new(
                ErrorKind::Config,
                "The base address must start with https:// or http://",
            ));
        }
        let timeout = self.timeout;
        Ok(Client {
            api_key: key,
            base_url: format!("{}/", base.trim_end_matches('/')),
            transport: self
                .transport
                .unwrap_or_else(|| Arc::new(UreqTransport::new(timeout))),
            sleeper: self.sleeper.unwrap_or_else(|| Arc::new(std::thread::sleep)),
        })
    }
}

/// Client for the SpecStream API. Cheap to clone and safe to share across threads.
#[derive(Clone)]
pub struct Client {
    api_key: String,
    base_url: String,
    transport: Arc<dyn Transport>,
    sleeper: Sleeper,
}

/// Never shows the key.
impl fmt::Debug for Client {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Client")
            .field("base_url", &self.base_url)
            .finish_non_exhaustive()
    }
}

/// Query of the Search API, `GET /v1/web-search`. Only `q` is required.
#[derive(Debug, Clone, Default)]
pub struct WebSearch {
    pub q: String,
    pub passages: Option<bool>,
    pub num: Option<u32>,
    pub page: Option<u32>,
    /// `fast` for the quickest answer.
    pub speed: Option<String>,
    pub news: Option<bool>,
    pub language: Option<String>,
    pub country: Option<String>,
    pub safe: Option<String>,
    pub engines: Option<String>,
    pub engines_asked: Option<bool>,
    pub pages_wait_ms: Option<u32>,
}

impl WebSearch {
    pub fn new(q: impl Into<String>) -> Self {
        WebSearch {
            q: q.into(),
            ..Default::default()
        }
    }

    fn query(&self) -> Vec<(&'static str, String)> {
        let mut pairs = vec![("q", self.q.clone())];
        let mut add = |name: &'static str, value: Option<String>| {
            if let Some(v) = value {
                pairs.push((name, v));
            }
        };
        add("passages", self.passages.map(|v| v.to_string()));
        add("num", self.num.map(|v| v.to_string()));
        add("page", self.page.map(|v| v.to_string()));
        add("speed", self.speed.clone());
        add("news", self.news.map(|v| v.to_string()));
        add("language", self.language.clone());
        add("country", self.country.clone());
        add("safe", self.safe.clone());
        add("engines", self.engines.clone());
        add("engines_asked", self.engines_asked.map(|v| v.to_string()));
        add("pages_wait_ms", self.pages_wait_ms.map(|v| v.to_string()));
        pairs
    }
}

impl Client {
    /// A client for `https://api.specstream.ai` with the default transport.
    pub fn new(api_key: impl Into<String>) -> Result<Client, Error> {
        Client::builder(api_key).build()
    }

    /// A client from the `SPECSTREAM_API_KEY` environment variable.
    pub fn from_env() -> Result<Client, Error> {
        Client::new(std::env::var("SPECSTREAM_API_KEY").unwrap_or_default())
    }

    pub fn builder(api_key: impl Into<String>) -> ClientBuilder {
        ClientBuilder {
            api_key: api_key.into(),
            base_url: DEFAULT_BASE_URL.to_owned(),
            timeout: DEFAULT_TIMEOUT,
            transport: None,
            sleeper: None,
        }
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    // --- Deep Search -------------------------------------------------------------

    /// `POST /v1/parse`: read a request in everyday words into a reading (the spec).
    pub fn compile(&self, q: &str) -> Result<Value, Error> {
        self.compile_with_locale(q, "en-US")
    }

    pub fn compile_with_locale(&self, q: &str, locale: &str) -> Result<Value, Error> {
        self.request(
            "POST",
            "/v1/parse",
            Some(serde_json::json!({ "q": q, "locale": locale })),
        )
    }

    /// `POST /v1/parse/from-chips`: change a condition or a fact of a reading.
    pub fn edit_spec(&self, ast: &Value, operations: &Value) -> Result<Value, Error> {
        let operations = if operations.is_null() {
            Value::Array(vec![])
        } else {
            operations.clone()
        };
        self.request(
            "POST",
            "/v1/parse/from-chips",
            Some(serde_json::json!({ "ast": ast, "operations": operations })),
        )
    }

    /// `GET /v1/spec-options/{target}`: the conditions and facts a kind of record supports.
    pub fn spec_options(&self, target: &str) -> Result<Value, Error> {
        self.request("GET", &format!("/v1/spec-options/{}", escape(target)), None)
    }

    /// `POST /v1/capacity/quotes`: price a reading before anything runs. Nothing is charged.
    pub fn quote_capacity_work(&self, body: &Value) -> Result<Value, Error> {
        self.request("POST", "/v1/capacity/quotes", Some(body.clone()))
    }

    /// `GET /v1/capacity/quotes/{quote_id}`
    pub fn get_capacity_quote(&self, quote_id: &str) -> Result<Value, Error> {
        self.request(
            "GET",
            &format!("/v1/capacity/quotes/{}", escape(quote_id)),
            None,
        )
    }

    /// `POST /v1/capacity/executions`: approve the exact quote and start the run.
    /// Sends nothing unless `quote_id`, `quote_hash`, `confirm_max_cents` and
    /// `idempotency_key` are all present and well formed.
    pub fn authorize_capacity_work(&self, body: &Value) -> Result<Value, Error> {
        require_work_authorization(body)?;
        self.request("POST", "/v1/capacity/executions", Some(body.clone()))
    }

    /// `GET /v1/capacity/requests/{request_key}`: the run already started with this key.
    pub fn get_capacity_request(
        &self,
        request_key: &str,
        project_id: Option<&str>,
    ) -> Result<Value, Error> {
        let path = format!("/v1/capacity/requests/{}", escape(request_key));
        self.request(
            "GET",
            &with_query(&path, &[("project_id", project_id.map(str::to_owned))]),
            None,
        )
    }

    /// `GET /v1/capacity/balance`
    pub fn get_capacity_balance(&self, project_id: Option<&str>) -> Result<Value, Error> {
        self.request(
            "GET",
            &with_query(
                "/v1/capacity/balance",
                &[("project_id", project_id.map(str::to_owned))],
            ),
            None,
        )
    }

    /// `GET /v1/finds/{find_id}`: progress of a run.
    pub fn get_find(&self, find_id: &str) -> Result<Value, Error> {
        self.request("GET", &format!("/v1/finds/{}", escape(find_id)), None)
    }

    /// `POST /v1/finds/{find_id}/cancel`
    pub fn cancel_find(&self, find_id: &str) -> Result<Value, Error> {
        self.request(
            "POST",
            &format!("/v1/finds/{}/cancel", escape(find_id)),
            Some(Value::Object(Map::new())),
        )
    }

    /// `GET /v1/finds/{find_id}/rows`: one page of delivered rows (`limit` 1 to 100).
    /// Pass the page's `next_cursor` to read the next one.
    pub fn rows(&self, find_id: &str, cursor: Option<&str>, limit: u32) -> Result<Value, Error> {
        if !(1..=100).contains(&limit) {
            return Err(Error::new(
                ErrorKind::InvalidArgument,
                "Row page limit must be an integer from 1 to 100",
            ));
        }
        if let Some(c) = cursor {
            if c.is_empty() || c.len() > 2048 {
                return Err(Error::new(
                    ErrorKind::InvalidArgument,
                    "Use the opaque next_cursor returned by this Delivery",
                ));
            }
        }
        let path = format!("/v1/finds/{}/rows", escape(find_id));
        self.request(
            "GET",
            &with_query(
                &path,
                &[
                    ("limit", Some(limit.to_string())),
                    ("cursor", cursor.map(str::to_owned)),
                ],
            ),
            None,
        )
    }

    /// Every delivered row of a run, page after page until `next_cursor` is null.
    /// Reading rows you own costs nothing.
    pub fn all_rows(&self, find_id: &str) -> Result<Vec<Value>, Error> {
        let mut out = Vec::new();
        let mut cursor: Option<String> = None;
        loop {
            let page = self.rows(find_id, cursor.as_deref(), 100)?;
            if let Some(rows) = page.get("rows").and_then(Value::as_array) {
                out.extend(rows.iter().cloned());
            }
            match page.get("next_cursor").and_then(Value::as_str) {
                Some(next) if !next.is_empty() => cursor = Some(next.to_owned()),
                _ => return Ok(out),
            }
        }
    }

    /// `POST /v1/finds/{find_id}/export`: `format` is csv, xlsx, json or html.
    pub fn export(&self, find_id: &str, format: &str) -> Result<Value, Error> {
        self.request(
            "POST",
            &format!("/v1/finds/{}/export", escape(find_id)),
            Some(serde_json::json!({ "format": format })),
        )
    }

    // --- Search API and Extract API ----------------------------------------------

    /// `GET /v1/web-search`
    pub fn web_search(&self, search: &WebSearch) -> Result<Value, Error> {
        let pairs: Vec<(&str, Option<String>)> = search
            .query()
            .into_iter()
            .map(|(k, v)| (k, Some(v)))
            .collect();
        self.request("GET", &with_query("/v1/web-search", &pairs), None)
    }

    /// `POST /v1/extract`, for example `{"urls": ["https://example.com"]}`.
    pub fn extract_pages(&self, body: &Value) -> Result<Value, Error> {
        self.request("POST", "/v1/extract", Some(body.clone()))
    }

    // --- shared --------------------------------------------------------------------

    /// Any call of the API by method and path; returns the reply's `data` object.
    pub fn request(
        &self,
        method: &'static str,
        path: &str,
        body: Option<Value>,
    ) -> Result<Value, Error> {
        let request = HttpRequest {
            method,
            url: format!("{}{}", self.base_url, path.trim_start_matches('/')),
            headers: self.headers(),
            body: body.map(|b| b.to_string()),
        };
        let mut response = self.send(&request, path)?;
        if let Some(wait) = retry_after(&response) {
            // The server did nothing and names when to ask again: ask once more.
            (self.sleeper)(wait);
            response = self.send(&request, path)?;
        }
        parse(method, path, response)
    }

    fn send(&self, request: &HttpRequest, path: &str) -> Result<HttpResponse, Error> {
        // The transport's own text is dropped: it could hold a header value.
        self.transport.send(request).map_err(|_| {
            Error::new(
                ErrorKind::Transport,
                format!("{} {} transport failed", request.method, path),
            )
        })
    }

    fn headers(&self) -> Vec<(String, String)> {
        let auth = if self.api_key.to_ascii_lowercase().starts_with("bearer ") {
            self.api_key.clone()
        } else {
            format!("Bearer {}", self.api_key)
        };
        vec![
            ("Authorization".into(), auth),
            ("Accept".into(), "application/json".into()),
            ("Content-Type".into(), "application/json".into()),
            ("User-Agent".into(), user_agent()),
        ]
    }
}

/// The check `authorize_capacity_work` runs before it sends anything.
pub fn require_work_authorization(value: &Value) -> Result<(), Error> {
    let invalid = |message: &str| Err(Error::new(ErrorKind::InvalidArgument, message));
    const REQUIRED: [&str; 4] = [
        "quote_id",
        "quote_hash",
        "idempotency_key",
        "confirm_max_cents",
    ];
    let Some(map) = value.as_object() else {
        return invalid(
            "Provide the exact quote identity, signature, maximum cents and request key",
        );
    };
    let missing = REQUIRED.iter().any(|k| !map.contains_key(*k));
    let extra = map
        .keys()
        .any(|k| !REQUIRED.contains(&k.as_str()) && k != "authority_id");
    if missing || extra {
        return invalid(
            "Provide the exact quote identity, signature, maximum cents and request key",
        );
    }
    match map["quote_id"].as_str() {
        Some(s) if !s.is_empty() => {}
        _ => return invalid("An explicit quote identity is required"),
    }
    match map["quote_hash"].as_str() {
        Some(s)
            if s.len() == 64
                && s.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) => {}
        _ => return invalid("The reviewed quote signature is required"),
    }
    match map["idempotency_key"].as_str() {
        Some(s) if (8..=128).contains(&s.chars().count()) => {}
        _ => return invalid("Use a stable request key containing 8 to 128 characters"),
    }
    if map["confirm_max_cents"].as_u64().is_none() {
        return invalid("The approved maximum must be an explicit nonnegative integer in cents");
    }
    match map.get("authority_id") {
        None | Some(Value::Null) | Some(Value::String(_)) => Ok(()),
        _ => invalid("Authority must be an explicit existing identifier"),
    }
}

fn parse(method: &str, path: &str, response: HttpResponse) -> Result<Value, Error> {
    let status = response.status;
    let ok = (200..300).contains(&status);
    let loaded: Value = match serde_json::from_str(&response.body) {
        Ok(v) => v,
        Err(_) => {
            let body = Value::String(response.body);
            let message = if ok {
                format!("{method} {path} returned invalid JSON")
            } else {
                format!("{method} {path} failed with HTTP {status}")
            };
            return Err(Error::api(message, status, body));
        }
    };
    if !ok {
        return Err(Error::api(
            format!("{method} {path} failed with HTTP {status}"),
            status,
            loaded,
        ));
    }
    if !loaded.is_object() {
        return Err(Error::api(
            format!("{method} {path} returned non-object JSON"),
            status,
            loaded,
        ));
    }
    let has_error = loaded.get("error").map(|e| !e.is_null()).unwrap_or(false);
    if has_error || !loaded.get("data").map(Value::is_object).unwrap_or(false) {
        return Err(Error::api(
            format!("{method} {path} returned an invalid success envelope"),
            status,
            loaded,
        ));
    }
    match loaded {
        Value::Object(mut map) => Ok(map.remove("data").unwrap_or(Value::Null)),
        _ => unreachable!(),
    }
}

fn retry_after(response: &HttpResponse) -> Option<Duration> {
    if response.status != 503 {
        return None;
    }
    let value = response.header("retry-after")?.trim();
    let seconds = if !value.is_empty() && value.bytes().all(|b| b.is_ascii_digit() || b == b'.') {
        value.parse::<f64>().ok()?
    } else {
        let at = parse_http_date(value)?;
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .ok()?
            .as_secs_f64();
        at as f64 - now
    };
    if (0.0..=RETRY_AFTER_MAX_SECS).contains(&seconds) {
        Some(Duration::from_secs_f64(seconds))
    } else {
        None
    }
}

/// Seconds since 1970 of an IMF-fixdate such as `Sun, 06 Nov 1994 08:49:37 GMT`.
fn parse_http_date(value: &str) -> Option<i64> {
    let parts: Vec<&str> = value.split_whitespace().collect();
    if parts.len() != 6 || parts[5] != "GMT" {
        return None;
    }
    let day: i64 = parts[1].parse().ok()?;
    const MONTHS: [&str; 12] = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    let month = MONTHS.iter().position(|m| *m == parts[2])? as i64 + 1;
    let year: i64 = parts[3].parse().ok()?;
    let hms: Vec<i64> = parts[4]
        .split(':')
        .map(|p| p.parse().ok())
        .collect::<Option<_>>()?;
    if hms.len() != 3 || !(1..=31).contains(&day) {
        return None;
    }
    // Days from civil date (Howard Hinnant's algorithm).
    let y = if month <= 2 { year - 1 } else { year };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (month + 9) % 12;
    let doy = (153 * mp + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe - 719_468;
    Some(days * 86_400 + hms[0] * 3600 + hms[1] * 60 + hms[2])
}

/// Percent-encodes everything but the unreserved characters of RFC 3986.
fn escape(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    for b in value.bytes() {
        if b.is_ascii_alphanumeric() || matches!(b, b'-' | b'.' | b'_' | b'~') {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

fn with_query(path: &str, params: &[(&str, Option<String>)]) -> String {
    let pairs: Vec<String> = params
        .iter()
        .filter_map(|(k, v)| v.as_ref().map(|v| format!("{}={}", escape(k), escape(v))))
        .collect();
    if pairs.is_empty() {
        path.to_owned()
    } else {
        format!("{}?{}", path, pairs.join("&"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn http_date_matches_known_instant() {
        assert_eq!(
            parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT"),
            Some(784_111_777)
        );
        assert_eq!(parse_http_date("not a date"), None);
    }

    #[test]
    fn escape_keeps_unreserved_only() {
        assert_eq!(escape("f 1/x~é"), "f%201%2Fx~%C3%A9");
    }
}
