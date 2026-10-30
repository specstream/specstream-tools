{
  title: 'SpecStream',

  connection: {
    fields: [
      {
        name: 'api_key',
        label: 'API key',
        control_type: 'password',
        optional: false,
        hint: 'Create a key in SpecStream under <a href="https://specstream.ai/workspace/settings" target="_blank">Agents &amp; API</a>. Keys start with ss_live_.'
      }
    ],
    authorization: {
      type: 'custom_auth',
      apply: lambda do |connection|
        key = connection['api_key'].to_s.strip.sub(/\ABearer\s+/i, '')
        headers('Authorization': "Bearer #{key}", 'Accept': 'application/json')
      end
    },
    base_uri: lambda do |_connection|
      'https://api.specstream.ai'
    end
  },

  test: lambda do |_connection|
    get('/v1/me')
  end,

  methods: {
    data: lambda do |response|
      body = response.is_a?(Hash) ? response['data'] : nil
      error('SpecStream returned a response this connector could not read') unless body.is_a?(Hash)
      body
    end,

    list_link: lambda do |find_id|
      "https://specstream.ai/workspace/collections/#{find_id}"
    end,

    # Fields every row carries; a column with the same name is renamed so it can't overwrite them.
    column_key: lambda do |label|
      key = label.to_s.strip.gsub(/[^\w ]/, '_')
      %w[id list_id list_link position source_url checked_at change].include?(key) ? "#{key} (column)" : key
    end,

    # One row as flat fields a recipe can map: each column's label holds what the list shows,
    # plus where the row's first value was read and the link to the list.
    flatten_row: lambda do |find_id, record|
      row = {
        'id' => "#{find_id}:#{record['entity_id']}",
        'list_id' => find_id,
        'list_link' => call(:list_link, find_id),
        'position' => record['ordinal']
      }
      source = nil
      (record['cells'] || []).each do |cell|
        key = call(:column_key, cell['label'].presence || cell['column_id'])
        next if key.blank?
        row[key] = cell['display'].nil? ? (cell['value'].nil? ? '' : cell['value']) : cell['display']
        source ||= cell['provenance'] if cell['provenance'].is_a?(Hash) && cell['provenance']['source_url'].present?
      end
      row['source_url'] = source ? source['source_url'] : ''
      row['checked_at'] = source ? source['observed_at'].to_s : ''
      row
    end,

    # The newest finished list on the account, for samples and mappable columns.
    latest_rows: lambda do |limit|
      found = []
      specs = call(:data, get('/v1/specs', limit: 5))['specs'] || []
      specs.each do |spec|
        break if found.present?
        history = call(:data, get("/v1/specs/#{spec['spec_id']}/finds", limit: 3))['finds'] || []
        history.each do |find|
          page = call(:data, get("/v1/finds/#{find['find_id']}/rows"))
          next unless %w[completed partial].include?(page['status']) && (page['rows'] || []).present?
          found = page['rows'].first(limit).map { |record| call(:flatten_row, page['find_id'], record) }
          break
        end
      end
      found
    end,

    row_fields: lambda do |sample_rows|
      fixed = [
        { name: 'id', label: 'Row ID' },
        { name: 'list_id', label: 'List ID' },
        { name: 'list_link', label: 'List link' },
        { name: 'position', type: 'integer' },
        { name: 'source_url', label: 'Source URL' },
        { name: 'checked_at', label: 'Checked at' },
        { name: 'change', hint: 'New or changed, for rows from a list you keep current.' }
      ]
      known = fixed.map { |field| field[:name] }
      columns = (sample_rows || []).flat_map(&:keys).uniq.reject { |key| known.include?(key) }
      fixed + columns.map { |key| { name: key } }
    end,

    recover: lambda do |request_key|
      response = get("/v1/capacity/requests/#{request_key}").
                 after_error_response(404) { |_code, _body, _headers, _message| { 'data' => nil } }
      found = response.is_a?(Hash) ? response['data'] : nil
      found.is_a?(Hash) && found['find_id'].present? ? found : nil
    end,

    dollars: lambda do |cents|
      cents = cents.to_i
      "$#{cents / 100}.#{(cents % 100).to_s.rjust(2, '0')}"
    end
  },

  object_definitions: {
    row: {
      fields: lambda do |_connection, _config_fields|
        call(:row_fields, call(:latest_rows, 3))
      end
    },

    list: {
      fields: lambda do |_connection, _config_fields|
        [
          { name: 'list_id', label: 'List ID' },
          { name: 'status' },
          { name: 'request', label: 'Request as read' },
          { name: 'number_of_results', type: 'integer' },
          { name: 'maximum_price_usd', label: 'Maximum price (USD)', type: 'number' },
          { name: 'list_link', label: 'List link' }
        ]
      end
    }
  },

  actions: {
    find_list: {
      title: 'Find a list',
      subtitle: 'Ask for a list in plain words',
      description: "Find a <span class='provider'>list</span> in <span class='provider'>SpecStream</span>",
      help: 'Asks for a list in plain words and starts it if the price is within your maximum. ' \
            'Rows arrive through the New row trigger when the list finishes.',

      input_fields: lambda do |_object_definitions|
        [
          {
            name: 'q',
            label: 'What to find',
            control_type: 'text-area',
            optional: false,
            hint: 'Describe the list in plain words, with what every row must meet and the details to bring back. ' \
                  'Example: Roofing companies in Columbus, Ohio with their website and phone.'
          },
          {
            name: 'count',
            label: 'Number of results',
            type: 'integer',
            control_type: 'integer',
            optional: false,
            default: 25,
            hint: 'How many matching rows to find. You pay for each row delivered.'
          },
          {
            name: 'confirm_max_usd',
            label: 'Maximum price (USD)',
            type: 'number',
            control_type: 'number',
            optional: false,
            hint: 'The most this list may cost. If the price comes back higher, nothing runs and the step stops with the price. ' \
                  '<a href="https://specstream.ai/pricing" target="_blank">Pricing</a>'
          }
        ]
      end,

      execute: lambda do |_connection, input|
        q = input['q'].to_s.strip
        error('Describe the list to find.') if q.empty?
        count = input['count'].to_i
        error('Number of results must be 1 or more.') if count < 1
        max_usd = input['confirm_max_usd'].to_f
        error('Maximum price must be more than 0.') unless max_usd.positive?
        max_cents = (max_usd * 100).round

        # The same request asked again within the same hour gets the run it already started,
        # so a retried job never buys the list twice.
        hour = now.utc.strftime('%Y-%m-%dT%H')
        request_key = "workato-#{"#{q}|#{count}|#{max_cents}|#{hour}".encode_sha256.encode_hex[0, 32]}"
        existing = call(:recover, request_key)
        if existing
          next {
            'list_id' => existing['find_id'],
            'status' => existing['status'].presence || 'running',
            'request' => q,
            'number_of_results' => count,
            'maximum_price_usd' => (existing['maximum_cents'] || max_cents).to_f / 100,
            'list_link' => call(:list_link, existing['find_id'])
          }
        end

        reading = call(:data, post('/v1/parse', q: q, locale: 'en-US'))
        unless reading['status'] == 'runnable'
          error("SpecStream needs a clearer request before it can price it. It read: \"#{reading['canonical_sentence'].presence || q}\". " \
                'Add the place or what every row must meet.')
        end

        quote = call(:data, post('/v1/capacity/quotes',
                                 ast_hash: reading['ast_hash'], operation: 'find', requested_units: count))
        if quote['maximum_cents'].to_i > max_cents
          error("This list can cost up to #{call(:dollars, quote['maximum_cents'])}, above your maximum of " \
                "#{call(:dollars, max_cents)}. Raise the maximum or ask for fewer results.")
        end

        run = call(:data, post('/v1/capacity/executions',
                               quote_id: quote['quote_id'], quote_hash: quote['quote_hash'],
                               confirm_max_cents: quote['maximum_cents'], idempotency_key: request_key))
        {
          'list_id' => run['find_id'],
          'status' => run['state'].presence || 'running',
          'request' => reading['canonical_sentence'].presence || q,
          'number_of_results' => count,
          'maximum_price_usd' => quote['maximum_cents'].to_f / 100,
          'list_link' => call(:list_link, run['find_id'])
        }
      end,

      output_fields: lambda do |object_definitions|
        object_definitions['list']
      end,

      sample_output: lambda do |_connection, _input|
        {
          'list_id' => 'fnd_example',
          'status' => 'running',
          'request' => 'Roofing companies in Columbus, Ohio with their website and phone',
          'number_of_results' => 25,
          'maximum_price_usd' => 2.5,
          'list_link' => 'https://specstream.ai/workspace/collections/fnd_example'
        }
      end
    },

    get_list_results: {
      title: 'Get list results',
      subtitle: 'Get the rows of a list',
      description: "Get <span class='provider'>list results</span> in <span class='provider'>SpecStream</span>",
      help: 'Returns every row found so far, each with the page it was read from. Free; nothing runs.',

      input_fields: lambda do |_object_definitions|
        [{ name: 'list_id', label: 'List ID', optional: false, hint: 'The List ID from Find a list or the New row trigger.' }]
      end,

      execute: lambda do |_connection, input|
        list_id = input['list_id'].to_s.strip
        error('Enter a List ID.') unless list_id.match?(/\A[A-Za-z0-9_-]+\z/)
        page = call(:data, get("/v1/finds/#{list_id}/rows"))
        {
          'list_id' => page['find_id'],
          'list_status' => page['status'],
          'number_of_rows' => (page['rows'] || []).length,
          'list_link' => call(:list_link, page['find_id']),
          'rows' => (page['rows'] || []).map { |record| call(:flatten_row, page['find_id'], record) }
        }
      end,

      output_fields: lambda do |object_definitions|
        [
          { name: 'list_id', label: 'List ID' },
          { name: 'list_status', hint: 'running, completed or partial' },
          { name: 'number_of_rows', type: 'integer' },
          { name: 'list_link', label: 'List link' },
          { name: 'rows', type: 'array', of: 'object', properties: object_definitions['row'] }
        ]
      end,

      sample_output: lambda do |_connection, _input|
        rows = call(:latest_rows, 3)
        {
          'list_id' => rows.dig(0, 'list_id') || 'fnd_example',
          'list_status' => 'completed',
          'number_of_rows' => rows.length,
          'list_link' => rows.dig(0, 'list_link') || 'https://specstream.ai/workspace/collections/fnd_example',
          'rows' => rows
        }
      end
    }
  },

  custom_action: true,
  custom_action_help: {
    body: 'Call any SpecStream API endpoint with this connection. Paths start at /v1.',
    learn_more_url: 'https://specstream.ai/docs/api',
    learn_more_text: 'SpecStream API'
  },

  triggers: {
    new_row: {
      title: 'New row',
      subtitle: 'Once for every row a list brings back',
      description: "New <span class='provider'>row</span> in <span class='provider'>SpecStream</span>",
      help: 'Starts a job for every row when a list you asked for finishes, or when a list you keep current finds new or changed rows.',

      input_fields: lambda do |_object_definitions|
        [
          {
            name: 'event',
            label: 'Rows from',
            control_type: 'select',
            pick_list: 'row_events',
            optional: false,
            default: 'find.completed'
          }
        ]
      end,

      webhook_subscribe: lambda do |webhook_url, _connection, input, _recipe_id|
        call(:data, post('/v1/account/webhooks', url: webhook_url, events: [input['event'].presence || 'find.completed']))
      end,

      webhook_unsubscribe: lambda do |webhook_subscribe_output, _connection|
        delete("/v1/account/webhooks/#{webhook_subscribe_output['hook_id']}")
      end,

      webhook_payload_type: 'raw',

      # Only deliveries signed with this subscription's secret within five minutes become jobs.
      # This lambda cannot call methods, so the row shape below mirrors flatten_row.
      webhook_notification: lambda do |input, payload, _eis, _eos, headers, _params, _connection, webhook_subscribe_output|
        signature = (headers || {}).find { |name, _| name.to_s.downcase == 'specstream-signature' }&.last.to_s
        match = signature.match(/\At=(\d+),v1=([a-f0-9]{64})\z/)
        secret = webhook_subscribe_output && webhook_subscribe_output['secret']
        next [] unless match && secret.present? && payload.is_a?(String) && (now.to_i - match[1].to_i).abs <= 300

        expected = "#{match[1]}.#{payload}".hmac_sha256(secret).encode_hex
        next [] unless expected.length == match[2].length &&
                       expected.bytes.zip(match[2].bytes).reduce(0) { |diff, (a, b)| diff | (a ^ b) }.zero?

        body = workato.parse_json(payload)
        next [] unless body['event'] == (input['event'].presence || 'find.completed') && body['id'].present?

        find_id = body['find_id']
        new_ids = body['new_ids'] || []
        reserved = %w[id list_id list_link position source_url checked_at change]
        (body['records'] || []).map do |record|
          row = {
            'id' => "#{find_id}:#{record['entity_id']}",
            'list_id' => find_id,
            'list_link' => "https://specstream.ai/workspace/collections/#{find_id}",
            'position' => record['ordinal']
          }
          source = nil
          (record['cells'] || []).each do |cell|
            key = (cell['label'].presence || cell['column_id']).to_s.strip.gsub(/[^\w ]/, '_')
            next if key.blank?
            key = "#{key} (column)" if reserved.include?(key)
            row[key] = cell['display'].nil? ? (cell['value'].nil? ? '' : cell['value']) : cell['display']
            source ||= cell['provenance'] if cell['provenance'].is_a?(Hash) && cell['provenance']['source_url'].present?
          end
          row['source_url'] = source ? source['source_url'] : ''
          row['checked_at'] = source ? source['observed_at'].to_s : ''
          row['change'] = if body['event'] == 'monitor.found'
                            new_ids.include?(record['entity_id']) ? 'new' : 'changed'
                          else
                            'new'
                          end
          row
        end
      end,

      dedup: lambda do |row|
        row['id']
      end,

      output_fields: lambda do |object_definitions|
        object_definitions['row']
      end,

      sample_output: lambda do |_connection, _input|
        call(:latest_rows, 1).first || {
          'id' => 'fnd_example:ent_example',
          'list_id' => 'fnd_example',
          'list_link' => 'https://specstream.ai/workspace/collections/fnd_example',
          'position' => 1,
          'Business' => 'Northside Roofing',
          'Website' => 'northsideroofing.com',
          'Phone' => '(614) 555-0142',
          'source_url' => 'https://northsideroofing.com/contact',
          'checked_at' => '2026-10-14T08:00:00Z',
          'change' => 'new'
        }
      end
    }
  },

  pick_lists: {
    row_events: lambda do |_connection|
      [
        ['A list you asked for finishes', 'find.completed'],
        ['A list you keep current finds new or changed rows', 'monitor.found']
      ]
    end
  }
}
