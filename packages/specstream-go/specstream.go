// Package specstream is the Go client for the SpecStream Deep Search API, Search API
// and Extract API.
//
// Deep Search reads a request in everyday words, prices it, and after a person
// approves the price, delivers every matching row with its sources:
//
//	reading, err := client.Compile(ctx, "Open-source vector databases on GitHub, with their license.", "")
//	offer, err := client.QuoteCapacityWork(ctx, specstream.Data{"ast_hash": reading["ast_hash"], "operation": "find", "requested_units": 25})
//
// Search answers a question from the live web and returns the results it read:
//
//	client, err := specstream.NewClient(os.Getenv("SPECSTREAM_API_KEY"))
//	if err != nil {
//		log.Fatal(err)
//	}
//	found, err := client.Search(ctx, "What is the population of Japan?", nil)
//
// Extract reads pages and returns their text:
//
//	pages, err := client.Extract(ctx, specstream.ExtractRequest{URLs: []string{"https://example.com"}})
//
// The package uses only the standard library. A Client is safe for use by several
// goroutines. Redirects are not followed and no proxy from the environment is used,
// so the key goes only to the base address.
package specstream

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	// Version is the version of this module.
	Version = "0.2.0"
	// DefaultBaseURL is the address of the SpecStream API.
	DefaultBaseURL = "https://api.specstream.ai"
	// DefaultTimeout is the time one call may take when the caller brings no HTTP client.
	DefaultTimeout = 150 * time.Second

	userAgent = "specstream-go/" + Version
	// A 503 that names a Retry-After of at most this long is asked once more.
	retryAfterMax = 10 * time.Second
	// No reply is read past this size.
	maxReplyBytes = 64 << 20
)

// Client calls the SpecStream API with one API key.
type Client struct {
	apiKey     string
	baseURL    string
	http       *http.Client
	ownsClient bool
	sleep      func(context.Context, time.Duration) error
}

// Option changes a Client at construction.
type Option func(*Client)

// WithBaseURL sends the calls to another address, for example a test server.
func WithBaseURL(baseURL string) Option {
	return func(c *Client) {
		if strings.TrimSpace(baseURL) != "" {
			c.baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
		}
	}
}

// WithHTTPClient replaces the HTTP client. The caller then owns its timeout,
// its proxy and its redirect rule.
func WithHTTPClient(httpClient *http.Client) Option {
	return func(c *Client) {
		if httpClient != nil {
			c.http = httpClient
			c.ownsClient = false
		}
	}
}

// WithTimeout sets the time one call may take with the default HTTP client.
// It has no effect together with WithHTTPClient.
func WithTimeout(timeout time.Duration) Option {
	return func(c *Client) {
		if timeout > 0 && c.ownsClient {
			c.http.Timeout = timeout
		}
	}
}

