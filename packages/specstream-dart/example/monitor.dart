// Monitor a Deep Search list: put it on a weekly schedule, then read what the last refresh reached.
//
//   export SPECSTREAM_API_KEY="ss_live_..."
//   dart run example/monitor.dart <find_id> <ast_hash>
//
// The find and its reading come from a run you already own (see the README).
import 'dart:io';

import 'package:specstream/specstream.dart';

Future<void> main(List<String> args) async {
  if (args.length != 2) {
    stderr.writeln('usage: dart run example/monitor.dart <find_id> <ast_hash>');
    exit(64);
  }
  final findId = args[0];
  final astHash = args[1];
  final client = SpecStream(Platform.environment['SPECSTREAM_API_KEY'] ?? '');
  try {
    final now = DateTime.now().toUtc();
    final schedule = await client.createCapacitySchedule({
      'idempotency_key': 'weekly-$findId',
      'scope': {
        'ast_hash': astHash,
        'operation': 'refresh',
        'parent_find_id': findId,
      },
      'cadence_seconds': 7 * 24 * 3600,
      'first_due_at': now.add(const Duration(days: 7)).toIso8601String(),
      // The limits a person approved: at most $5 a run and $20 a period.
      'per_run_cents': 500,
      'period_cents': 2000,
      'valid_until': now.add(const Duration(days: 90)).toIso8601String(),
    });
    print('schedule ${schedule['schedule_id']} is ${schedule['state']}');

    String? after = '';
    while (after != null) {
      final page = await client.revisit(findId, after: after);
      print(page);
      final next = page['next_after'];
      after = next is String && next.isNotEmpty ? next : null;
    }
  } on SpecStreamException catch (error) {
    stderr.writeln('${error.status} ${error.code}: ${error.message}');
    exitCode = 1;
  } finally {
    client.close();
  }
}
