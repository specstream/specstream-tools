//! The real HTTP transport against a one-shot local server (no network, no key).

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::thread;
use std::time::Duration;

use serde_json::{json, Value};
use specstream::{Client, ErrorKind};

struct Seen {
    request_line: String,
    headers: Vec<(String, String)>,
    body: String,
}

fn serve(
    status_line: &'static str,
    body: String,
    extra: &'static str,
) -> (String, thread::JoinHandle<Seen>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let handle = thread::spawn(move || {
        let (stream, _) = listener.accept().unwrap();
        let mut reader = BufReader::new(stream.try_clone().unwrap());
        let mut request_line = String::new();
        reader.read_line(&mut request_line).unwrap();
        let mut headers = Vec::new();
        loop {
            let mut line = String::new();
            reader.read_line(&mut line).unwrap();
            if line == "\r\n" || line.is_empty() {
                break;
            }
            let (k, v) = line.split_once(':').unwrap();
            headers.push((k.to_ascii_lowercase(), v.trim().to_owned()));
        }
        let length: usize = headers
            .iter()
            .find(|(k, _)| k == "content-length")
            .map(|(_, v)| v.parse().unwrap())
            .unwrap_or(0);
        let mut buf = vec![0; length];
        reader.read_exact(&mut buf).unwrap();
        let mut stream = stream;
        write!(
            stream,
            "HTTP/1.1 {status_line}\r\nContent-Type: application/json\r\n{extra}Content-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.len()
        )
        .unwrap();
        Seen {
            request_line: request_line.trim().to_owned(),
            headers,
            body: String::from_utf8(buf).unwrap(),
        }
    });
    (base, handle)
}

fn client(base: &str) -> Client {
    Client::builder("ss_k")
        .base_url(base)
        .timeout(Duration::from_secs(5))
        .build()
        .unwrap()
}

#[test]
fn post_goes_over_http_with_json_body() {
    let (base, handle) = serve("200 OK", json!({"data": {"ast_hash": "h"}}).to_string(), "");
    let out = client(&base).compile("tools").unwrap();
    assert_eq!(out["ast_hash"], "h");
    let seen = handle.join().unwrap();
    assert_eq!(seen.request_line, "POST /v1/parse HTTP/1.1");
    let auth = seen
        .headers
        .iter()
        .find(|(k, _)| k == "authorization")
        .unwrap();
    assert_eq!(auth.1, "Bearer ss_k");
    let sent: Value = serde_json::from_str(&seen.body).unwrap();
    assert_eq!(sent, json!({"q": "tools", "locale": "en-US"}));
}

#[test]
fn api_error_status_is_read() {
    let (base, handle) = serve(
        "401 Unauthorized",
        json!({"error": {"code": "unauthorized"}}).to_string(),
        "",
    );
    let err = client(&base).get_find("f").unwrap_err();
    handle.join().unwrap();
    assert_eq!(err.status(), Some(401));
    assert_eq!(err.code(), Some("unauthorized"));
}

#[test]
fn redirect_is_not_followed() {
    let (base, handle) = serve(
        "302 Found",
        "{}".into(),
        "Location: http://example.com/\r\n",
    );
    let err = client(&base).get_find("f").unwrap_err();
    handle.join().unwrap();
    assert_eq!(err.status(), Some(302));
}

#[test]
fn closed_port_is_a_transport_error() {
    let port = TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port();
    let err = client(&format!("http://127.0.0.1:{port}"))
        .get_find("f")
        .unwrap_err();
    assert_eq!(err.kind(), ErrorKind::Transport);
    assert!(err.to_string().contains("transport failed"));
}
