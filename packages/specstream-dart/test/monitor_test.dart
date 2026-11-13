import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specstream/specstream.dart';
import 'package:test/test.dart';

const key = 'ss_test_key_never_real';

http.Response reply(Object? body, [int status = 200]) =>
    http.Response(jsonEncode(body), status,
        headers: {'content-type': 'application/json'});

/// A client whose every request lands in [seen] and gets [answer].
SpecStream recording(List<http.Request> seen,
        {Object? answer = const {'data': {}}, int status = 200}) =>
    SpecStream(key, httpClient: MockClient((request) async {
      seen.add(request);
      return reply(answer, status);
    }));

void main() {
  test('createCapacitySchedule posts the approved limits as they are',
      () async {
    final seen = <http.Request>[];
    final client = recording(seen,
        answer: {
          'data': {'schedule_id': 'sch_1', 'state': 'active', 'version': 1}
        },
        status: 201);
    final body = {
      'idempotency_key': 'weekly-find_1',
      'scope': {
        'ast_hash': 'a' * 64,
        'operation': 'refresh',
        'parent_find_id': 'find_1'
      },
      'cadence_seconds': 604800,
      'first_due_at': '2026-11-20T09:00:00Z',
      'per_run_cents': 500,
      'period_cents': 2000,
      'valid_until': '2027-02-20T09:00:00Z',
    };

    final data = await client.createCapacitySchedule(body);

    expect(seen.single.method, 'POST');
    expect(seen.single.url.path, '/v1/capacity/schedules');
    expect(seen.single.headers['Authorization'], 'Bearer $key');
    expect(seen.single.headers['Content-Type'], startsWith('application/json'));
    expect(jsonDecode(seen.single.body), body);
    expect(data['schedule_id'], 'sch_1');
  });

  test('listCapacitySchedules sends only the filters given', () async {
    final seen = <http.Request>[];
    final client = recording(seen);

    await client.listCapacitySchedules();
    await client.listCapacitySchedules(
        projectId: 'proj_1', after: 'sch_9', limit: 20);

    expect(seen[0].method, 'GET');
    expect(seen[0].url.path, '/v1/capacity/schedules');
    expect(seen[0].url.hasQuery, isFalse);
    expect(seen[1].url.queryParameters,
        {'project_id': 'proj_1', 'after': 'sch_9', 'limit': '20'});
  });

  test('updateCapacitySchedule patches the state with the version read',
      () async {
    final seen = <http.Request>[];
    final client = recording(seen);

    await client.updateCapacitySchedule('sch/1',
        expectedVersion: 3, state: 'paused');

    expect(seen.single.method, 'PATCH');
    expect(seen.single.url.path, '/v1/capacity/schedules/sch%2F1');
    expect(jsonDecode(seen.single.body),
        {'expected_version': 3, 'state': 'paused'});
  });

  test('a conflict names the current version in details', () async {
    final client = recording([], answer: {
      'error': {
        'code': 'conflict',
        'message': 'The schedule changed',
        'details': {'current_version': 4}
      }
    }, status: 409);

    await expectLater(
      client.updateCapacitySchedule('sch_1',
          expectedVersion: 3, state: 'active'),
      throwsA(isA<SpecStreamException>()
          .having((e) => e.status, 'status', 409)
          .having((e) => e.code, 'code', 'conflict')
          .having((e) => e.details['current_version'], 'current_version', 4)),
    );
  });

  test('listCapacityOccurrences and runCapacityScheduleNow name the schedule',
      () async {
    final seen = <http.Request>[];
    final client = recording(seen);

    await client.listCapacityOccurrences('sch_1', before: 'occ_5', limit: 10);
    await client.runCapacityScheduleNow('sch_1');

    expect(seen[0].method, 'GET');
    expect(seen[0].url.path, '/v1/capacity/schedules/sch_1/occurrences');
    expect(seen[0].url.queryParameters, {'before': 'occ_5', 'limit': '10'});
    expect(seen[1].method, 'POST');
    expect(seen[1].url.path, '/v1/capacity/schedules/sch_1/run');
    expect(seen[1].body, isEmpty);
  });

  test('revisit pages with next_after', () async {
    final seen = <http.Request>[];
    final pages = [
      {
        'data': {
          'items': [1],
          'next_after': 'r_1'
        }
      },
      {
        'data': {'items': [], 'next_after': null}
      },
    ];
    final client = SpecStream(key, httpClient: MockClient((request) async {
      seen.add(request);
      return reply(pages[seen.length - 1]);
    }));

    String? after;
    do {
      final page = await client.revisit('find_1', after: after, limit: 50);
      after = page['next_after'] as String?;
    } while (after != null);

    expect(seen.map((r) => r.url.path).toSet(), {'/v1/finds/find_1/revisit'});
    expect(seen[0].url.queryParameters, {'limit': '50'});
    expect(seen[1].url.queryParameters, {'after': 'r_1', 'limit': '50'});
  });

  test('bad monitor input is refused before anything is sent', () {
    final seen = <http.Request>[];
    final client = recording(seen);
    expect(() => client.revisit(' '), throwsArgumentError);
    expect(() => client.runCapacityScheduleNow(''), throwsArgumentError);
    expect(
        () => client.updateCapacitySchedule('sch_1',
            expectedVersion: 1, state: 'stopped'),
        throwsArgumentError);
    expect(
        () => client.updateCapacitySchedule('sch_1',
            expectedVersion: 0, state: 'paused'),
        throwsArgumentError);
    expect(seen, isEmpty);
  });
}
