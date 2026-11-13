# frozen_string_literal: true

require "minitest/autorun"
require "json"
require "openssl"
require "specstream"

# A scripted transport: records each call and answers from a list.
class MonitorTransport
  attr_reader :calls

  def initialize(*replies)
    @replies = replies
    @calls = []
  end

  def call(method, uri, headers, body)
    @calls << { method: method, uri: uri, headers: headers, body: body && JSON.parse(body) }
    reply = @replies.shift or raise "no scripted reply left"
    status, data = reply
    [status, {}, JSON.generate(data)]
  end
end

AST_HASH = "b" * 64
NOW = Time.utc(2026, 11, 12, 15, 42, 7)

SCHEDULE = {
  "schedule_id" => "sch_1",
  "state" => "active",
  "version" => 3,
  "cadence_seconds" => 604_800,
  "per_run_cents" => 200,
  "period_cents" => 800,
  "next_due_at" => "2026-11-19T15:00:00Z",
  "valid_until" => "2027-11-19T15:00:00Z",
  "scope" => { "parent_find_id" => "fnd_1", "operation" => "refresh" }
}.freeze

class MonitorsTest < Minitest::Test
  def client(transport)
    Specstream::Client.new("ss_test_key", transport: transport, clock: -> { NOW })
  end

  def test_monitor_list_prices_one_check_then_saves_the_schedule
    t = MonitorTransport.new(
      [200, { "data" => { "find_id" => "fnd_1", "ast_hash" => AST_HASH, "requested_count" => 40, "project_id" => "prj_1" } }],
      [200, { "data" => { "quote_id" => "q1", "quote_hash" => "a" * 64, "maximum_cents" => 150 } }],
      [201, { "data" => SCHEDULE }]
    )
    monitor = client(t).monitor_list("fnd_1", every: "week", max_price_per_run_usd: 2, max_price_per_month_usd: 8)

    assert_equal %w[GET POST POST], t.calls.map { |c| c[:method] }
    assert_equal %w[/v1/finds/fnd_1 /v1/capacity/quotes /v1/capacity/schedules], t.calls.map { |c| c[:uri].path }
    scope = { "ast_hash" => AST_HASH, "operation" => "refresh", "parent_find_id" => "fnd_1",
              "requested_units" => 40, "project_id" => "prj_1" }
    assert_equal scope, t.calls[1][:body]
    saved = t.calls[2][:body]
    assert_equal scope, saved["scope"]
    assert_equal 604_800, saved["cadence_seconds"]
    assert_equal 200, saved["per_run_cents"]
    assert_equal 800, saved["period_cents"]
    assert_equal "2026-11-19T15:00:00Z", saved["first_due_at"]
    assert_equal "2027-11-19T15:00:00Z", saved["valid_until"]
    assert_match(/\Aruby-monitor-[0-9a-f]{32}\z/, saved["idempotency_key"])

    assert_equal "saved", monitor["status"]
    assert_equal "sch_1", monitor["monitor_id"]
    assert_equal "fnd_1", monitor["list_id"]
    assert_equal 2.0, monitor["max_price_per_run_usd"]
    assert_equal 8.0, monitor["max_price_per_month_usd"]
    assert_equal 3, monitor["version"]
  end

  def test_monitor_list_retry_in_the_same_hour_sends_the_same_key
    keys = 2.times.map do
      t = MonitorTransport.new(
        [200, { "data" => { "ast_hash" => AST_HASH } }],
        [200, { "data" => { "maximum_cents" => 10 } }],
        [201, { "data" => SCHEDULE }]
      )
      client(t).monitor_list("fnd_1", max_price_per_run_usd: 1)
      t.calls.last[:body]["idempotency_key"]
    end
    assert_equal keys.first, keys.last
  end

  def test_monitor_list_default_month_limit_covers_31_days_of_checks
    t = MonitorTransport.new(
      [200, { "data" => { "ast_hash" => AST_HASH } }],
      [200, { "data" => { "maximum_cents" => 10 } }],
      [201, { "data" => SCHEDULE }]
    )
    client(t).monitor_list("fnd_1", max_price_per_run_usd: 0.5)
    body = t.calls.last[:body]
    assert_equal 86_400, body["cadence_seconds"]
    assert_equal 50 * 31, body["period_cents"]
    assert_equal 25, body["scope"]["requested_units"]
    assert_equal "2026-11-13T15:00:00Z", body["first_due_at"]
  end

  def test_monitor_list_over_the_maximum_saves_nothing
    t = MonitorTransport.new(
      [200, { "data" => { "ast_hash" => AST_HASH } }],
      [200, { "data" => { "maximum_cents" => 450 } }]
    )
    out = client(t).monitor_list("fnd_1", max_price_per_run_usd: 2)
    assert_equal "over_maximum", out["status"]
    assert_equal 4.5, out["maximum_price_usd"]
    assert_includes out["message"], "$4.50"
    assert_equal 2, t.calls.size
  end

  def test_monitor_list_refuses_bad_limits_before_any_call
    t = MonitorTransport.new
    c = client(t)
    assert_raises(ArgumentError) { c.monitor_list("", max_price_per_run_usd: 1) }
    assert_raises(ArgumentError) { c.monitor_list("fnd_1", max_price_per_run_usd: 0) }
    assert_raises(ArgumentError) { c.monitor_list("fnd_1", max_price_per_run_usd: "abc") }
    assert_raises(ArgumentError) { c.monitor_list("fnd_1", max_price_per_run_usd: 1, every: "minute") }
    assert_raises(ArgumentError) { c.monitor_list("fnd_1", max_price_per_run_usd: 2, max_price_per_month_usd: 1) }
    assert_raises(ArgumentError) do
      c.monitor_list("fnd_1", max_price_per_run_usd: 1, first_run_at: "2027-01-02T00:00:00Z", ends_at: "2027-01-01T00:00:00Z")
    end
    assert_empty t.calls
  end

  def test_monitors_follow_next_after
    t = MonitorTransport.new(
      [200, { "data" => { "schedules" => [SCHEDULE], "next_after" => "sch_1" } }],
      [200, { "data" => { "schedules" => [SCHEDULE.merge("schedule_id" => "sch_2")], "next_after" => nil } }]
    )
    assert_equal %w[sch_1 sch_2], client(t).monitors.map { |m| m["monitor_id"] }
    assert_equal({ "limit" => "100" }, URI.decode_www_form(t.calls[0][:uri].query).to_h)
    assert_equal({ "after" => "sch_1", "limit" => "100" }, URI.decode_www_form(t.calls[1][:uri].query).to_h)
  end

  def test_monitor_runs_reads_occurrences
    t = MonitorTransport.new(
      [200, { "data" => { "occurrences" => [
        { "due_at" => "2026-11-12T15:00:00Z", "status" => "completed", "find_id" => "fnd_9" },
        { "due_at" => "2026-11-05T15:00:00Z", "status" => "blocked", "reason" => "period_limit" }
      ] } }]
    )
    runs = client(t).monitor_runs("sch_1", limit: 500)
    assert_equal "/v1/capacity/schedules/sch_1/occurrences", t.calls.first[:uri].path
    assert_equal "limit=100", t.calls.first[:uri].query
    assert_equal "fnd_9", runs[0]["list_id"]
    assert_equal "period_limit", runs[1]["reason"]
    assert_nil runs[1]["list_id"]
  end

  def test_run_monitor_now
    t = MonitorTransport.new([200, { "data" => { "find_id" => "fnd_7", "started_at" => "2026-11-12T15:42:07Z" } }])
    out = client(t).run_monitor_now("sch_1")
    assert_equal({ "monitor_id" => "sch_1", "list_id" => "fnd_7", "started_at" => "2026-11-12T15:42:07Z" }, out)
    assert_equal "POST", t.calls.first[:method]
    assert_equal "/v1/capacity/schedules/sch_1/run", t.calls.first[:uri].path
  end

  def test_pause_resume_delete_send_the_current_version
    %w[pause_monitor resume_monitor delete_monitor].zip(%w[paused active deleted]).each do |call, state|
      t = MonitorTransport.new(
        [200, { "data" => { "schedules" => [SCHEDULE], "next_after" => nil } }],
        [200, { "data" => SCHEDULE.merge("state" => state, "version" => 4) }]
      )
      out = client(t).public_send(call, "sch_1")
      assert_equal "PATCH", t.calls.last[:method]
      assert_equal "/v1/capacity/schedules/sch_1", t.calls.last[:uri].path
      assert_equal({ "expected_version" => 3, "state" => state }, t.calls.last[:body])
      assert_equal state, out["state"]
    end
  end

  def test_unknown_monitor_raises_without_a_write
    t = MonitorTransport.new([200, { "data" => { "schedules" => [], "next_after" => nil } }])
    assert_raises(Specstream::Error) { client(t).pause_monitor("sch_x") }
    assert_equal 1, t.calls.size
  end

  def test_set_monitor_delivery_to_a_webhook
    t = MonitorTransport.new(
      [200, { "data" => { "schedules" => [SCHEDULE], "next_after" => nil } }],
      [200, { "data" => { "schedule_id" => "sch_1", "version" => 4, "delivery" => {}, "webhook_secret" => "whsec_x" } }]
    )
    out = client(t).set_monitor_delivery("sch_1", webhook: "https://example.com/hooks/specstream")
    assert_equal "/v1/workspace/schedules/sch_1/delivery", t.calls.last[:uri].path
    assert_equal({ "expected_version" => 3, "notify" => true, "webhook" => "https://example.com/hooks/specstream" },
                 t.calls.last[:body])
    assert_equal "whsec_x", out["webhook_secret"]
  end

  def test_raw_schedule_calls_and_revisit
    t = MonitorTransport.new(*Array.new(4) { [200, { "data" => {} }] })
    c = client(t)
    c.create_capacity_schedule({ "idempotency_key" => "key-12345" })
    c.list_capacity_schedules(project_id: "prj_1")
    c.list_capacity_occurrences("sch 1", before: Time.utc(2026, 11, 1), limit: 5)
    c.revisit("fnd_1", after: "r9")
    assert_equal "/v1/capacity/schedules", t.calls[0][:uri].path
    assert_equal "project_id=prj_1", t.calls[1][:uri].query
    assert_equal "/v1/capacity/schedules/sch%201/occurrences", t.calls[2][:uri].path
    assert_equal({ "before" => "2026-11-01T00:00:00Z", "limit" => "5" }, URI.decode_www_form(t.calls[2][:uri].query).to_h)
    assert_equal "/v1/finds/fnd_1/revisit", t.calls[3][:uri].path
    assert_equal({ "after" => "r9", "limit" => "100" }, URI.decode_www_form(t.calls[3][:uri].query).to_h)
  end
