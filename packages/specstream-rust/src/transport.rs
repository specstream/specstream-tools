use std::io::Read;
use std::time::Duration;

/// One HTTP request, as the client hands it to a [`Transport`].
#[derive(Debug, Clone)]
pub struct HttpRequest {
    pub method: &'static str,
    pub url: String,
    pub headers: Vec<(String, String)>,
    pub body: Option<String>,
}

/// One HTTP answer. Any status is an answer, including 3xx, 4xx and 5xx.
#[derive(Debug, Clone, Default)]
pub struct HttpResponse {
    pub status: u16,
    pub headers: Vec<(String, String)>,
    pub body: String,
}

impl HttpResponse {
    /// The first value of a header, by case-insensitive name.
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }
}

/// Sends a request. The default is [`UreqTransport`]; tests and apps with their own
/// HTTP stack bring another. Return `Err` only when no answer came back; the text
/// is never shown with the key.
pub trait Transport: Send + Sync {
    fn send(&self, request: &HttpRequest) -> Result<HttpResponse, String>;
}

/// Largest reply body read, so a broken server cannot fill the host's memory.
const MAX_BODY_BYTES: u64 = 64 * 1024 * 1024;

/// The default transport: blocking HTTP with rustls. Redirects are not followed and
/// no proxy from the environment is used, so the key goes only to the base address.
pub struct UreqTransport {
    agent: ureq::Agent,
}

impl UreqTransport {
    pub fn new(timeout: Duration) -> Self {
        let agent = ureq::AgentBuilder::new()
            .redirects(0)
            .try_proxy_from_env(false)
            .timeout_connect(timeout.min(Duration::from_secs(30)))
            .timeout(timeout)
            .build();
        UreqTransport { agent }
    }
}

impl Transport for UreqTransport {
    fn send(&self, request: &HttpRequest) -> Result<HttpResponse, String> {
        let mut req = self.agent.request(request.method, &request.url);
        for (name, value) in &request.headers {
            req = req.set(name, value);
        }
        let result = match &request.body {
            Some(body) => req.send_string(body),
            None => req.call(),
        };
        let response = match result {
            Ok(response) | Err(ureq::Error::Status(_, response)) => response,
            Err(ureq::Error::Transport(err)) => return Err(format!("{:?}", err.kind())),
        };
        let status = response.status();
        let headers = response
            .headers_names()
            .into_iter()
            .filter_map(|name| {
                let value = response.header(&name)?.to_owned();
                Some((name, value))
            })
            .collect();
        let mut bytes = Vec::new();
        response
            .into_reader()
            .take(MAX_BODY_BYTES)
            .read_to_end(&mut bytes)
            .map_err(|err| format!("{:?}", err.kind()))?;
        Ok(HttpResponse {
            status,
            headers,
            body: String::from_utf8_lossy(&bytes).into_owned(),
        })
    }
}
