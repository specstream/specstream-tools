# frozen_string_literal: true

require "minitest/autorun"
require "json"
require "socket"
require "specstream"

# The real Net::HTTP path against a one-shot local server (no network, no key).
class HttpBoundaryTest < Minitest::Test
  def serve(status_line, body, extra_headers = "")
    server = TCPServer.new("127.0.0.1", 0)
    seen = {}
    thread = Thread.new do
      sock = server.accept
      seen[:request_line] = sock.gets
      headers = {}
      while (line = sock.gets) && line != "\r\n"
        k, v = line.split(":", 2)
        headers[k.downcase] = v.strip
      end
      seen[:headers] = headers
      length = headers["content-length"].to_i
      seen[:body] = length.positive? ? sock.read(length) : nil
      sock.write("HTTP/1.1 #{status_line}\r\nContent-Type: application/json\r\n#{extra_headers}" \
                 "Content-Length: #{body.bytesize}\r\nConnection: close\r\n\r\n#{body}")
      sock.close
    end
    yield "http://127.0.0.1:#{server.addr[1]}"
    thread.join(5)
    seen
  ensure
    server&.close
  end

  def test_post_goes_over_http_with_json_body
    seen = serve("200 OK", JSON.generate({ "data" => { "ast_hash" => "h" } })) do |base|
      out = Specstream::Client.new("ss_k", base_url: base, timeout: 5).compile("tools")
      assert_equal "h", out["ast_hash"]
    end
    assert_equal "POST /v1/parse HTTP/1.1", seen[:request_line].strip
    assert_equal "Bearer ss_k", seen[:headers]["authorization"]
    assert_equal({ "q" => "tools", "locale" => "en-US" }, JSON.parse(seen[:body]))
  end

  def test_redirect_is_not_followed
    serve("302 Found", "{}", "Location: http://example.com/\r\n") do |base|
      err = assert_raises(Specstream::Error) do
        Specstream::Client.new("ss_k", base_url: base, timeout: 5).get_find("f")
      end
      assert_equal 302, err.status
    end
  end

  def test_closed_port_is_a_transport_error
    port = TCPServer.open("127.0.0.1", 0) { |s| s.addr[1] }
    err = assert_raises(Specstream::Error) do
      Specstream::Client.new("ss_k", base_url: "http://127.0.0.1:#{port}", timeout: 2).get_find("f")
    end
    assert_match(/transport failed/, err.message)
  end
end
