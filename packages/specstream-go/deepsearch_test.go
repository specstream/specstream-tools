package specstream

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func TestCompileSendsTheRequestAndReturnsData(t *testing.T) {
	client, calls := server(t, reply(200, `{"data":{"ast_hash":"abc"}}`))
	data, err := client.Compile(context.Background(), "vector databases", "")
	if err != nil {
		t.Fatal(err)
	}
	if data["ast_hash"] != "abc" {
		t.Fatalf("data: %v", data)
	}
	got := (*calls)[0]
	if got.method != "POST" || got.path != "/v1/parse" || got.auth != "Bearer ss_test_key" ||
		got.agent != "specstream-go/"+Version || got.contentType != "application/json" {
		t.Fatalf("call: %+v", got)
	}
	var body map[string]any
	if err := json.Unmarshal([]byte(got.body), &body); err != nil || body["q"] != "vector databases" || body["locale"] != "en-US" {
		t.Fatalf("body: %s", got.body)
	}
}

func TestDeepSearchPathsAndQueries(t *testing.T) {
	ctx := context.Background()
	cases := []struct {
		run  func(c *Client) (Data, error)
		want string
	}{
		{func(c *Client) (Data, error) { return c.EditSpec(ctx, Data{}, nil) }, "POST /v1/parse/from-chips"},
		{func(c *Client) (Data, error) { return c.SpecOptions(ctx, "a b/c") }, "GET /v1/spec-options/a b/c"},
		{func(c *Client) (Data, error) { return c.QuoteCapacityWork(ctx, Data{"ast_hash": "h"}) }, "POST /v1/capacity/quotes"},
		{func(c *Client) (Data, error) { return c.GetCapacityQuote(ctx, "q1") }, "GET /v1/capacity/quotes/q1"},
		{func(c *Client) (Data, error) { return c.GetCapacityRequest(ctx, "key-1234", "p1") }, "GET /v1/capacity/requests/key-1234?project_id=p1"},
		{func(c *Client) (Data, error) { return c.GetCapacityBalance(ctx, "") }, "GET /v1/capacity/balance"},
		{func(c *Client) (Data, error) { return c.GetFind(ctx, "f1") }, "GET /v1/finds/f1"},
		{func(c *Client) (Data, error) { return c.CancelFind(ctx, "f1") }, "POST /v1/finds/f1/cancel"},
		{func(c *Client) (Data, error) { return c.Rows(ctx, "f1", "cur", 0) }, "GET /v1/finds/f1/rows?cursor=cur&limit=100"},
		{func(c *Client) (Data, error) { return c.Export(ctx, "f1", "") }, "POST /v1/finds/f1/export"},
	}
	for _, tc := range cases {
		client, calls := server(t, reply(200, `{"data":{}}`))
		if _, err := tc.run(client); err != nil {
			t.Fatalf("%s: %v", tc.want, err)
		}
		got := (*calls)[0].method + " " + (*calls)[0].path
		if query := (*calls)[0].query.Encode(); query != "" {
			got += "?" + query
		}
		if got != tc.want {
			t.Errorf("got %q, want %q", got, tc.want)
		}
	}
}

func TestAuthorizeSendsNothingUnlessComplete(t *testing.T) {
	client, calls := server(t, reply(200, `{"data":{"find_id":"f1"}}`))
	good := Authorization{QuoteID: "q1", QuoteHash: strings.Repeat("a", 64), ConfirmMaxCents: 500, IdempotencyKey: "request-key-1"}
	bad := []Authorization{
		{QuoteHash: good.QuoteHash, ConfirmMaxCents: 500, IdempotencyKey: good.IdempotencyKey},
		{QuoteID: "q1", QuoteHash: "short", ConfirmMaxCents: 500, IdempotencyKey: good.IdempotencyKey},
		{QuoteID: "q1", QuoteHash: good.QuoteHash, ConfirmMaxCents: 500, IdempotencyKey: "short"},
		{QuoteID: "q1", QuoteHash: good.QuoteHash, ConfirmMaxCents: -1, IdempotencyKey: good.IdempotencyKey},
	}
	for i, a := range bad {
		_, err := client.AuthorizeCapacityWork(context.Background(), a)
		var refused *Error
		if !errors.As(err, &refused) || refused.Status != 0 || strings.Contains(err.Error(), "HTTP") {
			t.Errorf("case %d: %v", i, err)
		}
	}
	if len(*calls) != 0 {
		t.Fatalf("%d calls went out for incomplete approvals", len(*calls))
	}
	run, err := client.AuthorizeCapacityWork(context.Background(), good)
	if err != nil || run["find_id"] != "f1" {
		t.Fatalf("run: %v, %v", run, err)
	}
	var body map[string]any
	json.Unmarshal([]byte((*calls)[0].body), &body)
	if len(body) != 4 || body["confirm_max_cents"] != float64(500) || body["quote_id"] != "q1" || body["idempotency_key"] != "request-key-1" {
		t.Fatalf("body: %s", (*calls)[0].body)
	}
}

func TestEachRowFollowsTheCursorToItsEnd(t *testing.T) {
	client, calls := server(t,
		reply(200, `{"data":{"rows":[{"n":1},{"n":2}],"next_cursor":"c2"}}`),
		reply(200, `{"data":{"rows":[{"n":3}],"next_cursor":null}}`),
	)
	total := 0.0
	err := client.EachRow(context.Background(), "f1", func(row Data) error {
		total += row["n"].(float64)
		return nil
	})
	if err != nil || total != 6 || len(*calls) != 2 || (*calls)[1].query.Get("cursor") != "c2" {
		t.Fatalf("err %v, total %v, calls %+v", err, total, *calls)
	}
}

func TestEachRowStopsAtTheFirstError(t *testing.T) {
	client, calls := server(t, reply(500, `{"error":{"code":"internal"}}`))
	visited := 0
	err := client.EachRow(context.Background(), "f1", func(Data) error { visited++; return nil })
	if err == nil || visited != 0 || len(*calls) != 1 {
		t.Fatalf("err %v, visited %d, calls %d", err, visited, len(*calls))
	}

	client, calls = server(t, reply(200, `{"data":{"rows":[{"n":1},{"n":2}],"next_cursor":"c2"}}`))
	stop := errors.New("stop")
	if err := client.EachRow(context.Background(), "f1", func(Data) error { return stop }); err != stop || len(*calls) != 1 {
		t.Fatalf("err %v, calls %d", err, len(*calls))
	}
}

func TestRowsRefusesABadLimit(t *testing.T) {
	client, calls := server(t, reply(200, `{"data":{}}`))
	if _, err := client.Rows(context.Background(), "f1", "", 101); err == nil {
		t.Fatal("limit 101 was sent")
	}
	if len(*calls) != 0 {
		t.Fatal("a call went out")
	}
}

func TestADeepSearchRefusalCarriesStatusCodeAndDetails(t *testing.T) {
	client, _ := server(t, reply(402, `{"error":{"code":"insufficient_balance","message":"Add credit.","details":{"needed_cents":40}}}`))
	_, err := client.GetFind(context.Background(), "f1")
	var apiError *Error
	if !errors.As(err, &apiError) || apiError.Status != 402 || apiError.Code != "insufficient_balance" || apiError.Details["needed_cents"] != float64(40) {
		t.Fatalf("err: %#v", err)
	}
}
