//! The client against a scripted transport: no network, no key.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::{json, Value};
use specstream::{Client, ErrorKind, HttpRequest, HttpResponse, Transport, WebSearch};

/// A scripted answer: status, JSON body (a JSON string is sent as raw text) and headers.
type Reply = (u16, Value, Vec<(&'static str, &'static str)>);

#[derive(Clone, Default)]
struct Fake {
    replies: Arc<Mutex<VecDeque<Result<HttpResponse, String>>>>,
    calls: Arc<Mutex<Vec<HttpRequest>>>,
}

impl Fake {
    fn with(replies: Vec<Reply>) -> Self {
        let fake = Fake::default();
        for (status, body, headers) in replies {
            let body = match body {
                Value::String(s) => s,
                other => other.to_string(),
            };
            fake.replies.lock().unwrap().push_back(Ok(HttpResponse {
                status,
                headers: headers
                    .into_iter()
                    .map(|(k, v)| (k.to_owned(), v.to_owned()))
                    .collect(),
                body,
            }));
        }
        fake
    }

    fn calls(&self) -> Vec<HttpRequest> {
        self.calls.lock().unwrap().clone()
    }
}

impl Transport for Fake {
    fn send(&self, request: &HttpRequest) -> Result<HttpResponse, String> {
        self.calls.lock().unwrap().push(request.clone());
        self.replies
            .lock()
            .unwrap()
            .pop_front()
            .expect("no scripted reply left")
    }
}

fn client(fake: &Fake) -> Client {
    Client::builder("ss_test_key")
        .transport(fake.clone())
        .sleeper(|_| panic!("slept"))
        .build()
        .unwrap()
}

fn header<'a>(req: &'a HttpRequest, name: &str) -> &'a str {
    req.headers
        .iter()
        .find(|(k, _)| k == name)
        .map(|(_, v)| v.as_str())
        .unwrap()
}

fn body(req: &HttpRequest) -> Value {
    serde_json::from_str(req.body.as_deref().unwrap()).unwrap()
}

const QUOTE_HASH: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

#[test]
fn requires_a_key() {
    assert_eq!(Client::new("  ").unwrap_err().kind(), ErrorKind::Config);
    assert_eq!(Client::new("").unwrap_err().kind(), ErrorKind::Config);
    assert_eq!(
        Client::builder("k")
            .base_url("ftp://x")
            .build()
            .unwrap_err()
            .kind(),
        ErrorKind::Config
    );
}

#[test]
fn debug_hides_the_key() {
    let c = Client::new("ss_secret_value").unwrap();
    assert!(!format!("{c:?}").contains("ss_secret_value"));
}

#[test]
fn compile_posts_the_request_with_bearer_key_and_user_agent() {
    let fake = Fake::with(vec![(
        200,
        json!({"data": {"ast_hash": "h1", "ast": {}}}),
        vec![],
    )]);
    let out = client(&fake)
        .compile_with_locale("Open-source vector databases", "en-GB")
        .unwrap();
    assert_eq!(out, json!({"ast_hash": "h1", "ast": {}}));
    let call = &fake.calls()[0];
    assert_eq!(call.method, "POST");
    assert_eq!(call.url, "https://api.specstream.ai/v1/parse");
    assert_eq!(
        body(call),
        json!({"q": "Open-source vector databases", "locale": "en-GB"})
    );
    assert_eq!(header(call, "Authorization"), "Bearer ss_test_key");
    assert_eq!(
        header(call, "User-Agent"),
        format!("specstream-rust/{}", specstream::VERSION)
    );
}

#[test]
fn base_url_override_keeps_its_path_and_ids_are_escaped() {
    let fake = Fake::with(vec![(200, json!({"data": {}}), vec![])]);
    let c = Client::builder("k")
        .base_url("http://127.0.0.1:9/api/")
        .transport(fake.clone())
        .build()
        .unwrap();
    c.get_find("f 1/x").unwrap();
    assert_eq!(
        fake.calls()[0].url,
        "http://127.0.0.1:9/api/v1/finds/f%201%2Fx"
    );
}

