# frozen_string_literal: true

require "digest"
require "openssl"
require "time"

module Specstream
  # Monitors: a saved list checked again on the live web on a schedule, within a
  # limit per check and per UTC calendar month. Included in Specstream::Client.
  #
  # The API calls them schedules (/v1/capacity/schedules). The raw calls take and
  # return the API's own fields; the monitor calls below build them for one list.
  module Monitors
    CADENCE_SECONDS = { "hour" => 3_600, "day" => 86_400, "week" => 604_800, "month" => 2_592_000 }.freeze
    MONITOR_STATES = %w[active paused deleted].freeze

    # --- schedules, as the API names them --------------------------------------------

    # POST /v1/capacity/schedules: approve future runs of an exact priced scope within
    # per_run_cents and period_cents. A write: call it after a person agrees to the limits.
    def create_capacity_schedule(body)
      request("POST", "/v1/capacity/schedules", body)
    end

    # GET /v1/capacity/schedules: one page of schedules. Follow next_after.
    def list_capacity_schedules(project_id: nil, after: nil, limit: nil)
      request("GET", with_query("/v1/capacity/schedules", project_id: project_id, after: after, limit: limit))
    end

    # PATCH /v1/capacity/schedules/{id}: { "expected_version" => n, "state" => "active" | "paused" | "deleted" }.
    def update_capacity_schedule(schedule_id, body)
      request("PATCH", "/v1/capacity/schedules/#{escape(require_id(schedule_id))}", body)
    end

    # GET /v1/capacity/schedules/{id}/occurrences: completed, blocked and missed runs, newest first.
    def list_capacity_occurrences(schedule_id, before: nil, limit: nil)
      path = "/v1/capacity/schedules/#{escape(require_id(schedule_id))}/occurrences"
      request("GET", with_query(path, before: before.respond_to?(:iso8601) ? before.iso8601 : before, limit: limit))
    end

    # POST /v1/capacity/schedules/{id}/run: one run now, inside the schedule's own limits.
    def run_capacity_schedule_now(schedule_id)
      request("POST", "/v1/capacity/schedules/#{escape(require_id(schedule_id))}/run", {})
    end

    # PATCH /v1/workspace/schedules/{id}/delivery: where new and changed records go
    # (notify, slack, sendTo, webhook). Needs the schedule's expected_version. Nothing runs.
    # A new webhook answers with webhook_secret once: store it, never log it.
    def set_schedule_delivery(schedule_id, body)
      request("PATCH", "/v1/workspace/schedules/#{escape(require_id(schedule_id))}/delivery", body)
    end

    # GET /v1/finds/{id}/revisit: each record of a refreshed list, with its outcome
    # (still matches, no longer matches, unresolved, unavailable). Follow next_after.
    def revisit(find_id, after: nil, limit: 100)
      request("GET", with_query("/v1/finds/#{escape(require_id(find_id))}/revisit", after: after, limit: limit))
    end

    # --- monitors of one list --------------------------------------------------------

    # Prices one check of a list you own and saves a schedule that checks it again
    # every hour, day, week or month ("month" is every 30 days).
    #
    # Returns the monitor ("status" => "saved"), or "status" => "over_maximum" with
    # nothing saved when one check can cost more than max_price_per_run_usd.
    # max_price_per_month_usd defaults to the per-check maximum times the checks in
    # 31 days. The first check is one interval after the current hour began and the
    # monitor ends a year later, unless first_run_at and ends_at say otherwise.
    # A retry with the same arguments in the same hour gets the monitor already saved.
    def monitor_list(list_id, max_price_per_run_usd:, every: "day", max_price_per_month_usd: nil,
                     first_run_at: nil, ends_at: nil)
      find_id = require_id(list_id, "Give the list_id of the list to monitor")
      cadence = CADENCE_SECONDS[every.to_s]
      raise ArgumentError, 'every must be "hour", "day", "week" or "month"' if cadence.nil?

      per_run = usd_to_cents(max_price_per_run_usd)
      raise ArgumentError, "max_price_per_run_usd must be greater than 0" unless per_run.positive?

      period = if max_price_per_month_usd.nil?
                 per_run * (31 * 86_400.0 / cadence).ceil
               else
                 usd_to_cents(max_price_per_month_usd)
               end
      raise ArgumentError, "max_price_per_month_usd must cover at least one check" if period < per_run

      hour_start = Time.at((current_time.to_i / 3600) * 3600).utc
      first = first_run_at.nil? ? hour_start + cadence : to_time(first_run_at, "first_run_at")
      ends = ends_at.nil? ? first + (365 * 86_400) : to_time(ends_at, "ends_at")
      raise ArgumentError, "ends_at must come after the first check" unless ends > first

      list = get_find(find_id)
      ast_hash = list["ast_hash"]
      unless ast_hash.is_a?(String) && !ast_hash.empty?
        raise Error, "GET /v1/finds/#{find_id} returned no ast_hash"
      end

      units = Integer(list["requested_count"] || 25, exception: false) || 25
      scope = {
        "ast_hash" => ast_hash,
        "operation" => "refresh",
        "parent_find_id" => find_id,
        "requested_units" => units.clamp(1, 10_000)
      }
      # A list in a project is checked in that project; the API refuses any other.
      project = list["project_id"]
      scope["project_id"] = project if project.is_a?(String) && !project.empty?

      quote = quote_capacity_work(scope)
      maximum = Integer(quote["maximum_cents"] || 0, exception: false) || 0
      if maximum > per_run
        return {
          "status" => "over_maximum",
          "list_id" => find_id,
          "maximum_price_usd" => maximum / 100.0,
          "message" => "Nothing was saved: one check of this list can cost up to #{dollars(maximum)}, " \
                       "above the maximum of #{dollars(per_run)} per check. Raise max_price_per_run_usd."
        }
      end

      first_due = first.utc.iso8601
      valid_until = ends.utc.iso8601
      digest = Digest::SHA256.hexdigest([find_id, cadence, per_run, period, first_due, valid_until].join("|"))
      saved = create_capacity_schedule(
        "idempotency_key" => "ruby-monitor-#{digest[0, 32]}",
        "scope" => scope,
        "cadence_seconds" => cadence,
        "first_due_at" => first_due,
        "per_run_cents" => per_run,
        "period_cents" => period,
        "valid_until" => valid_until
      )
      monitor_view(saved)
    end

    # Every monitor of the account, running, paused or ended, page after page. Free.
    def monitors(project_id: nil)
      found = []
      after = nil
      loop do
        page = list_capacity_schedules(project_id: project_id, after: after, limit: 100)
        Array(page["schedules"]).each { |item| found << monitor_view(item) if item.is_a?(Hash) }
        following = page["next_after"]
        break if !following.is_a?(String) || following.empty? || following == after

        after = following
      end
      found
    end

    # A monitor's recent checks, newest first: when, the outcome, the reason and the
    # list each one made. Free.
    def monitor_runs(monitor_id, limit: 50)
      size = (Integer(limit, exception: false) || 50).clamp(1, 100)
      page = list_capacity_occurrences(monitor_id, limit: size)
      Array(page["occurrences"]).select { |item| item.is_a?(Hash) }.map do |item|
        {
          "due_at" => item["due_at"].to_s,
          "status" => item["status"].to_s,
          "reason" => item["reason"]&.to_s,
          "list_id" => item["find_id"]&.to_s
        }
      end
    end

    # One check now, inside the monitor's limits. Its regular times stay as they are.
    def run_monitor_now(monitor_id)
      id = require_id(monitor_id)
      run = run_capacity_schedule_now(id)
      raise Error, "POST /v1/capacity/schedules/#{id}/run returned no find_id" if run["find_id"].nil?

      { "monitor_id" => id, "list_id" => run["find_id"].to_s, "started_at" => run["started_at"].to_s }
    end

    # Stops the checks until resume_monitor. A missed check is never bought later.
    def pause_monitor(monitor_id)
      set_monitor_state(monitor_id, "paused")
    end

    # Starts the checks again from the next time due.
    def resume_monitor(monitor_id)
      set_monitor_state(monitor_id, "active")
    end

    # Ends the monitor for good. The lists it made stay yours.
    def delete_monitor(monitor_id)
      set_monitor_state(monitor_id, "deleted")
    end

    # Where each check's new and changed records go. webhook: an https URL; slack: a
    # channel of the connected Slack workspace; send_to: a connected tool; notify:
    # SpecStream notifications. Nothing runs. A new webhook comes back with
    # "webhook_secret" once: keep it for Specstream::Webhook.verify.
    def set_monitor_delivery(monitor_id, webhook: nil, slack: nil, send_to: nil, notify: true)
      id = require_id(monitor_id)
      body = { "expected_version" => current_monitor(id)["version"], "notify" => notify ? true : false }
      body["webhook"] = webhook unless webhook.nil?
      body["slack"] = slack unless slack.nil?
      body["sendTo"] = send_to unless send_to.nil?
      set_schedule_delivery(id, body)
    end

    private

    def set_monitor_state(monitor_id, state)
      raise ArgumentError, "state must be one of #{MONITOR_STATES.join(', ')}" unless MONITOR_STATES.include?(state)

      id = require_id(monitor_id)
      current = current_monitor(id)
      monitor_view(update_capacity_schedule(id, { "expected_version" => current["version"], "state" => state }))
    end

    def current_monitor(id)
      monitors.find { |monitor| monitor["monitor_id"] == id } or raise Error, "No monitor #{id} on this account"
    end

    def monitor_view(data)
      id = data["schedule_id"]
      raise Error, "The schedule answer carries no schedule_id" unless id.is_a?(String) && !id.empty?

      scope = data["scope"].is_a?(Hash) ? data["scope"] : {}
      {
        "status" => "saved",
        "monitor_id" => id,
        "list_id" => optional_text(scope["parent_find_id"]),
        "state" => data["state"].to_s,
        "every_seconds" => Integer(data["cadence_seconds"] || 0, exception: false) || 0,
        "next_run_at" => optional_text(data["next_due_at"]),
        "last_run_at" => optional_text(data["last_occurrence_at"]),
        "last_list_id" => optional_text(data["last_find_id"]),
        "last_reason" => optional_text(data["last_reason"]),
        "max_price_per_run_usd" => cents_to_usd(data["per_run_cents"]),
        "max_price_per_month_usd" => cents_to_usd(data["monthly_maximum_cents"] || data["period_cents"]),
        "valid_until" => optional_text(data["valid_until"]),
        "version" => Integer(data["version"] || 0, exception: false) || 0
      }
    end

    def require_id(value, message = "An identifier is required")
      text = value.to_s.strip
      raise ArgumentError, message if text.empty?

      text
    end

    def optional_text(value)
      value.nil? || value.to_s.empty? ? nil : value.to_s
    end

    def usd_to_cents(value)
      number = Float(value, exception: false)
      raise ArgumentError, "Give a price in US dollars, for example 2 or 2.5" if number.nil? || !number.finite?

      (number * 100).round
    end

    def cents_to_usd(value)
      (Integer(value || 0, exception: false) || 0) / 100.0
    end

    def dollars(cents)
      format("$%.2f", cents / 100.0)
    end

    def to_time(value, name)
      return value.to_time.utc if value.respond_to?(:to_time) && !value.is_a?(String)

      Time.iso8601(value.to_s).utc
    rescue ArgumentError
      raise ArgumentError, "#{name} must be a Time or an ISO 8601 time"
    end

    def current_time
      @clock ? @clock.call : Time.now
    end
  end

  # Checks a monitor delivery before your app trusts its body.
  #
  # Each delivery is a JSON POST with Specstream-Event-Id and
  # Specstream-Signature: t=<unix time>,v1=<hex>, where v1 is the HMAC-SHA256 of
  # "<t>.<raw body>" with the webhook's signing secret.
  module Webhook
    DEFAULT_TOLERANCE_S = 300

    # true when the signature matches the raw body and t is within tolerance seconds.
    def self.valid?(secret:, signature:, body:, tolerance: DEFAULT_TOLERANCE_S, now: Time.now)
      verify!(secret: secret, signature: signature, body: body, tolerance: tolerance, now: now)
      true
    rescue Error
      false
    end

    # Raises Specstream::Error unless the delivery is signed with secret and recent.
    def self.verify!(secret:, signature:, body:, tolerance: DEFAULT_TOLERANCE_S, now: Time.now)
      raise Error, "The webhook signing secret is required" if secret.to_s.empty?

      parts = signature.to_s.split(",").filter_map do |part|
        key, value = part.strip.split("=", 2)
        [key, value] unless value.nil?
      end
      stamp = parts.find { |key, _| key == "t" }&.last
      signed = parts.select { |key, _| key == "v1" }.map(&:last)
      raise Error, "Specstream-Signature has no t= or v1=" if stamp.nil? || !stamp.match?(/\A\d+\z/) || signed.empty?
      raise Error, "Specstream-Signature is too old or from the future" if (now.to_i - stamp.to_i).abs > tolerance

      expected = OpenSSL::HMAC.hexdigest("SHA256", secret.to_s, "#{stamp}.#{body}")
      return true if signed.any? { |value| secure_compare(expected, value) }

      raise Error, "Specstream-Signature does not match the body"
    end

    def self.secure_compare(left, right)
      return false unless left.bytesize == right.bytesize

      OpenSSL.fixed_length_secure_compare(left, right)
    end
    private_class_method :secure_compare
  end
end
