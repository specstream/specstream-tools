package specstream

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
)

// Data is the "data" object of a Deep Search reply.
type Data = map[string]any

// Compile reads a request in everyday words into a reading (the spec):
// POST /v1/parse. An empty locale means "en-US". Nothing is charged.
func (c *Client) Compile(ctx context.Context, q, locale string) (Data, error) {
	if locale == "" {
		locale = "en-US"
	}
	return c.call(ctx, http.MethodPost, "/v1/parse", Data{"q": q, "locale": locale})
}

// EditSpec changes a condition or a fact of a reading: POST /v1/parse/from-chips.
func (c *Client) EditSpec(ctx context.Context, ast any, operations []any) (Data, error) {
	if operations == nil {
		operations = []any{}
	}
	return c.call(ctx, http.MethodPost, "/v1/parse/from-chips", Data{"ast": ast, "operations": operations})
}

// SpecOptions lists the conditions and facts a kind of record supports:
// GET /v1/spec-options/{target}.
func (c *Client) SpecOptions(ctx context.Context, target string) (Data, error) {
	return c.call(ctx, http.MethodGet, "/v1/spec-options/"+url.PathEscape(target), nil)
}

// QuoteCapacityWork prices a reading before anything runs: POST /v1/capacity/quotes.
// Nothing is charged.
func (c *Client) QuoteCapacityWork(ctx context.Context, body Data) (Data, error) {
	return c.call(ctx, http.MethodPost, "/v1/capacity/quotes", body)
}

// GetCapacityQuote reads a quote again: GET /v1/capacity/quotes/{quote_id}.
func (c *Client) GetCapacityQuote(ctx context.Context, quoteID string) (Data, error) {
	return c.call(ctx, http.MethodGet, "/v1/capacity/quotes/"+url.PathEscape(quoteID), nil)
}

// Authorization approves one exact quote. Every field except AuthorityID is required.
type Authorization struct {
	// QuoteID and QuoteHash come from the quote a person reviewed.
	QuoteID   string
	QuoteHash string
	// ConfirmMaxCents is the maximum the person approved, in cents.
	ConfirmMaxCents int64
	// IdempotencyKey is a request key of 8 to 128 characters that you saved first.
	// The same key never starts, or charges, a second run.
	IdempotencyKey string
	// AuthorityID is optional.
	AuthorityID string
}

var quoteHashPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

// Validate reports what is missing or malformed, before anything is sent.
func (a Authorization) Validate() error {
	switch {
	case a.QuoteID == "":
		return errors.New("an explicit quote identity is required")
	case !quoteHashPattern.MatchString(a.QuoteHash):
		return errors.New("the reviewed quote signature is required")
	case len(a.IdempotencyKey) < 8 || len(a.IdempotencyKey) > 128:
		return errors.New("use a stable request key containing 8 to 128 characters")
	case a.ConfirmMaxCents < 0:
		return errors.New("the approved maximum must be a nonnegative integer in cents")
	}
	return nil
}

// AuthorizeCapacityWork approves the exact quote and starts the run:
// POST /v1/capacity/executions. It sends nothing unless the Authorization is valid.
func (c *Client) AuthorizeCapacityWork(ctx context.Context, a Authorization) (Data, error) {
	if err := a.Validate(); err != nil {
		return nil, &Error{Message: err.Error()}
	}
	body := Data{
		"quote_id":          a.QuoteID,
		"quote_hash":        a.QuoteHash,
		"confirm_max_cents": a.ConfirmMaxCents,
		"idempotency_key":   a.IdempotencyKey,
	}
	if a.AuthorityID != "" {
		body["authority_id"] = a.AuthorityID
	}
	return c.call(ctx, http.MethodPost, "/v1/capacity/executions", body)
}

// GetCapacityRequest returns the run already started with this request key:
// GET /v1/capacity/requests/{request_key}. projectID may be empty.
func (c *Client) GetCapacityRequest(ctx context.Context, requestKey, projectID string) (Data, error) {
	return c.call(ctx, http.MethodGet, withQuery("/v1/capacity/requests/"+url.PathEscape(requestKey), "project_id", projectID), nil)
}