#[test]
fn quote_then_authorize_then_rows() {
    let fake = Fake::with(vec![
        (
            200,
            json!({"data": {"quote_id": "q1", "quote_hash": QUOTE_HASH, "maximum_cents": 500}}),
            vec![],
        ),
        (200, json!({"data": {"find_id": "find_1"}}), vec![]),
        (
            200,
            json!({"data": {"rows": [{"id": 1}], "next_cursor": null}}),
            vec![],
        ),
    ]);
    let c = client(&fake);
    let offer = c
        .quote_capacity_work(&json!({"ast_hash": "h1", "operation": "find", "requested_units": 10}))
        .unwrap();
    let run = c
        .authorize_capacity_work(&json!({
            "quote_id": offer["quote_id"], "quote_hash": offer["quote_hash"],
            "confirm_max_cents": 500, "idempotency_key": "key-12345"
        }))
        .unwrap();
    let page = c.rows(run["find_id"].as_str().unwrap(), None, 50).unwrap();
    assert_eq!(page["rows"], json!([{"id": 1}]));
    let urls: Vec<String> = fake.calls().iter().map(|r| r.url.clone()).collect();
    assert_eq!(
        urls,
        vec![
            "https://api.specstream.ai/v1/capacity/quotes",
            "https://api.specstream.ai/v1/capacity/executions",
            "https://api.specstream.ai/v1/finds/find_1/rows?limit=50",
        ]
    );
}

#[test]
fn authorize_refuses_before_sending_anything() {
    let fake = Fake::default();
    let c = client(&fake);
    let good = json!({"quote_id": "q1", "quote_hash": QUOTE_HASH, "confirm_max_cents": 500, "idempotency_key": "key-12345"});
    let with = |k: &str, v: Value| {
        let mut b = good.clone();
        b[k] = v;
        b
    };
    let mut missing = good.clone();
    missing.as_object_mut().unwrap().remove("confirm_max_cents");
    for bad in [
        missing,
        with("confirm_max_cents", json!(5.0)),
        with("confirm_max_cents", json!(-1)),
        with("quote_hash", json!("abc")),
        with("idempotency_key", json!("short")),
        with("extra", json!(1)),
        with("authority_id", json!(7)),
        json!("not an object"),
    ] {
        let err = c.authorize_capacity_work(&bad).unwrap_err();
        assert_eq!(err.kind(), ErrorKind::InvalidArgument, "{bad}");
    }
    assert!(fake.calls().is_empty());
}

#[test]
fn all_rows_follows_next_cursor_until_null() {
    let fake = Fake::with(vec![
        (
            200,
            json!({"data": {"rows": [{"n": 1}, {"n": 2}], "next_cursor": "c 2"}}),
            vec![],
        ),
        (
            200,
            json!({"data": {"rows": [{"n": 3}], "next_cursor": null}}),
            vec![],
        ),
    ]);
    let rows = client(&fake).all_rows("f1").unwrap();
    let ns: Vec<i64> = rows.iter().map(|r| r["n"].as_i64().unwrap()).collect();
    assert_eq!(ns, vec![1, 2, 3]);
    assert!(fake.calls()[1]
        .url
        .ends_with("/v1/finds/f1/rows?limit=100&cursor=c%202"));
}

#[test]
fn rows_validates_limit_and_cursor() {
    let fake = Fake::default();
    let c = client(&fake);
    assert_eq!(
        c.rows("f", None, 0).unwrap_err().kind(),
        ErrorKind::InvalidArgument
    );
    assert_eq!(
        c.rows("f", None, 101).unwrap_err().kind(),
        ErrorKind::InvalidArgument
    );
    assert_eq!(
        c.rows("f", Some(""), 10).unwrap_err().kind(),
        ErrorKind::InvalidArgument
    );
    assert!(fake.calls().is_empty());
}

