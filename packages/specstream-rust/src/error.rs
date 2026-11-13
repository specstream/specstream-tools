use std::fmt;

use serde_json::{Map, Value};

/// What went wrong.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    /// The client was built without an API key, or with a base address it cannot use.
    Config,
    /// An argument was refused before anything was sent.
    InvalidArgument,
    /// The connection failed: no answer, a timeout or a reset.
    Transport,
    /// The API answered with an error status, or with a reply that is not its
    /// `{"data": {...}}` envelope.
    Api,
}

/// The error of every call. API errors carry the HTTP status and the API's own
/// `error.code` and `error.details`. No message ever holds the API key.
#[derive(Debug, Clone)]
pub struct Error {
    kind: ErrorKind,
    message: String,
    status: Option<u16>,
    body: Option<Value>,
    code: Option<String>,
    details: Map<String, Value>,
}

impl Error {
    pub(crate) fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Error {
            kind,
            message: message.into(),
            status: None,
            body: None,
            code: None,
            details: Map::new(),
        }
    }

    pub(crate) fn api(message: impl Into<String>, status: u16, body: Value) -> Self {
        let mut err = Error::new(ErrorKind::Api, message);
        err.status = Some(status);
        if let Some(error) = body.get("error").and_then(Value::as_object) {
            err.code = error.get("code").and_then(Value::as_str).map(str::to_owned);
            if let Some(details) = error.get("details").and_then(Value::as_object) {
                err.details = details.clone();
            }
        }
        err.body = Some(body);
        err
    }

    pub fn kind(&self) -> ErrorKind {
        self.kind
    }

    pub fn message(&self) -> &str {
        &self.message
    }

    /// The HTTP status, when the API answered.
    pub fn status(&self) -> Option<u16> {
        self.status
    }

    /// The reply body: parsed JSON, or a JSON string when the reply was not JSON.
    pub fn body(&self) -> Option<&Value> {
        self.body.as_ref()
    }

    /// The API's `error.code`, for example `insufficient_balance`.
    pub fn code(&self) -> Option<&str> {
        self.code.as_deref()
    }

    /// The API's `error.details`, empty when it sent none.
    pub fn details(&self) -> &Map<String, Value> {
        &self.details
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.code {
            Some(code) => write!(f, "{} ({})", self.message, code),
            None => f.write_str(&self.message),
        }
    }
}

impl std::error::Error for Error {}
