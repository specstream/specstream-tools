# frozen_string_literal: true

require_relative "lib/specstream/version"

Gem::Specification.new do |spec|
  spec.name = "specstream"
  spec.version = Specstream::VERSION
  spec.authors = ["SpecStream"]
  spec.summary = "SpecStream: the live web data engine. One platform to build, search, extract, enrich, map, " \
                 "and monitor data across the entire web."
  spec.description = "Ruby client for SpecStream's Deep Search API, Search API and Extract API. " \
                     "Ask for any dataset in plain words, and SpecStream builds it from the entire live web: " \
                     "every match found, extracted and enriched into structured records, then monitored for change. " \
                     "Standard library only."
  spec.homepage = "https://specstream.ai"
  spec.license = "MIT"
  spec.required_ruby_version = ">= 3.1"

  spec.metadata = {
    "homepage_uri" => "https://specstream.ai",
    "documentation_uri" => "https://specstream.ai/docs/api",
    "source_code_uri" => "https://github.com/specstream/specstream-tools/tree/main/packages/specstream-ruby",
    "bug_tracker_uri" => "https://github.com/specstream/specstream-tools/issues",
    "rubygems_mfa_required" => "true"
  }

  spec.files = Dir["lib/**/*.rb"] + %w[README.md LICENSE specstream.gemspec]
  spec.require_paths = ["lib"]
end