// GetCapacityBalance reads the balance: GET /v1/capacity/balance. projectID may be empty.
func (c *Client) GetCapacityBalance(ctx context.Context, projectID string) (Data, error) {
	return c.call(ctx, http.MethodGet, withQuery("/v1/capacity/balance", "project_id", projectID), nil)
}

// GetFind shows the progress of a run: GET /v1/finds/{find_id}.
func (c *Client) GetFind(ctx context.Context, findID string) (Data, error) {
	return c.call(ctx, http.MethodGet, "/v1/finds/"+url.PathEscape(findID), nil)
}

// CancelFind stops a run: POST /v1/finds/{find_id}/cancel.
func (c *Client) CancelFind(ctx context.Context, findID string) (Data, error) {
	return c.call(ctx, http.MethodPost, "/v1/finds/"+url.PathEscape(findID)+"/cancel", Data{})
}

// Rows reads one page of delivered rows: GET /v1/finds/{find_id}/rows. cursor is
// empty for the first page and the reply's next_cursor after that; limit is 1 to
// 100, and 0 means 100.
func (c *Client) Rows(ctx context.Context, findID, cursor string, limit int) (Data, error) {
	if limit == 0 {
		limit = 100
	}
	if limit < 1 || limit > 100 {
		return nil, &Error{Message: "row page limit must be an integer from 1 to 100"}
	}
	if len(cursor) > 2048 {
		return nil, &Error{Message: "use the opaque next_cursor returned by this delivery"}
	}
	path := withQuery("/v1/finds/"+url.PathEscape(findID)+"/rows", "limit", strconv.Itoa(limit), "cursor", cursor)
	return c.call(ctx, http.MethodGet, path, nil)
}

// EachRow calls visit for every delivered row of a run, page after page until
// next_cursor is null. It stops at the first error, from the API or from visit,
// and returns it. Reading rows you own costs nothing.
//
//	err := client.EachRow(ctx, findID, func(row specstream.Data) error {
//		fmt.Println(row)
//		return nil
//	})
func (c *Client) EachRow(ctx context.Context, findID string, visit func(Data) error) error {
	cursor := ""
	for {
		page, err := c.Rows(ctx, findID, cursor, 100)
		if err != nil {
			return err
		}
		rows, _ := page["rows"].([]any)
		for _, item := range rows {
			row, _ := item.(map[string]any)
			if err := visit(row); err != nil {
				return err
			}
		}
		next, _ := page["next_cursor"].(string)
		if next == "" {
			return nil
		}
		cursor = next
	}
}

// Export makes a file of a run's rows: POST /v1/finds/{find_id}/export. format is
// csv, xlsx, json or html; empty means csv.
func (c *Client) Export(ctx context.Context, findID, format string) (Data, error) {
	if format == "" {
		format = "csv"
	}
	return c.call(ctx, http.MethodPost, "/v1/finds/"+url.PathEscape(findID)+"/export", Data{"format": format})
}

// call sends one Deep Search call and returns the reply's "data" object as a map.
func (c *Client) call(ctx context.Context, method, path string, body any) (Data, error) {
	var payload []byte
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return nil, &Error{Message: "the request cannot be sent as JSON: " + err.Error()}
		}
		payload = encoded
	}
	raw, err := c.do(ctx, method, path, payload, nil)
	if err != nil {
		return nil, err
	}
	var data Data
	if err := json.Unmarshal(raw, &data); err != nil {
		return nil, &Error{Status: http.StatusOK, Message: "the reply is not a JSON object: " + err.Error(), Body: string(raw)}
	}
	return data, nil
}

// withQuery adds the name and value pairs whose value is not empty.
func withQuery(path string, pairs ...string) string {
	query := url.Values{}
	for i := 0; i+1 < len(pairs); i += 2 {
		if pairs[i+1] != "" {
			query.Set(pairs[i], pairs[i+1])
		}
	}
	if len(query) == 0 {
		return path
	}
	return path + "?" + query.Encode()
}
