package specstream

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

type seen struct {
	method, path, auth, agent, idempotency, contentType string
	query                                               url.Values
	body                                                string
}

func server(t *testing.T, replies ...func(http.ResponseWriter)) (*Client, *[]seen) {
	t.Helper()
	calls := &[]seen{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		*calls = append(*calls, seen{
			method: r.Method, path: r.URL.Path, auth: r.Header.Get("Authorization"),
			agent: r.Header.Get("User-Agent"), idempotency: r.Header.Get("Idempotency-Key"),
			contentType: r.Header.Get("Content-Type"), query: r.URL.Query(), body: string(body),
		})
		index := len(*calls) - 1
		if index >= len(replies) {
			index = len(replies) - 1
		}
		replies[index](w)
	}))
	t.Cleanup(srv.Close)
	client, err := NewClient("ss_test_key", WithBaseURL(srv.URL+"/"))
	if err != nil {
		t.Fatal(err)
	}
	client.sleep = func(context.Context, time.Duration) error { return nil }
	return client, calls
}

func reply(status int, body string, header ...string) func(http.ResponseWriter) {
	return func(w http.ResponseWriter) {
		for i := 0; i+1 < len(header); i += 2 {
			w.Header().Set(header[i], header[i+1])
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		fmt.Fprint(w, body)
	}
}

const searchReply = `{"data": {"id": null, "request_id": "req_1", "query": "population of Japan", "kind": "fact",
 "columns": [], "answer": {"value": "123 million", "page": "https://example.org/japan", "seen_at": null, "confirmed": true},
 "rows": [{"name": "Japan", "page": "https://example.org/japan", "snippet": "s", "probability": 0.9, "fields": {"population": "123 million"}, "sources": [0]}],
 "sources": [{"url": "https://example.org/japan", "title": "Japan", "site": "example.org", "snippet": "About 123 million", "cited": true, "published": null}],
 "passages": [{"url": "https://example.org/japan", "title": "Japan", "text": "The population is about 123 million."}],
 "handoff": null, "took_ms": 812, "price_usd": 0.005, "page": 1, "next_page": 2, "later_field": "kept"}}`

func TestNewClientNeedsAKey(t *testing.T) {
	if _, err := NewClient("  "); err == nil {
		t.Fatal("an empty key was accepted")
	}
}

func TestClientNeverPrintsItsKey(t *testing.T) {
	client, _ := NewClient("ss_live_secret")
	for _, text := range []string{fmt.Sprint(client), fmt.Sprintf("%v %+v %#v %s", client, client, client, client)} {
		if strings.Contains(text, "ss_live_secret") {
			t.Fatalf("the key is printed: %s", text)
		}
	}
}

func TestSearchSendsTheQueryAndReadsTheReply(t *testing.T) {
	client, calls := server(t, reply(200, searchReply))
	found, err := client.Search(context.Background(), "population of Japan", &SearchOptions{
		Num: 5, Page: 1, Passages: true, Speed: SpeedFast, Language: "en", Country: "US",
		IdempotencyKey: "call-1", Extra: url.Values{"engines": {"brave"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	call := (*calls)[0]
	if call.method != "GET" || call.path != "/v1/web-search" {
		t.Fatalf("called %s %s", call.method, call.path)
	}
	want := map[string]string{"q": "population of Japan", "num": "5", "page": "1", "passages": "true", "speed": "fast", "language": "en", "country": "US", "engines": "brave"}
	for name, value := range want {
		if call.query.Get(name) != value {
			t.Errorf("query %s = %q, want %q", name, call.query.Get(name), value)
		}
	}
	if len(call.query) != len(want) {
		t.Errorf("query holds more than was asked: %v", call.query)
	}
	if call.auth != "Bearer ss_test_key" || call.agent != "specstream-go/"+Version || call.idempotency != "call-1" {
		t.Errorf("headers: %+v", call)
	}
	if found.RequestID != "req_1" || found.Kind != "fact" || found.ID != "" || found.TookMS != 812 || found.PriceUSD != 0.005 || found.NextPage != 2 {
		t.Errorf("result: %+v", found)
	}
	if found.Answer == nil || found.Answer.Value != "123 million" || found.Answer.Confirmed == nil || !*found.Answer.Confirmed {
		t.Errorf("answer: %+v", found.Answer)
	}
	if len(found.Sources) != 1 || found.Sources[0].Site != "example.org" || !found.Sources[0].Cited || found.Sources[0].Published != "" {
		t.Errorf("sources: %+v", found.Sources)
	}
	if len(found.Rows) != 1 || found.Rows[0].Fields["population"] != "123 million" || found.Rows[0].Sources[0] != 0 {
		t.Errorf("rows: %+v", found.Rows)
	}
	if len(found.Passages) != 1 || !strings.Contains(found.Passages[0].Text, "123 million") || found.Handoff != nil {
		t.Errorf("passages: %+v handoff: %+v", found.Passages, found.Handoff)
	}
	var raw map[string]any
	if json.Unmarshal(found.Raw, &raw) != nil || raw["later_field"] != "kept" {
		t.Errorf("Raw does not hold the whole reply: %s", found.Raw)
	}
}

func TestSearchWithNoOptionsSendsOnlyTheQuery(t *testing.T) {
	client, calls := server(t, reply(200, searchReply))
	if _, err := client.Search(context.Background(), "q one", nil); err != nil {
		t.Fatal(err)
	}
	if query := (*calls)[0].query; len(query) != 1 || query.Get("q") != "q one" {
		t.Fatalf("query: %v", query)
	}
	if _, err := client.Search(context.Background(), " ", nil); err == nil || len(*calls) != 1 {
		t.Fatal("an empty query was sent")
	}
}

func TestExtractPostsThePagesAndReadsTheReply(t *testing.T) {
	client, calls := server(t, reply(200, `{"data": {"request_id": "req_2", "took_ms": 40, "price_usd": 0.0008, "results": [
 {"url": "https://example.com", "status": "ok", "title": "Example", "text": "# Example", "published": null, "read_from": "live", "captured_at": null},
 {"url": "https://example.com/none", "status": "not_found", "title": null, "text": "", "published": null}]}}`))
	pages, err := client.Extract(context.Background(), ExtractRequest{
		URLs: []string{"https://example.com", "https://example.com/none"}, Format: FormatText, IdempotencyKey: "call-2",
	})
	if err != nil {
		t.Fatal(err)
	}
	call := (*calls)[0]
	if call.method != "POST" || call.path != "/v1/extract" || call.contentType != "application/json" || call.idempotency != "call-2" {
		t.Fatalf("call: %+v", call)
	}
	if call.body != `{"urls":["https://example.com","https://example.com/none"],"format":"text"}` {
		t.Fatalf("body: %s", call.body)
	}
	if pages.RequestID != "req_2" || len(pages.Results) != 2 || pages.PriceUSD != 0.0008 {
		t.Fatalf("result: %+v", pages)
	}
	if first := pages.Results[0]; !first.OK() || first.Title != "Example" || first.Text != "# Example" || first.ReadFrom != "live" {
		t.Errorf("first page: %+v", first)
	}
	if second := pages.Results[1]; second.OK() || second.Status != "not_found" || second.Title != "" {
		t.Errorf("second page: %+v", second)
	}
}

func TestExtractSendsHTMLAndRefusesAnEmptyRequest(t *testing.T) {
	client, calls := server(t, reply(200, `{"data": {"request_id": "r", "results": [], "took_ms": 1, "price_usd": 0}}`))
	if _, err := client.Extract(context.Background(), ExtractRequest{}); err == nil || len(*calls) != 0 {
		t.Fatal("an empty request was sent")
	}
	if _, err := client.Extract(context.Background(), ExtractRequest{Pages: []HTMLPage{{HTML: "Hi", URL: "https://example.com/a"}}}); err != nil {
		t.Fatal(err)
	}
	if body := (*calls)[0].body; body != `{"pages":[{"html":"Hi","url":"https://example.com/a"}]}` {
		t.Fatalf("body: %s", body)
	}
}

func TestARefusalIsAnErrorWithTheAPIsCode(t *testing.T) {
	client, _ := server(t, reply(402, `{"error": {"code": "insufficient_credit", "message": "Add credit.", "details": {"balance_cents": 0}}}`))
	_, err := client.Search(context.Background(), "q", nil)
	var failure *Error
	if !errors.As(err, &failure) {
		t.Fatalf("not an *Error: %v", err)
	}
	if failure.Status != 402 || failure.Code != "insufficient_credit" || failure.Message != "Add credit." || failure.Details["balance_cents"] != float64(0) {
		t.Fatalf("error: %+v", failure)
	}
	if text := failure.Error(); text != "specstream: HTTP 402 insufficient_credit: Add credit." {
		t.Fatalf("message: %s", text)
	}
}

func TestAReplyThatIsNotTheEnvelopeIsAnError(t *testing.T) {
	for _, body := range []string{"<html>", `{"data": [1]}`, `{"other": {}}`} {
		client, _ := server(t, reply(200, body))
		_, err := client.Search(context.Background(), "q", nil)
		var failure *Error
		if !errors.As(err, &failure) || failure.Body != body {
			t.Fatalf("%s: %v", body, err)
		}
	}
	client, _ := server(t, reply(502, "<html>bad gateway</html>"))
	_, err := client.Extract(context.Background(), ExtractRequest{URLs: []string{"https://example.com"}})
	var failure *Error
	if !errors.As(err, &failure) || failure.Status != 502 || failure.Code != "" {
		t.Fatalf("502: %v", err)
	}
}

func TestA503WithAShortRetryAfterIsAskedOnceMore(t *testing.T) {
	client, calls := server(t, reply(503, `{"error": {"code": "busy", "message": "Busy."}}`, "Retry-After", "2"), reply(200, searchReply))
	var waited time.Duration
	client.sleep = func(_ context.Context, wait time.Duration) error { waited = wait; return nil }
	if _, err := client.Search(context.Background(), "q", nil); err != nil {
		t.Fatal(err)
	}
	if len(*calls) != 2 || waited != 2*time.Second {
		t.Fatalf("calls %d, waited %s", len(*calls), waited)
	}
}

func TestNothingElseIsRetried(t *testing.T) {
	cases := []func(http.ResponseWriter){
		reply(503, `{"error": {"code": "busy", "message": "Busy."}}`, "Retry-After", "60"),
		reply(503, `{"error": {"code": "busy", "message": "Busy."}}`),
		reply(500, `{"error": {"code": "internal", "message": "Failed."}}`, "Retry-After", "1"),
		reply(429, `{"error": {"code": "rate_limited", "message": "Slow down."}}`, "Retry-After", "1"),
	}
	for index, first := range cases {
		client, calls := server(t, first, reply(200, searchReply))
		if _, err := client.Search(context.Background(), "q", nil); err == nil || len(*calls) != 1 {
			t.Errorf("case %d: err %v after %d calls", index, err, len(*calls))
		}
	}
	// A second 503 is returned, not asked a third time.
	client, calls := server(t, reply(503, `{"error": {"code": "busy", "message": "Busy."}}`, "Retry-After", "1"))
	_, err := client.Search(context.Background(), "q", nil)
	var failure *Error
	if !errors.As(err, &failure) || failure.Status != 503 || len(*calls) != 2 {
		t.Fatalf("err %v after %d calls", err, len(*calls))
	}
}

func TestARedirectIsNotFollowed(t *testing.T) {
	other := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("the key went to another address: %s", r.Header.Get("Authorization"))
	}))
	defer other.Close()
	client, calls := server(t, reply(302, "", "Location", other.URL+"/v1/web-search"))
	_, err := client.Search(context.Background(), "q", nil)
	var failure *Error
	if !errors.As(err, &failure) || failure.Status != 302 || len(*calls) != 1 {
		t.Fatalf("err %v after %d calls", err, len(*calls))
	}
}

func TestACancelledContextStopsTheCall(t *testing.T) {
	client, _ := server(t, reply(200, searchReply))
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := client.Search(ctx, "q", nil); !errors.Is(err, context.Canceled) {
		t.Fatalf("err: %v", err)
	}
}

func TestATransportFailureDoesNotShowTheKey(t *testing.T) {
	client, _ := NewClient("ss_live_secret", WithBaseURL("http://127.0.0.1:1"), WithTimeout(2*time.Second))
	_, err := client.Search(context.Background(), "q", nil)
	if err == nil || strings.Contains(err.Error(), "ss_live_secret") {
		t.Fatalf("err: %v", err)
	}
}
