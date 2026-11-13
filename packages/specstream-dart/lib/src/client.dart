import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'error.dart';

/// The address every call goes to unless `baseUrl` says otherwise.
const defaultBaseUrl = 'https://api.specstream.ai';

/// This package's version, as in pubspec.yaml.
const packageVersion = '0.1.0';

/// A 503 that names a Retry-After of at most this many seconds is asked once more.
const _retryAfterMax = Duration(seconds: 10);

final RegExp _quoteHash = RegExp(r'^[0-9a-f]{64}$');

/// Client for SpecStream's Deep Search, Search API and Extract API.
///
/// ```dart
/// final specstream = SpecStream(apiKey);
/// final search = await specstream.webSearch('What is the population of Japan?');
/// final pages = await specstream.extractPages({'urls': ['https://example.com']});
/// specstream.close();
/// ```
///
/// Every method returns the `data` object of the API's reply and throws
/// [SpecStreamException] on any failure. Redirects are not followed, so the key
/// goes only to the base address.
class SpecStream {
  final String _apiKey;
  final Uri _base;
  final http.Client _http;
  final bool _ownsHttp;
  final Future<void> Function(Duration) _sleep;

  /// How long one request may take before it fails.
  final Duration timeout;

  /// [apiKey] is an API key from Agents & API in the SpecStream workspace.
  ///
  /// [httpClient] lets an app bring its own HTTP stack (and lets tests answer
  /// without a network); the caller closes a client it passes in.
  SpecStream(
    String apiKey, {
    String baseUrl = defaultBaseUrl,
    this.timeout = const Duration(seconds: 150),
    http.Client? httpClient,
    Future<void> Function(Duration)? sleep,
  })  : _apiKey = apiKey.trim(),
        _base = _parseBase(baseUrl),
        _http = httpClient ?? http.Client(),
        _ownsHttp = httpClient == null,
        _sleep = sleep ?? Future<void>.delayed {
    if (_apiKey.isEmpty) {
      if (_ownsHttp) _http.close();
      throw ArgumentError('A SpecStream API key is required');
    }
  }

  /// The address every call goes to.
  String get baseUrl => _base.toString();

  /// Search API, `GET /v1/web-search`: search the live web.
  ///
  /// [num] is the number of results (up to 10 per search), [page] the result
  /// page, [speed] `fast` for the fast tier, [news] true for news results,
  /// [passages] true to get the passages of each page that answer [q].
  /// [language], [country] and [safe] narrow the search. A parameter left out
  /// is not sent, and the API's default applies.
  Future<Map<String, dynamic>> webSearch(
    String q, {
    int? num,
    int? page,
    String? speed,
    bool? news,
    bool? passages,
    String? language,
    String? country,
    String? safe,
  }) {
    if (q.trim().isEmpty) {
      throw ArgumentError.value(q, 'q', 'A search needs a question');
    }
    final query = <String, String>{
      'q': q,
      if (num != null) 'num': '$num',
      if (page != null) 'page': '$page',
      if (speed != null) 'speed': speed,
      if (news != null) 'news': '$news',
      if (passages != null) 'passages': '$passages',
      if (language != null) 'language': language,
      if (country != null) 'country': country,
      if (safe != null) 'safe': safe,
    };
    return _request('GET', '/v1/web-search', query: query);
  }

  /// Extract API, `POST /v1/extract`: read pages as clean text.
  ///
  /// [request] is the API's body, for example `{'urls': ['https://example.com']}`:
  /// up to 20 pages, live from their URLs or from HTML you send.
  Future<Map<String, dynamic>> extractPages(Map<String, Object?> request) {
    return _request('POST', '/v1/extract', body: request);
  }

  /// `POST /v1/parse`: reads a request in everyday words into a reading (the
  /// spec): the conditions every result must meet and the facts to bring back.
  Future<Map<String, dynamic>> compile(String q, {String locale = 'en-US'}) {
    if (q.trim().isEmpty) {
      throw ArgumentError.value(q, 'q', 'Deep Search needs a request');
    }
    return _request('POST', '/v1/parse', body: {'q': q, 'locale': locale});
  }

  /// `POST /v1/parse/from-chips`: changes a condition or a fact of a reading.
  Future<Map<String, dynamic>> editSpec(
    Map<String, Object?> ast, [
    List<Map<String, Object?>> operations = const [],
  ]) =>
      _request('POST', '/v1/parse/from-chips',
          body: {'ast': ast, 'operations': operations});

