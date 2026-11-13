import 'dart:io';

import 'package:specstream/specstream.dart';

/// Reads a request and prints its price. The run starts only when
/// SPECSTREAM_APPROVE_MAX_CENTS names a maximum that covers the quote.
Future<void> main(List<String> args) async {
  final specstream =
      SpecStream(Platform.environment['SPECSTREAM_API_KEY'] ?? '');
  final request = args.isEmpty
      ? 'Open-source vector databases on GitHub, with their license.'
      : args.join(' ');
  try {
    final reading = await specstream.compile(request);
    final quote = await specstream.quoteCapacityWork({
      'ast_hash': reading['ast_hash'],
      'operation': 'find',
      'requested_units': reading['ast']['limit']['max'],
    });
    final maximum = quote['maximum_cents'];
    print('At most $maximum cents, until ${quote['expires_at']}');

    final approved = int.tryParse(
        Platform.environment['SPECSTREAM_APPROVE_MAX_CENTS'] ?? '');
    if (approved == null || maximum is! int || approved < maximum) {
      print('Nothing started. Set SPECSTREAM_APPROVE_MAX_CENTS to approve.');
      return;
    }

    final run = await specstream.authorizeCapacityWork({
      'quote_id': quote['quote_id'],
      'quote_hash': quote['quote_hash'],
      'confirm_max_cents': maximum,
      'idempotency_key': 'example-${quote['quote_id']}',
    });
    final findId = run['find_id'] as String;
    print(await specstream.getFind(findId));

    // The results delivered so far; run it again later for the rest.
    await for (final row in specstream.eachRow(findId)) {
      print(row);
    }
  } on SpecStreamException catch (error) {
    stderr.writeln(error);
    exitCode = 1;
  } finally {
    specstream.close();
  }
}