end

class WebhookTest < Minitest::Test
  SECRET = "whsec_test"
  BODY = '{"event":"monitor.found","schedule_id":"sch_1"}'

  def header(stamp, body = BODY, secret = SECRET)
    "t=#{stamp},v1=#{OpenSSL::HMAC.hexdigest('SHA256', secret, "#{stamp}.#{body}")}"
  end

  def test_a_signed_recent_delivery_is_valid
    assert Specstream::Webhook.valid?(secret: SECRET, signature: header(NOW.to_i), body: BODY, now: NOW)
    assert Specstream::Webhook.verify!(secret: SECRET, signature: header(NOW.to_i - 60), body: BODY, now: NOW)
  end

  def test_a_changed_body_a_wrong_secret_or_an_old_time_is_refused
    refute Specstream::Webhook.valid?(secret: SECRET, signature: header(NOW.to_i), body: "#{BODY} ", now: NOW)
    refute Specstream::Webhook.valid?(secret: SECRET, signature: header(NOW.to_i, BODY, "other"), body: BODY, now: NOW)
    refute Specstream::Webhook.valid?(secret: SECRET, signature: header(NOW.to_i - 301), body: BODY, now: NOW)
    refute Specstream::Webhook.valid?(secret: SECRET, signature: "v1=abc", body: BODY, now: NOW)
    refute Specstream::Webhook.valid?(secret: "", signature: header(NOW.to_i), body: BODY, now: NOW)
    assert_raises(Specstream::Error) do
      Specstream::Webhook.verify!(secret: SECRET, signature: nil, body: BODY, now: NOW)
    end
  end
end
