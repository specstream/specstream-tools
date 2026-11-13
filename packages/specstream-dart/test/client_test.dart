import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specstream/specstream.dart';
import 'package:test/test.dart';

const key = 'ss_test_key_never_real';

http.Response reply(Object? body,
        [int status = 200, Map<String, String> headers = const {}]) =>
    http.Response(jsonEncode(body), status,
        headers: {'content-type': 'application/json', ...headers});

void main() {
  test(
      'webSearch sends GET /v1/web-search with the key and only the parameters given',
      () async {
    late http.Request seen;
    final client = SpecStream(key, httpClient: MockClient((request) async {
      seen = request;
      return reply({
        'data': {
          'sources': [
            {'title': 'Japan', 'url': 'https://example.com/japan'}
          ]
        }
      });
    }));

    final data = await client.webSearch('population of Japan & more',
        num: 5, speed: 'fast', news: false);

    expect(seen.method, 'GET');
    expect(seen.url.origin, 'https://api.specstream.ai');
    expect(seen.url.path, '/v1/web-search');
    expect(seen.url.queryParameters, {
      'q': 'population of Japan & more',
      'num': '5',
      'speed': 'fast',
      'news': 'false'
    });
    expect(seen.headers['Authorization'], 'Bearer $key');
    expect(seen.headers['User-Agent'], 'specstream-dart/$packageVersion');
    expect(seen.followRedirects, isFalse);
    expect(seen.body, isEmpty);
    expect(data['sources'][0]['url'], 'https://example.com/japan');
  });

  test('extractPages posts the body as JSON to /v1/extract', () async {
    late http.Request seen;
    final client = SpecStream(key, baseUrl: 'https://proxy.example/api/',
        httpClient: MockClient((request) async {
      seen = request;
      return reply({
        'data': {
          'results': [
            {
              'url': 'https://example.com',
              'title': 'Example Domain',
              'text': 'Text with é.'
            }
          ]
        }
      });
    }));

    final data = await client.extractPages({
      'urls': ['https://example.com']
    });

    expect(seen.method, 'POST');
    expect(seen.url.toString(), 'https://proxy.example/api/v1/extract');
    expect(seen.headers['Content-Type'], startsWith('application/json'));
    expect(jsonDecode(seen.body), {
      'urls': ['https://example.com']
    });
    expect(data['results'][0]['text'], 'Text with é.');
  });

  test(
      'a refused request throws with status, code and details, and never the key',
      () async {
    final client = SpecStream(key, httpClient: MockClient((request) async {
      return reply({
        'error': {
          'code': 'insufficient_credit',
          'message': 'Add credit',
          'details': {'balance_cents': 0}
        }
      }, 402);
    }));

    await expectLater(
      client.webSearch('q'),
      throwsA(isA<SpecStreamException>()
          .having((e) => e.status, 'status', 402)
          .having((e) => e.code, 'code', 'insufficient_credit')
          .having((e) => e.details, 'details', {'balance_cents': 0}).having(
              (e) => e.toString(),
              'text',
              allOf(contains('HTTP 402'), isNot(contains(key))))),
    );
    expect(client.toString(), isNot(contains(key)));
  });

  test('a 503 with a short Retry-After is asked once more, and only once',
      () async {
    var calls = 0;
    final waits = <Duration>[];
    final client = SpecStream(
      key,
      sleep: (wait) async => waits.add(wait),
      httpClient: MockClient((request) async {
        calls += 1;
        return calls == 1
            ? reply(
                {
                  'error': {'code': 'busy'}
                },
                503,
                {'retry-after': '2'})
            : reply({
                'data': {'ok': true}
              });
      }),
    );

    expect(await client.webSearch('q'), {'ok': true});
    expect(calls, 2);
    expect(waits, [const Duration(seconds: 2)]);

    calls = 0;
    final always = SpecStream(
      key,
      sleep: (wait) async {},
      httpClient: MockClient((request) async {
        calls += 1;
        return reply(
            {
              'error': {'code': 'busy'}
            },
            503,
            {'retry-after': '1'});
      }),
    );
    await expectLater(
        always.webSearch('q'),
        throwsA(
            isA<SpecStreamException>().having((e) => e.status, 'status', 503)));
    expect(calls, 2);
  });

  test(
      'a 503 with a long or missing Retry-After, and any other failure, is not retried',
      () async {
    for (final response in [
      reply(
          {
            'error': {'code': 'busy'}
          },
          503,
          {'retry-after': '60'}),
      reply({
        'error': {'code': 'busy'}
      }, 503),
      reply(
          {
            'error': {'code': 'boom'}
          },
          500,
          {'retry-after': '1'}),
    ]) {
      var calls = 0;
      final client = SpecStream(key, sleep: (wait) async {},
          httpClient: MockClient((request) async {
        calls += 1;
        return response;
      }));
      await expectLater(client.extractPages({'urls': []}),
          throwsA(isA<SpecStreamException>()));
      expect(calls, 1);
    }
  });

  test('a reply that is not the data envelope throws', () async {
    for (final response in [
      http.Response('<html>', 200),
      http.Response('<html>bad gateway</html>', 502),
      reply([1, 2]),
      reply({'data': 'text'}),
      reply({
        'data': {},
        'error': {'code': 'odd'}
      }),
    ]) {
      final client =
          SpecStream(key, httpClient: MockClient((request) async => response));
      await expectLater(
          client.webSearch('q'), throwsA(isA<SpecStreamException>()));
    }
  });

  test(
      'a transport failure and a timeout throw SpecStreamException without the request',
      () async {
    final broken = SpecStream(key, httpClient: MockClient((request) async {
      throw http.ClientException(
          'connection refused for ${request.url} with ${request.headers}');
    }));
    await expectLater(
      broken.webSearch('private question'),
      throwsA(isA<SpecStreamException>().having(
          (e) => e.toString(),
          'text',
          allOf(contains('transport failed'), isNot(contains(key)),
              isNot(contains('private'))))),
    );

    // The server never answers; only the client's own timeout can end the call.
    final slow = SpecStream(key,
        timeout: const Duration(milliseconds: 20),
        httpClient: MockClient((request) => Completer<http.Response>().future));
    await expectLater(
      slow.webSearch('q'),
      throwsA(isA<SpecStreamException>()
          .having((e) => e.message, 'message', contains('timed out'))),
    );
  });

  test('bad input is refused before anything is sent', () {
    var calls = 0;
    final mock = MockClient((request) async {
      calls += 1;
      return reply({'data': {}});
    });
    expect(() => SpecStream('  ', httpClient: mock), throwsArgumentError);
    expect(
        () => SpecStream(key, baseUrl: 'ftp://example.com', httpClient: mock),
        throwsArgumentError);
    expect(() => SpecStream(key, baseUrl: 'not an address', httpClient: mock),
        throwsArgumentError);
    final client = SpecStream(key, httpClient: mock);
    expect(() => client.webSearch(' '), throwsArgumentError);
    expect(client.extractPages({'urls': Object()}), throwsArgumentError);
    expect(calls, 0);
  });

  test('a key that already says Bearer is sent as it is', () async {
    late http.Request seen;
    final client =
        SpecStream('Bearer $key', httpClient: MockClient((request) async {
      seen = request;
      return reply({'data': {}});
    }));
    await client.webSearch('q');
    expect(seen.headers['Authorization'], 'Bearer $key');
  });

  test('packageVersion is the version of pubspec.yaml and of the changelog',
      () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    expect(pubspec, contains('\nversion: $packageVersion\n'));
    expect(File('CHANGELOG.md').readAsStringSync(),
        startsWith('## $packageVersion\n'));
  });
}
