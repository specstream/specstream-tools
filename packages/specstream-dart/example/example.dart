import 'dart:io';

import 'package:specstream/specstream.dart';

Future<void> main() async {
  final specstream =
      SpecStream(Platform.environment['SPECSTREAM_API_KEY'] ?? '');
  try {
    final search =
        await specstream.webSearch('What is the population of Japan?');
    for (final source in (search['sources'] as List? ?? const []).take(3)) {
      print('${source['title']}  ${source['url']}');
    }

    final pages = await specstream.extractPages({
      'urls': ['https://example.com'],
    });
    for (final page in pages['results'] as List? ?? const []) {
      print('${page['title']}\n${page['text']}');
    }
  } on SpecStreamException catch (error) {
    stderr.writeln(error);
    exitCode = 1;
  } finally {
    specstream.close();
  }
}
