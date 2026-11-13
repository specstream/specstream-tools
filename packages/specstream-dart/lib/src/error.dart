import 'dart:convert';

/// Thrown for every failed call: a refused request, a transport failure, or a
/// reply that is not the API's `{"data": {...}}` envelope.
class SpecStreamException implements Exception {
  /// What failed, without the API key.
  final String message;

  /// The HTTP status, when the server answered.
  final int? status;

  /// The reply as received: decoded JSON when it was JSON, else the text.
  final Object? body;

  /// `error.code` of the API's reply, when it has one.
  final String? code;

  /// `error.details` of the API's reply; empty when it has none.
  final Map<String, dynamic> details;

  SpecStreamException._(
      this.message, this.status, this.body, this.code, this.details);

  factory SpecStreamException(String message, {int? status, Object? body}) {
    Object? parsed = body;
    if (parsed is String) {
      try {
        parsed = jsonDecode(parsed);
      } on FormatException {
        parsed = null;
      }
    }
    String? code;
    var details = const <String, dynamic>{};
    if (parsed is Map && parsed['error'] is Map) {
      final error = parsed['error'] as Map;
      if (error['code'] is String) code = error['code'] as String;
      if (error['details'] is Map) {
        details = Map<String, dynamic>.from(error['details'] as Map);
      }
    }
    return SpecStreamException._(message, status, body, code, details);
  }

  @override
  String toString() {
    final parts = [
      if (status != null) 'HTTP $status',
      if (code != null) code!,
    ];
    return 'SpecStreamException: $message${parts.isEmpty ? '' : ' (${parts.join(', ')})'}';
  }
}
