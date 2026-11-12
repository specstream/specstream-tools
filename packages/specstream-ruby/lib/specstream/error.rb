# frozen_string_literal: true

require "json"

module Specstream
  # Raised for every failed call: a refused request, a transport failure or a reply
  # that is not the API's {"data": {...}} envelope.
  class Error < StandardError
    attr_reader :status, :body, :code, :details

    def initialize(message, status: nil, body: nil)
      super(message)
      @status = status
      @body = body
      @code = nil
      @details = {}
      parsed = body
      if parsed.is_a?(String)
        begin
          parsed = JSON.parse(parsed)
        rescue JSON::ParserError
          parsed = nil
        end
      end
      return unless parsed.is_a?(Hash) && parsed["error"].is_a?(Hash)

      error = parsed["error"]
      @code = error["code"] if error["code"].is_a?(String)
      @details = error["details"].dup if error["details"].is_a?(Hash)
    end
  end
end