// NewClient returns a client for the API key. Create a key under Agents & API in
// the SpecStream workspace.
func NewClient(apiKey string, options ...Option) (*Client, error) {
	key := strings.TrimSpace(apiKey)
	if key == "" {
		return nil, errors.New("specstream: an API key is required (SPECSTREAM_API_KEY)")
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	client := &Client{
		apiKey:  key,
		baseURL: DefaultBaseURL,
		http: &http.Client{
			Timeout:   DefaultTimeout,
			Transport: transport,
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
		ownsClient: true,
		sleep:      sleepContext,
	}
	for _, option := range options {
		if option != nil {
			option(client)
		}
	}
	return client, nil
}

// String never shows the key.
func (c *Client) String() string {
	return fmt.Sprintf("specstream.Client{BaseURL: %q}", c.baseURL)
}

// GoString never shows the key.
func (c *Client) GoString() string { return c.String() }

// Error is returned for every call the API refuses and for every reply that is
// not the API's JSON. Read it with errors.As.
type Error struct {
	// Status is the HTTP status of the reply, or 0 when the client refused the call
	// before sending it.
	Status int
	// Code is the API's error code, for example "insufficient_credit".
	Code string
	// Message is the API's sentence about the failure.
	Message string
	// Details holds the API's facts about the failure, when it gives any.
	Details map[string]any
	// Body is the reply as received.
	Body string
}

func (e *Error) Error() string {
	if e.Status == 0 {
		// Refused here, before anything was sent.
		return "specstream: " + e.Message
	}
	text := fmt.Sprintf("specstream: HTTP %d", e.Status)
	if e.Code != "" {
		text += " " + e.Code
	}
	if e.Message != "" {
		text += ": " + e.Message
	}
	return text
}

// Speed values for SearchOptions.Speed.
const (
	SpeedDefault = "default"
	SpeedFast    = "fast"
)

// SearchOptions holds the optional parameters of a search. The zero value asks
// for the default search.
type SearchOptions struct {
	// Num is the number of results to return, 1 to 100.
	Num int
	// Page is the page of results to return, 1 to 10. Page 2 continues the list of page 1.
	Page int
	// Passages also returns the text of the top pages closest to the request.
	Passages bool
	// Speed is SpeedDefault or SpeedFast. The fast tier returns the engines' first
	// results at the fast price.
	Speed string
	// Language is the language of the results, for example "en".
	Language string
	// Country is the country of the results, for example "US".
	Country string
	// Safe is the safe-search rule.
	Safe string
	// News returns news items for the query, newest first.
	News bool
	// Images returns image results for the query.
	Images bool
	// IdempotencyKey is your id for this call, at most 128 characters. A call is
	// charged once per id, and the same id again is refused with 409.
	IdempotencyKey string
	// Extra holds any other query parameter of GET /v1/web-search.
	Extra url.Values
}

// SearchResult is the reply of a search.
type SearchResult struct {
	ID        string    `json:"id"`
	RequestID string    `json:"request_id"`
	Query     string    `json:"query"`
	Kind      string    `json:"kind"`
	Columns   []string  `json:"columns"`
	Answer    *Value    `json:"answer"`
	Rows      []Row     `json:"rows"`
	Sources   []Source  `json:"sources"`
	Passages  []Passage `json:"passages"`
	Handoff   *Handoff  `json:"handoff"`
	Page      int       `json:"page"`
	NextPage  int       `json:"next_page"`
	TookMS    int       `json:"took_ms"`
	PriceUSD  float64   `json:"price_usd"`
	// Raw is the whole reply, for fields this struct does not name.
	Raw json.RawMessage `json:"-"`
}

// Value is an answer with the page it comes from.
type Value struct {
	Value     string `json:"value"`
	Page      string `json:"page"`
	SeenAt    string `json:"seen_at"`
	Confirmed *bool  `json:"confirmed"`
}

// Row is one row of a list answer.
type Row struct {
	Name        string         `json:"name"`
	Page        string         `json:"page"`
	Snippet     string         `json:"snippet"`
	Probability float64        `json:"probability"`
	Fields      map[string]any `json:"fields"`
	Sources     []int          `json:"sources"`
}

// Source is one search result.
type Source struct {
	URL       string `json:"url"`
	Title     string `json:"title"`
	Site      string `json:"site"`
	Snippet   string `json:"snippet"`
	Cited     bool   `json:"cited"`
	Published string `json:"published"`
}

// Passage is text of a page close to the request.
type Passage struct {
	URL   string `json:"url"`
	Title string `json:"title"`
	Text  string `json:"text"`
}

// Handoff says how to get the full table when the request is a list.
type Handoff struct {
	Line          string          `json:"line"`
	Request       string          `json:"request"`
	RowsEstimated int             `json:"rows_estimated"`
	RowsBasis     string          `json:"rows_basis"`
	CountPage     string          `json:"count_page"`
	Next          json.RawMessage `json:"next"`
}

// Search calls the Search API, GET /v1/web-search. options may be nil.
func (c *Client) Search(ctx context.Context, query string, options *SearchOptions) (*SearchResult, error) {
	if strings.TrimSpace(query) == "" {
		return nil, errors.New("specstream: a search needs a query")
	}
	values := url.Values{}
	header := http.Header{}
	if options != nil {
		for name, list := range options.Extra {
			for _, value := range list {
				values.Add(name, value)
			}
		}
		if options.Num > 0 {
			values.Set("num", strconv.Itoa(options.Num))
		}
		if options.Page > 0 {
			values.Set("page", strconv.Itoa(options.Page))
		}
		if options.Passages {
			values.Set("passages", "true")
		}
		if options.News {
			values.Set("news", "true")
		}
		if options.Images {
			values.Set("images", "true")
		}
		for name, value := range map[string]string{
			"speed": options.Speed, "language": options.Language,
			"country": options.Country, "safe": options.Safe,
		} {
			if value != "" {
				values.Set(name, value)
			}
		}
		if options.IdempotencyKey != "" {
			header.Set("Idempotency-Key", options.IdempotencyKey)
		}
	}
	values.Set("q", query)
	raw, err := c.do(ctx, http.MethodGet, "/v1/web-search?"+values.Encode(), nil, header)
	if err != nil {
		return nil, err
	}
	result := &SearchResult{Raw: raw}
	if err := json.Unmarshal(raw, result); err != nil {
		return nil, &Error{Status: http.StatusOK, Message: "the reply is not a search result: " + err.Error(), Body: string(raw)}
	}
	return result, nil
}

// Format values for ExtractRequest.Format.
const (
	FormatMarkdown = "markdown"
	FormatText     = "text"
)

// ExtractRequest names the pages to read, at most 20 in one call: URLs to read
// live, HTML you already hold, or both.
type ExtractRequest struct {
	URLs  []string   `json:"urls,omitempty"`
	Pages []HTMLPage `json:"pages,omitempty"`
	// Format is FormatMarkdown (the default) or FormatText.
	Format string `json:"format,omitempty"`
	// IdempotencyKey is your id for this call, at most 128 characters.
	IdempotencyKey string `json:"-"`
}

// HTMLPage is HTML you already hold, with the address it came from when you know it.
type HTMLPage struct {
	HTML string `json:"html"`
	URL  string `json:"url,omitempty"`
}

// ExtractResult is the reply of an extract call.
type ExtractResult struct {
	RequestID string          `json:"request_id"`
	Results   []ExtractedPage `json:"results"`
	TookMS    int             `json:"took_ms"`
	PriceUSD  float64         `json:"price_usd"`
	// Raw is the whole reply, for fields this struct does not name.
	Raw json.RawMessage `json:"-"`
}

// ExtractedPage is one page that was read. Status is "ok" when the page has text;
// the other values are "blocked", "not_found", "empty", "unsupported",
// "invalid_url" and "failed".
type ExtractedPage struct {
	URL        string `json:"url"`
	Status     string `json:"status"`
	Title      string `json:"title"`
	Text       string `json:"text"`
	Published  string `json:"published"`
	ReadFrom   string `json:"read_from"`
	CapturedAt string `json:"captured_at"`
}

// OK reports whether the page was read and has text.
func (p ExtractedPage) OK() bool { return p.Status == "ok" }

// Extract calls the Extract API, POST /v1/extract.
func (c *Client) Extract(ctx context.Context, request ExtractRequest) (*ExtractResult, error) {
	if len(request.URLs) == 0 && len(request.Pages) == 0 {
		return nil, errors.New("specstream: an extract call needs at least one URL or one page of HTML")
	}
	body, err := json.Marshal(request)
	if err != nil {
		return nil, fmt.Errorf("specstream: the request cannot be written as JSON: %w", err)
	}
	header := http.Header{}
	if request.IdempotencyKey != "" {
		header.Set("Idempotency-Key", request.IdempotencyKey)
	}
	raw, err := c.do(ctx, http.MethodPost, "/v1/extract", body, header)
	if err != nil {
		return nil, err
	}
	result := &ExtractResult{Raw: raw}
	if err := json.Unmarshal(raw, result); err != nil {
		return nil, &Error{Status: http.StatusOK, Message: "the reply is not an extract result: " + err.Error(), Body: string(raw)}
	}
	return result, nil
}

// do sends one call and returns the object inside the reply's "data".
func (c *Client) do(ctx context.Context, method, path string, body []byte, header http.Header) (json.RawMessage, error) {
	status, replyHeader, text, err := c.send(ctx, method, path, body, header)
	if err != nil {
		return nil, err
	}
	if wait, ok := retryAfter(status, replyHeader); ok {
		// The server did nothing and names when to ask again: ask once more.
		if err := c.sleep(ctx, wait); err != nil {
			return nil, err
		}
		if status, _, text, err = c.send(ctx, method, path, body, header); err != nil {
			return nil, err
		}
	}
	if status < 200 || status > 299 {
		failure := &Error{Status: status, Body: string(text)}
		var envelope struct {
			Error struct {
				Code    string         `json:"code"`
				Message string         `json:"message"`
				Details map[string]any `json:"details"`
			} `json:"error"`
		}
		if json.Unmarshal(text, &envelope) == nil {
			failure.Code, failure.Message, failure.Details = envelope.Error.Code, envelope.Error.Message, envelope.Error.Details
		}
		return nil, failure
	}
	var envelope struct {
		Data json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(text, &envelope); err != nil || len(envelope.Data) == 0 || envelope.Data[0] != '{' {
		return nil, &Error{Status: status, Message: "the reply is not the API's {\"data\": {...}} object", Body: string(text)}
	}
	return envelope.Data, nil
}

func (c *Client) send(ctx context.Context, method, path string, body []byte, header http.Header) (int, http.Header, []byte, error) {
	route := strings.SplitN(path, "?", 2)[0]
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	request, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	if err != nil {
		return 0, nil, nil, fmt.Errorf("specstream: %s %s: the address is not valid", method, route)
	}
	for name, values := range header {
		request.Header[name] = values
	}
	authorization := c.apiKey
	if !strings.HasPrefix(strings.ToLower(authorization), "bearer ") {
		authorization = "Bearer " + authorization
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	request.Header.Set("User-Agent", userAgent)
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	reply, err := c.http.Do(request)
	if err != nil {
		if ctx.Err() != nil {
			return 0, nil, nil, ctx.Err()
		}
		// The transport's error holds the address, never the key.
		return 0, nil, nil, fmt.Errorf("specstream: %s %s did not reach the API: %w", method, route, err)
	}
	defer reply.Body.Close()
	text, err := io.ReadAll(io.LimitReader(reply.Body, maxReplyBytes))
	if err != nil {
		return 0, nil, nil, fmt.Errorf("specstream: %s %s: the reply stopped early: %w", method, route, err)
	}
	return reply.StatusCode, reply.Header, text, nil
}

func retryAfter(status int, header http.Header) (time.Duration, bool) {
	if status != http.StatusServiceUnavailable {
		return 0, false
	}
	value := strings.TrimSpace(header.Get("Retry-After"))
	if value == "" {
		return 0, false
	}
	var wait time.Duration
	if seconds, err := strconv.ParseFloat(value, 64); err == nil {
		wait = time.Duration(seconds * float64(time.Second))
	} else if at, err := http.ParseTime(value); err == nil {
		wait = time.Until(at)
	} else {
		return 0, false
	}
	if wait < 0 {
		wait = 0
	}
	if wait > retryAfterMax {
		return 0, false
	}
	return wait, true
}

func sleepContext(ctx context.Context, wait time.Duration) error {
	timer := time.NewTimer(wait)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