#[test]
fn web_search_and_extract() {
    let fake = Fake::with(vec![
        (200, json!({"data": {"sources": []}}), vec![]),
        (200, json!({"data": {"results": []}}), vec![]),
    ]);
    let c = client(&fake);
    let mut search = WebSearch::new("population of Japan");
    search.passages = Some(true);
    search.speed = Some("fast".into());
    c.web_search(&search).unwrap();
    c.extract_pages(&json!({"urls": ["https://example.com"]}))
        .unwrap();
    let calls = fake.calls();
    assert_eq!(calls[0].method, "GET");
    assert_eq!(calls[0].url, "https://api.specstream.ai/v1/web-search?q=population%20of%20Japan&passages=true&speed=fast");
    assert!(calls[0].body.is_none());
    assert_eq!(calls[1].url, "https://api.specstream.ai/v1/extract");
    assert_eq!(body(&calls[1]), json!({"urls": ["https://example.com"]}));
}

#[test]
fn http_error_carries_code_and_details() {
    let fake = Fake::with(vec![(
        402,
        json!({"error": {"code": "insufficient_balance", "details": {"need": 5}}}),
        vec![],
    )]);
    let err = client(&fake).get_capacity_balance(None).unwrap_err();
    assert_eq!(err.kind(), ErrorKind::Api);
    assert_eq!(err.status(), Some(402));
    assert_eq!(err.code(), Some("insufficient_balance"));
    assert_eq!(err.details().get("need"), Some(&json!(5)));
}

#[test]
fn invalid_envelope_and_invalid_json_are_errors() {
    for reply in [
        json!({"rows": []}),
        json!("<html>"),
        json!([1, 2]),
        json!({"data": {}, "error": {"code": "x"}}),
    ] {
        let fake = Fake::with(vec![(200, reply.clone(), vec![])]);
        let err = client(&fake).get_find("f").unwrap_err();
        assert_eq!(err.kind(), ErrorKind::Api, "{reply}");
    }
}

#[test]
fn one_retry_on_503_with_short_retry_after() {
    let slept = Arc::new(Mutex::new(Vec::new()));
    let seen = slept.clone();
    let fake = Fake::with(vec![
        (
            503,
            json!({"error": {"code": "busy"}}),
            vec![("Retry-After", "2")],
        ),
        (200, json!({"data": {"ok": true}}), vec![]),
    ]);
    let c = Client::builder("k")
        .transport(fake.clone())
        .sleeper(move |d| seen.lock().unwrap().push(d))
        .build()
        .unwrap();
    assert_eq!(c.get_find("f").unwrap(), json!({"ok": true}));
    assert_eq!(*slept.lock().unwrap(), vec![Duration::from_secs(2)]);
    assert_eq!(fake.calls().len(), 2);
}

#[test]
fn no_retry_on_long_retry_after_or_other_errors() {
    let fake = Fake::with(vec![(
        503,
        json!({"error": {}}),
        vec![("retry-after", "60")],
    )]);
    assert_eq!(client(&fake).get_find("f").unwrap_err().status(), Some(503));
    assert_eq!(fake.calls().len(), 1);
    let fake = Fake::with(vec![(
        500,
        json!({"error": {}}),
        vec![("Retry-After", "1")],
    )]);
    assert_eq!(client(&fake).get_find("f").unwrap_err().status(), Some(500));
    assert_eq!(fake.calls().len(), 1);
}

#[test]
fn transport_failure_becomes_error_without_the_key() {
    let fake = Fake::default();
    fake.replies
        .lock()
        .unwrap()
        .push_back(Err("Bearer ss_test_key leaked?".into()));
    let err = client(&fake).get_find("f").unwrap_err();
    assert_eq!(err.kind(), ErrorKind::Transport);
    assert!(!err.to_string().contains("ss_test_key"));
    assert!(err.to_string().contains("transport failed"));
}