  /// `GET /v1/spec-options/{target}`: the conditions and facts that a kind of
  /// record supports.
  Future<Map<String, dynamic>> specOptions(String target) =>
      _request('GET', '/v1/spec-options/${_segment(target, 'target')}');

  /// `POST /v1/capacity/quotes`: prices a reading before anything runs.
  /// Nothing is charged.
  ///
  /// [request] is the API's body, for example `ast_hash` from [compile],
  /// `operation` (`find`) and `requested_units`.
  Future<Map<String, dynamic>> quoteCapacityWork(
          Map<String, Object?> request) =>
      _request('POST', '/v1/capacity/quotes', body: request);

  /// `GET /v1/capacity/quotes/{quote_id}`: a quote you made before.
  Future<Map<String, dynamic>> getCapacityQuote(String quoteId) =>
      _request('GET', '/v1/capacity/quotes/${_segment(quoteId, 'quoteId')}');

  /// `POST /v1/capacity/executions`: approves one exact quote and starts the
  /// run.
  ///
  /// [request] holds `quote_id`, `quote_hash`, `confirm_max_cents` (the
  /// maximum a person approved) and `idempotency_key`, and may hold
  /// `authority_id`. Nothing is sent unless all four are present and well
  /// formed. The same `idempotency_key` never starts a second run.
  Future<Map<String, dynamic>> authorizeCapacityWork(
      Map<String, Object?> request) {
    requireWorkAuthorization(request);
    return _request('POST', '/v1/capacity/executions', body: request);
  }

  /// `GET /v1/capacity/requests/{request_key}`: the run that this
  /// `idempotency_key` started. Use it when a reply to
  /// [authorizeCapacityWork] was lost.
  Future<Map<String, dynamic>> getCapacityRequest(String requestKey,
          {String? projectId}) =>
      _request(
          'GET', '/v1/capacity/requests/${_segment(requestKey, 'requestKey')}',
          query: _query({'project_id': projectId}));

  /// `GET /v1/capacity/balance`: the credit of the account.
  Future<Map<String, dynamic>> getCapacityBalance({String? projectId}) =>
      _request('GET', '/v1/capacity/balance',
          query: _query({'project_id': projectId}));

  /// `GET /v1/finds/{id}`: the progress of a run.
  Future<Map<String, dynamic>> getFind(String findId) =>
      _request('GET', '/v1/finds/${_segment(findId, 'findId')}');

  /// `POST /v1/finds/{id}/cancel`: stops a run. Results already delivered
  /// stay yours.
  Future<Map<String, dynamic>> cancelFind(String findId) =>
      _request('POST', '/v1/finds/${_segment(findId, 'findId')}/cancel',
          body: const <String, Object?>{});

