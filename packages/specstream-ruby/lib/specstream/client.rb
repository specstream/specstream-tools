# frozen_string_literal: true

require "json"
require "net/http"
require "time"
require "uri"
require_relative "error"
require_relative "version"

module Specstream
  DEFAULT_BASE_URL = "https://api.specstream.ai"
  USER_AGENT = "specstream-ruby/#{VERSION}"
  # A 503 that names a Retry-After of at most this many seconds is asked once more.
  RETRY_AFTER_MAX_S = 10.0

  # Client for the SpecStream API: Deep Search (read a request, quote it, approve it,
  # read the rows), the Search API and the Extract API.
  #
  # Standard library only. Each call opens its own connection, so one client can be
  # shared across threads. Redirects are not followed and no proxy from the
  # environment is used, so the key goes only to the base address.
  class Client
    attr_reader :base_url, :timeout

    # transport: optional callable (method, uri, headers, body) -> [status, headers, body],
    # for tests and for apps that bring their own HTTP stack.
    def initialize(api_key, base_url: DEFAULT_BASE_URL, timeout: 150, transport: nil, sleeper: nil)
      key = api_key.to_s.strip
      raise Error, "SPECSTREAM_API_KEY is required" if key.empty?

      @api_key = key
      @base_url = "#{(base_url.nil? || base_url.to_s.empty? ? DEFAULT_BASE_URL : base_url.to_s).chomp('/')}/"
      @timeout = timeout
      @transport = transport || method(:net_http_transport)
      @sleeper = sleeper || ->(seconds) { sleep(seconds) }
    end

    # Never show the key in logs or consoles.
    def inspect
      "#<#{self.class.name} base_url=#{@base_url.inspect}>"
    end
    alias to_s inspect

    # --- Deep Search ---------------------------------------------------------------

    # POST /v1/parse: read a request in everyday words into a reading (the spec).
    def compile(q, locale: "en-US")
      request("POST", "/v1/parse", { "q" => q, "locale" => locale })
    end

    # POST /v1/parse/from-chips: change a condition or a fact of a reading.
    def edit_spec(ast, operations = [])
      request("POST", "/v1/parse/from-chips", { "ast" => ast, "operations" => operations || [] })
    end

    # GET /v1/spec-options/{target}: the conditions and facts a kind of record supports.
    def spec_options(target)
      request("GET", "/v1/spec-options/#{escape(target)}")
    end

    # POST /v1/capacity/quotes: price a reading before anything runs. Nothing is charged.
    def quote_capacity_work(body)
      request("POST", "/v1/capacity/quotes", body)
    end

    # GET /v1/capacity/quotes/{quote_id}
    def get_capacity_quote(quote_id)
      request("GET", "/v1/capacity/quotes/#{escape(quote_id)}")
    end

    # POST /v1/capacity/executions: approve the exact quote and start the run.
    # Refuses to send anything unless quote_id, quote_hash, confirm_max_cents and
    # idempotency_key are all present and well formed.
    def authorize_capacity_work(body)
      self.class.require_work_authorization(body)
      request("POST", "/v1/capacity/executions", body)
    end

    # GET /v1/capacity/requests/{request_key}: the run already started with this key.
    def get_capacity_request(request_key, project_id: nil)
      request("GET", with_query("/v1/capacity/requests/#{escape(request_key)}", project_id: project_id))
    end

    # GET /v1/capacity/balance
    def get_capacity_balance(project_id: nil)
      request("GET", with_query("/v1/capacity/balance", project_id: project_id))
    end

    # GET /v1/finds/{find_id}: progress of a run.
    def get_find(find_id)
      request("GET", "/v1/finds/#{escape(find_id)}")
    end

    # POST /v1/finds/{find_id}/cancel
    def cancel_find(find_id)
      request("POST", "/v1/finds/#{escape(find_id)}/cancel", {})
    end

    # GET /v1/finds/{find_id}/rows: one page of delivered rows. Follow next_cursor.
    def rows(find_id, cursor: nil, limit: 100)
      unless limit.is_a?(Integer) && limit.between?(1, 100)
        raise ArgumentError, "Row page limit must be an integer from 1 to 100"
      end
      if !cursor.nil? && (!cursor.is_a?(String) || cursor.empty? || cursor.length > 2048)
        raise ArgumentError, "Use the opaque next_cursor returned by this Delivery"
      end

      request("GET", with_query("/v1/finds/#{escape(find_id)}/rows", limit: limit, cursor: cursor))
    end

    # Every delivered row of a run, page after page until next_cursor is null.
    # Reading rows you own costs nothing.
    def each_row(find_id, limit: 100)
      return enum_for(:each_row, find_id, limit: limit) unless block_given?

      cursor = nil
      loop do
        page = rows(find_id, cursor: cursor, limit: limit)
        Array(page["rows"]).each { |row| yield row }
        cursor = page["next_cursor"]
        break if cursor.nil? || cursor.to_s.empty?
      end
    end

    # POST /v1/finds/{find_id}/export: format is csv, xlsx, json or html.
    def export(find_id, format: "csv")
      request("POST", "/v1/finds/#{escape(find_id)}/export", { "format" => format })
    end

    # --- Search API and Extract API --------------------------------------------------

    # GET /v1/web-search
    def web_search(q:, passages: nil)
      request("GET", with_query("/v1/web-search", q: q, passages: passages))
    end

    # POST /v1/extract, for example { "urls" => ["https://example.com"] }.
    def extract_pages(body)
      request("POST", "/v1/extract", body)
    end

    # --- shared ----------------------------------------------------------------------

    def self.require_work_authorization(value)
      required = %w[quote_id quote_hash idempotency_key confirm_max_cents]
      keys = value.is_a?(Hash) ? value.keys.map(&:to_s) : []
      if !value.is_a?(Hash) || !(required - keys).empty? || !(keys - required - ["authority_id"]).empty?
        raise ArgumentError, "Provide the exact quote identity, signature, maximum cents and request key"
      end

      fetch = ->(name) { value.key?(name) ? value[name] : value[name.to_sym] }
      quote_id = fetch.call("quote_id")
      raise ArgumentError, "An explicit quote identity is required" unless quote_id.is_a?(String) && !quote_id.empty?

      quote_hash = fetch.call("quote_hash")
      unless quote_hash.is_a?(String) && quote_hash.match?(/\A[0-9a-f]{64}\z/)
        raise ArgumentError, "The reviewed quote signature is required"
      end

      key = fetch.call("idempotency_key")
      unless key.is_a?(String) && key.length.between?(8, 128)
        raise ArgumentError, "Use a stable request key containing 8 to 128 characters"
      end

      maximum = fetch.call("confirm_max_cents")
      unless maximum.is_a?(Integer) && maximum >= 0
        raise ArgumentError, "The approved maximum must be an explicit nonnegative integer in cents"
      end

      authority = fetch.call("authority_id")
      return if authority.nil? || authority.is_a?(String)

      raise ArgumentError, "Authority must be an explicit existing identifier"
    end

    def request(method, path, body = nil)
      uri = URI.join(@base_url, path.sub(%r{\A/+}, ""))
      payload = body.nil? ? nil : JSON.generate(body)
      status, headers, text = @transport.call(method, uri, headers_for, payload)
      wait = retry_after(status, headers)
      unless wait.nil?
        # The server did nothing and names when to ask again: ask once more.
        @sleeper.call(wait)
        status, headers, text = @transport.call(method, uri, headers_for, payload)
      end
      parse(method, path, status.to_i, text.to_s)
    rescue Error, ArgumentError
      raise
    rescue StandardError => e
      raise Error, "#{method} #{path} transport failed (#{e.class})"
    end

    private

    def headers_for
      auth = @api_key.downcase.start_with?("bearer ") ? @api_key : "Bearer #{@api_key}"
      {
        "Authorization" => auth,
        "Accept" => "application/json",
        "Content-Type" => "application/json",
        "User-Agent" => USER_AGENT
      }
    end

    def parse(method, path, status, text)
      loaded = begin
        JSON.parse(text)
      rescue JSON::ParserError
        raise Error.new("#{method} #{path} failed with HTTP #{status}", status: status, body: text) unless status.between?(200, 299)

        raise Error.new("#{method} #{path} returned invalid JSON", status: status, body: text)
      end
      unless status.between?(200, 299)
        raise Error.new("#{method} #{path} failed with HTTP #{status}", status: status, body: loaded)
      end
      unless loaded.is_a?(Hash)
        raise Error.new("#{method} #{path} returned non-object JSON", status: status, body: loaded)
      end
      if !loaded["error"].nil? || !loaded["data"].is_a?(Hash)
        raise Error.new("#{method} #{path} returned an invalid success envelope", status: status, body: loaded)
      end

      loaded["data"]
    end

    def retry_after(status, headers)
      return nil unless status.to_i == 503

      value = header(headers, "retry-after").to_s.strip
      return nil if value.empty?

      seconds = if value.match?(/\A\d+(\.\d+)?\z/)
                  value.to_f
                else
                  begin
                    Time.httpdate(value) - Time.now
                  rescue ArgumentError
                    return nil
                  end
                end
      seconds.between?(0, RETRY_AFTER_MAX_S) ? seconds : nil
    end

    def header(headers, name)
      return nil unless headers.respond_to?(:each)

      headers.each { |k, v| return(v.is_a?(Array) ? v.first : v) if k.to_s.downcase == name }
      nil
    end

    def escape(value)
      URI.encode_www_form_component(value.to_s).gsub("+", "%20")
    end

    def with_query(path, **params)
      pairs = params.reject { |_, v| v.nil? }.map { |k, v| [k.to_s, [true, false].include?(v) ? v.to_s : v] }
      pairs.empty? ? path : "#{path}?#{URI.encode_www_form(pairs)}"
    end

    def net_http_transport(method, uri, headers, body)
      http = Net::HTTP.new(uri.host, uri.port, nil)
      http.use_ssl = uri.scheme == "https"
      http.open_timeout = [@timeout, 30].min
      http.read_timeout = @timeout
      http.write_timeout = @timeout
      req = Net::HTTPGenericRequest.new(method, !body.nil?, true, uri.request_uri, headers)
      req.body = body unless body.nil?
      res = http.start { |conn| conn.request(req) }
      [res.code.to_i, res.to_hash, res.body.to_s]
    end
  end
end
