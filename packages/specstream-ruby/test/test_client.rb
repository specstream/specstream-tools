# frozen_string_literal: true

require "minitest/autorun"
require "json"
require "specstream"

# A scripted transport: records each call and answers from a list.
class FakeTransport
  attr_reader :calls

  def initialize(*replies)
    @replies = replies
    @calls = []
  end

  def call(method, uri, headers, body)
    @calls << { method: method, uri: uri, headers: headers, body: body && JSON.parse(body) }
    reply = @replies.shift or raise "no scripted reply left"
    status, data, headers_out = reply
    [status, headers_out || {}, data.is_a?(String) ? data : JSON.generate(data)]
  end
end

QUOTE_HASH = "a" * 64

class ClientTest < Minitest::Test
  def client(transport, **opts)
    Specstream::Client.new("ss_test_key", transport: transport, **opts)
  end

  def test_requires_a_key
    assert_raises(Specstream::Error) { Specstream::Client.new("  ") }
    assert_raises(Specstream::Error) { Specstream::Client.new(nil) }
  end

  def test_inspect_hides_the_key
    c = Specstream::Client.new("ss_secret_value")
    refute_includes c.inspect, "ss_secret_value"
    refute_includes c.to_s, "ss_secret_value"
  end

  def test_compile_posts_the_request_with_bearer_key_and_user_agent
    t = FakeTransport.new([200, { "data" => { "ast_hash" => "h1", "ast" => {} } }])
    out = client(t).compile("Open-source vector databases", locale: "en-GB")
    assert_equal({ "ast_hash" => "h1", "ast" => {} }, out)
    call = t.calls.first
    assert_equal "POST", call[:method]
    assert_equal "https://api.specstream.ai/v1/parse", call[:uri].to_s
    assert_equal({ "q" => "Open-source vector databases", "locale" => "en-GB" }, call[:body])
    assert_equal "Bearer ss_test_key", call[:headers]["Authorization"]
    assert_equal "specstream-ruby/#{Specstream::VERSION}", call[:headers]["User-Agent"]
  end

  def test_base_url_override_keeps_its_path
    t = FakeTransport.new([200, { "data" => {} }])
    client(t, base_url: "http://127.0.0.1:9/api/").get_find("f 1/x")
    assert_equal "http://127.0.0.1:9/api/v1/finds/f%201%2Fx", t.calls.first[:uri].to_s
  end

  def test_quote_then_authorize_then_rows
    t = FakeTransport.new(
      [200, { "data" => { "quote_id" => "q1", "quote_hash" => QUOTE_HASH, "maximum_cents" => 500 } }],
      [200, { "data" => { "find_id" => "find_1" } }],
      [200, { "data" => { "rows" => [{ "id" => 1 }], "next_cursor" => nil } }]
    )
    c = client(t)
    offer = c.quote_capacity_work({ "ast_hash" => "h1", "operation" => "find", "requested_units" => 10 })
    run = c.authorize_capacity_work({ "quote_id" => offer["quote_id"], "quote_hash" => offer["quote_hash"],
                                      "confirm_max_cents" => 500, "idempotency_key" => "key-12345" })
    page = c.rows(run["find_id"], limit: 50)
    assert_equal [{ "id" => 1 }], page["rows"]
    assert_equal %w[/v1/capacity/quotes /v1/capacity/executions /v1/finds/find_1/rows], t.calls.map { |x| x[:uri].path }
    assert_equal "limit=50", t.calls.last[:uri].query
  end

  def test_authorize_refuses_before_sending_anything
    t = FakeTransport.new
    c = client(t)
    good = { "quote_id" => "q1", "quote_hash" => QUOTE_HASH, "confirm_max_cents" => 500, "idempotency_key" => "key-12345" }
    assert_raises(ArgumentError) { c.authorize_capacity_work(good.reject { |k, _| k == "confirm_max_cents" }) }
    assert_raises(ArgumentError) { c.authorize_capacity_work(good.merge("confirm_max_cents" => 5.0)) }
    assert_raises(ArgumentError) { c.authorize_capacity_work(good.merge("confirm_max_cents" => -1)) }
    assert_raises(ArgumentError) { c.authorize_capacity_work(good.merge("quote_hash" => "abc")) }
    assert_raises(ArgumentError) { c.authorize_capacity_work(good.merge("idempotency_key" => "short")) }
    assert_raises(ArgumentError) { c.authorize_capacity_work(good.merge("extra" => 1)) }
    assert_raises(ArgumentError) { c.authorize_capacity_work("not a hash") }
    assert_empty t.calls
  end

  def test_authorize_accepts_symbol_keys
    t = FakeTransport.new([200, { "data" => { "find_id" => "f" } }])
    client(t).authorize_capacity_work(quote_id: "q1", quote_hash: QUOTE_HASH, confirm_max_cents: 0,
                                      idempotency_key: "key-12345")
    assert_equal 0, t.calls.first[:body]["confirm_max_cents"]
  end

  def test_each_row_follows_next_cursor_until_null
    t = FakeTransport.new(
      [200, { "data" => { "rows" => [{ "n" => 1 }, { "n" => 2 }], "next_cursor" => "c2" } }],
      [200, { "data" => { "rows" => [{ "n" => 3 }], "next_cursor" => nil } }]
    )
    assert_equal [1, 2, 3], client(t).each_row("f1").map { |r| r["n"] }
    assert_equal "c2", URI.decode_www_form(t.calls.last[:uri].query).to_h["cursor"]
  end

  def test_rows_validates_limit_and_cursor
    c = client(FakeTransport.new)
    assert_raises(ArgumentError) { c.rows("f", limit: 0) }
    assert_raises(ArgumentError) { c.rows("f", limit: 101) }
    assert_raises(ArgumentError) { c.rows("f", cursor: "") }
  end

  def test_web_search_and_extract
    t = FakeTransport.new([200, { "data" => { "sources" => [] } }], [200, { "data" => { "results" => [] } }])
    c = client(t)
    c.web_search(q: "population of Japan", passages: true)
    c.extract_pages({ "urls" => ["https://example.com"] })
    assert_equal({ "q" => "population of Japan", "passages" => "true" }, URI.decode_www_form(t.calls[0][:uri].query).to_h)
    assert_equal "/v1/extract", t.calls[1][:uri].path
    assert_equal({ "urls" => ["https://example.com"] }, t.calls[1][:body])
  end

  def test_http_error_carries_code_and_details
    t = FakeTransport.new([402, { "error" => { "code" => "insufficient_balance", "details" => { "need" => 5 } } }])
    err = assert_raises(Specstream::Error) { client(t).get_capacity_balance }
    assert_equal 402, err.status
    assert_equal "insufficient_balance", err.code
    assert_equal({ "need" => 5 }, err.details)
  end

  def test_invalid_envelope_and_invalid_json_raise
    assert_raises(Specstream::Error) { client(FakeTransport.new([200, { "rows" => [] }])).get_find("f") }
    assert_raises(Specstream::Error) { client(FakeTransport.new([200, "<html>"])).get_find("f") }
    assert_raises(Specstream::Error) { client(FakeTransport.new([200, [1, 2]])).get_find("f") }
  end

  def test_one_retry_on_503_with_short_retry_after
    slept = []
    t = FakeTransport.new([503, { "error" => { "code" => "busy" } }, { "Retry-After" => "2" }],
                          [200, { "data" => { "ok" => true } }])
    out = client(t, sleeper: ->(s) { slept << s }).get_find("f")
    assert_equal({ "ok" => true }, out)
    assert_equal [2.0], slept
    assert_equal 2, t.calls.size
  end

  def test_no_retry_on_long_retry_after_or_other_errors
    t = FakeTransport.new([503, { "error" => {} }, { "retry-after" => ["60"] }])
    assert_raises(Specstream::Error) { client(t, sleeper: ->(_) { flunk "slept" }).get_find("f") }
    assert_equal 1, t.calls.size
    t2 = FakeTransport.new([500, { "error" => {} }, { "Retry-After" => "1" }])
    assert_raises(Specstream::Error) { client(t2, sleeper: ->(_) { flunk "slept" }).get_find("f") }
  end

  def test_transport_failure_becomes_error_without_the_key
    boom = ->(*_) { raise IOError, "Bearer ss_test_key leaked?" }
    err = assert_raises(Specstream::Error) { client(boom).get_find("f") }
    refute_includes err.message, "ss_test_key"
    assert_match(/transport failed/, err.message)
  end
end