  /// `GET /v1/finds/{id}/rows`: one page of delivered results with their
  /// sources. Page with the reply's `next_cursor` as [cursor] until it is
  /// null. [limit] is 1 to 100 results a page.
  Future<Map<String, dynamic>> rows(String findId,
      {String? cursor, int limit = 100}) {
    if (limit < 1 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'Use 1 to 100');
    }
    if (cursor != null && (cursor.isEmpty || cursor.length > 2048)) {
      throw ArgumentError.value(
          cursor, 'cursor', 'Use the next_cursor of the page before');
    }
    return _request('GET', '/v1/finds/${_segment(findId, 'findId')}/rows',
        query: _query({'limit': limit, 'cursor': cursor}));
  }

  /// Every delivered result of a run, page after page until `next_cursor` is
  /// null. Reading results you own costs nothing.
  Stream<Map<String, dynamic>> eachRow(String findId,
      {int limit = 100}) async* {
    String? cursor;
    while (true) {
      final page = await rows(findId, cursor: cursor, limit: limit);
      final list = page['rows'];
      if (list is List) {
        for (final row in list) {
          if (row is Map) yield Map<String, dynamic>.from(row);
        }
      }
      final next = page['next_cursor'];
      // A cursor that repeats would never end: stop there.
      if (next is! String || next.isEmpty || next == cursor) return;
      cursor = next;
    }
  }

  /// `POST /v1/finds/{id}/export`: the results as a file. [format] is `csv`,
  /// `xlsx`, `json` or `html`.
  Future<Map<String, dynamic>> export(String findId, {String format = 'csv'}) =>
      _request('POST', '/v1/finds/${_segment(findId, 'findId')}/export',
          body: {'format': format});

  /// Throws [ArgumentError] unless [value] is a complete approval of one
  /// quote, as [authorizeCapacityWork] sends it.
  static void requireWorkAuthorization(Map<String, Object?> value) {
    const required = [
      'quote_id',
      'quote_hash',
      'idempotency_key',
      'confirm_max_cents',
    ];
    final allowed = {...required, 'authority_id'};
    if (!required.every(value.containsKey) ||
        !value.keys.every(allowed.contains)) {
      throw ArgumentError(
          'An approval holds quote_id, quote_hash, confirm_max_cents and idempotency_key, and may hold authority_id');
    }
    final quoteId = value['quote_id'];
    if (quoteId is! String || quoteId.isEmpty) {
      throw ArgumentError('quote_id is the identity of the quote you approve');
    }
    final quoteHash = value['quote_hash'];
    if (quoteHash is! String || !_quoteHash.hasMatch(quoteHash)) {
      throw ArgumentError('quote_hash is the quote_hash of that quote');
    }
    final key = value['idempotency_key'];
    if (key is! String || key.length < 8 || key.length > 128) {
      throw ArgumentError('idempotency_key has 8 to 128 characters');
    }
    final maximum = value['confirm_max_cents'];
    if (maximum is! int || maximum < 0) {
      throw ArgumentError(
          'confirm_max_cents is the approved maximum, a whole number of cents');
    }
    final authority = value['authority_id'];
    if (authority != null && authority is! String) {
      throw ArgumentError('authority_id is the identity of an authority');
    }
  }

  /// `GET /v1/finds/{id}/revisit`: which saved results of a Deep Search list
  /// the last refresh reached, and which it did not.
  ///
  /// Page with the reply's `next_after` as [after] until it is null. [limit]
  /// is 1 to 200 results a page.
  Future<Map<String, dynamic>> revisit(String findId,
          {String? after, int? limit}) =>
      _request('GET', '/v1/finds/${_segment(findId, 'findId')}/revisit',
          query: _query({'after': after, 'limit': limit}));

  /// `POST /v1/capacity/schedules`: runs a Deep Search request again on a
  /// cadence, within the money limits a person approved.
  ///
  /// [request] is the API's body: `idempotency_key`, `scope` (the same object
  /// as a quote request, for example a refresh of a list you own),
  /// `cadence_seconds` (3600 or more), `first_due_at`, `per_run_cents`,
  /// `period_cents` and `valid_until`. Nothing runs beyond those limits.
  Future<Map<String, dynamic>> createCapacitySchedule(
          Map<String, Object?> request) =>
      _request('POST', '/v1/capacity/schedules', body: request);

  /// `GET /v1/capacity/schedules`: the schedules of the account, one page.
  Future<Map<String, dynamic>> listCapacitySchedules(
          {String? projectId, String? after, int? limit}) =>
      _request('GET', '/v1/capacity/schedules',
          query: _query(
              {'project_id': projectId, 'after': after, 'limit': limit}));

  /// `PATCH /v1/capacity/schedules/{schedule_id}`: pauses, resumes or deletes
  /// a schedule.
  ///
  /// [state] is `active`, `paused` or `deleted`. [expectedVersion] is the
  /// version you last read, so another person's change is not overwritten:
  /// a conflict error names the current version.
  Future<Map<String, dynamic>> updateCapacitySchedule(
    String scheduleId, {
    required int expectedVersion,
    required String state,
  }) {
    if (!const {'active', 'paused', 'deleted'}.contains(state)) {
      throw ArgumentError.value(
          state, 'state', 'Use active, paused or deleted');
    }
    if (expectedVersion < 1) {
      throw ArgumentError.value(expectedVersion, 'expectedVersion',
          'Use the version you last read (1 or more)');
    }
    return _request(
        'PATCH', '/v1/capacity/schedules/${_segment(scheduleId, 'scheduleId')}',
        body: {'expected_version': expectedVersion, 'state': state});
  }

  /// `GET /v1/capacity/schedules/{schedule_id}/occurrences`: the past runs of
  /// a schedule, newest first. Page with [before].
  Future<Map<String, dynamic>> listCapacityOccurrences(String scheduleId,
          {String? before, int? limit}) =>
      _request('GET',
          '/v1/capacity/schedules/${_segment(scheduleId, 'scheduleId')}/occurrences',
          query: _query({'before': before, 'limit': limit}));

  /// `POST /v1/capacity/schedules/{schedule_id}/run`: runs a schedule now,
  /// within the limits it was approved with.
  Future<Map<String, dynamic>> runCapacityScheduleNow(String scheduleId) =>
      _request('POST',
          '/v1/capacity/schedules/${_segment(scheduleId, 'scheduleId')}/run');

  /// Frees the connection this client opened. A client passed in as
  /// `httpClient` stays open: its owner closes it.
  void close() {
    if (_ownsHttp) _http.close();
  }

  /// Never shows the key.
  @override
  String toString() => 'SpecStream(baseUrl: $baseUrl)';

  static String _segment(String value, String name) {
    if (value.trim().isEmpty) {
      throw ArgumentError.value(value, name, 'An identity is required');
    }
    return Uri.encodeComponent(value);
  }

  static Map<String, String>? _query(Map<String, Object?> values) {
    final pairs = <String, String>{
      for (final entry in values.entries)
        if (entry.value != null) entry.key: '${entry.value}',
    };
    return pairs.isEmpty ? null : pairs;
  }

  static Uri _parseBase(String baseUrl) {
    final text = baseUrl.trim().isEmpty ? defaultBaseUrl : baseUrl.trim();
    final uri = Uri.tryParse(text);
    if (uri == null ||
        uri.host.isEmpty ||
        !(uri.isScheme('https') || uri.isScheme('http'))) {
      throw ArgumentError.value(
          baseUrl, 'baseUrl', 'Use an http or https address');
    }
    return uri;
  }

  Uri _uri(String path, Map<String, String>? query) {
    var prefix = _base.path;
    while (prefix.endsWith('/')) {
      prefix = prefix.substring(0, prefix.length - 1);
    }
    return _base.replace(path: '$prefix$path', queryParameters: query);
  }

  Future<http.Response> _send(String method, Uri uri, String? payload) async {
    final request = http.Request(method, uri)
      ..followRedirects = false
      ..headers['Authorization'] = _apiKey.toLowerCase().startsWith('bearer ')
          ? _apiKey
          : 'Bearer $_apiKey'
      ..headers['Accept'] = 'application/json'
      ..headers['User-Agent'] = 'specstream-dart/$packageVersion';
    if (payload != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = payload;
    }
    return http.Response.fromStream(await _http.send(request));
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, String>? query,
    Object? body,
  }) async {
    final what = '$method $path';
    final String? payload;
    try {
      payload = body == null ? null : jsonEncode(body);
    } on JsonUnsupportedObjectError {
      throw ArgumentError(
          'The request body must be JSON: maps, lists, strings, numbers, booleans and null');
    }
    http.Response response;
    try {
      final uri = _uri(path, query);
      response = await _send(method, uri, payload).timeout(timeout);
      final wait = _retryAfter(response);
      if (wait != null) {
        // The server did nothing and names when to ask again: ask once more.
        await _sleep(wait);
        response = await _send(method, uri, payload).timeout(timeout);
      }
    } on TimeoutException {
      throw SpecStreamException('$what timed out after ${timeout.inSeconds} s');
    } catch (error) {
      // Only the kind of failure: a transport message can repeat the request.
      throw SpecStreamException(
          '$what transport failed (${error.runtimeType})');
    }
    return _parse(what, response);
  }

  Map<String, dynamic> _parse(String what, http.Response response) {
    final status = response.statusCode;
    final ok = status >= 200 && status <= 299;
    final text = utf8.decode(response.bodyBytes, allowMalformed: true);
    Object? loaded;
    try {
      loaded = jsonDecode(text);
    } on FormatException {
      throw SpecStreamException(
        ok ? '$what returned invalid JSON' : '$what failed with HTTP $status',
        status: status,
        body: text,
      );
    }
    if (!ok) {
      throw SpecStreamException('$what failed with HTTP $status',
          status: status, body: loaded);
    }
    if (loaded is! Map<String, dynamic> ||
        loaded['error'] != null ||
        loaded['data'] is! Map<String, dynamic>) {
      throw SpecStreamException('$what returned an invalid success envelope',
          status: status, body: loaded);
    }
    return loaded['data'] as Map<String, dynamic>;
  }

  Duration? _retryAfter(http.Response response) {
    if (response.statusCode != 503) return null;
    final value = response.headers['retry-after']?.trim() ?? '';
    final seconds = double.tryParse(value);
    if (seconds == null || seconds.isNaN || seconds < 0) return null;
    final wait = Duration(milliseconds: (seconds * 1000).round());
    return wait <= _retryAfterMax ? wait : null;
  }
}
