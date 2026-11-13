import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specstream/specstream.dart';
import 'package:test/test.dart';

const key = 'ss_test_key_never_real';

http.Response reply(Object? body, [int status = 200]) =>
    http.Response(jsonEncode(body), status,
        headers: {'content-type': 'application/json'});

/// A client whose every request lands in [seen] and gets the next of [answers]
/// (the last one again when they run out).
SpecStream recording(List<http.Request> seen,
    [List<Object?> answers = const [
      {'data': <String, Object?>{}}
    ]]) {
  var next = 0;
  return SpecStream(key, httpClient: MockClient((request) async {
    seen.add(request);
    final answer = answers[next < answers.length ? next : answers.length - 1];
    next++;
    return reply(answer);
  }));
}

Map<String, Object?> approval() => {
      'quote_id': 'quote_1',
      'quote_hash': 'a' * 64,
      'confirm_max_cents': 500,
      'idempotency_key': 'request-key-1',
    };

void main() {
  test('compile, quote and approve send the bodies the API reads', () async {
    final seen = <http.Request>[];
    final client = recording(seen, [
      {
        'data': {'ast_hash': 'b' * 64}
      },
      {
        'data': {'quote_id': 'quote_1', 'maximum_cents': 500}
      },
      {
        'data': {'find_id': 'find_1'}
      },
    ]);

    final reading = await client.compile('Vector databases with a license');
    final quote = await client.quoteCapacityWork(
        {'ast_hash': reading['ast_hash'], 'operation': 'find'});
    final run = await client.authorizeCapacityWork(approval());

    expect(seen.map((r) => '${r.method} ${r.url.path}'), [
      'POST /v1/parse',
      'POST /v1/capacity/quotes',
      'POST /v1/capacity/executions',
    ]);
    expect(jsonDecode(seen[0].body),
        {'q': 'Vector databases with a license', 'locale': 'en-US'});
    expect(
        jsonDecode(seen[1].body), {'ast_hash': 'b' * 64, 'operation': 'find'});
    expect(jsonDecode(seen[2].body), approval());
    expect(seen[2].headers['Authorization'], 'Bearer $key');
    expect(quote['maximum_cents'], 500);
    expect(run['find_id'], 'find_1');
  });

  test('an approval that is not complete sends nothing', () async {
    final seen = <http.Request>[];
    final client = recording(seen);
    final broken = <Map<String, Object?>>[
      approval()..remove('confirm_max_cents'),
      approval()..['confirm_max_cents'] = '500',
      approval()..['confirm_max_cents'] = -1,
      approval()..['quote_hash'] = 'not-a-hash',
      approval()..['idempotency_key'] = 'short',
      approval()..['quote_id'] = '',
      approval()..['surprise'] = true,
    ];

    for (final body in broken) {
      expect(() => client.authorizeCapacityWork(body), throwsArgumentError,
          reason: '$body');
    }
    expect(seen, isEmpty);

    await client.authorizeCapacityWork(approval()..['authority_id'] = 'auth_1');
    expect(seen, hasLength(1));
  });

  test('eachRow follows next_cursor to the last page', () async {
    final seen = <http.Request>[];
    final client = recording(seen, [
      {
        'data': {
          'rows': [
            {'n': 1},
            {'n': 2}
          ],
          'next_cursor': 'c2'
        }
      },
      {
        'data': {
          'rows': [
            {'n': 3}
          ],
          'next_cursor': null
        }
      },
    ]);

    final rows = await client.eachRow('find 1', limit: 2).toList();

    expect(rows.map((row) => row['n']), [1, 2, 3]);
    expect(seen, hasLength(2));
    expect(seen[0].url.toString(), endsWith('/v1/finds/find%201/rows?limit=2'));
    expect(seen[1].url.queryParameters, {'limit': '2', 'cursor': 'c2'});
  });

  test('eachRow stops when the API repeats a cursor', () async {
    final seen = <http.Request>[];
    final client = recording(seen, [
      {
        'data': {
          'rows': [
            {'n': 1}
          ],
          'next_cursor': 'same'
        }
      },
    ]);

    final rows = await client.eachRow('find_1').toList();

    expect(rows, hasLength(2));
    expect(seen, hasLength(2));
  });

  test('rows refuses a limit the API does not take', () {
    final seen = <http.Request>[];
    final client = recording(seen);

    expect(() => client.rows('find_1', limit: 0), throwsArgumentError);
    expect(() => client.rows('find_1', limit: 101), throwsArgumentError);
    expect(() => client.rows('find_1', cursor: ''), throwsArgumentError);
    expect(seen, isEmpty);
  });

  test('the other Deep Search calls reach their paths', () async {
    final seen = <http.Request>[];
    final client = recording(seen);

    await client.editSpec({
      'target': 'company'
    }, [
      {'op': 'remove', 'path': '/filters/0'}
    ]);
    await client.specOptions('company');
    await client.getCapacityQuote('quote/1');
    await client.getCapacityRequest('request-key-1', projectId: 'proj_1');
    await client.getCapacityBalance();
    await client.getFind('find_1');
    await client.cancelFind('find_1');
    await client.export('find_1', format: 'xlsx');

    expect(seen.map((r) => '${r.method} ${r.url.path}'), [
      'POST /v1/parse/from-chips',
      'GET /v1/spec-options/company',
      'GET /v1/capacity/quotes/quote%2F1',
      'GET /v1/capacity/requests/request-key-1',
      'GET /v1/capacity/balance',
      'GET /v1/finds/find_1',
      'POST /v1/finds/find_1/cancel',
      'POST /v1/finds/find_1/export',
    ]);
    expect(jsonDecode(seen[0].body), {
      'ast': {'target': 'company'},
      'operations': [
        {'op': 'remove', 'path': '/filters/0'}
      ]
    });
    expect(seen[3].url.queryParameters, {'project_id': 'proj_1'});
    expect(seen[4].url.hasQuery, isFalse);
    expect(jsonDecode(seen[7].body), {'format': 'xlsx'});
  });
}
