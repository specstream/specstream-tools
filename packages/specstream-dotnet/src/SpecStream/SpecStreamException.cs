using System;
using System.Text.Json;

namespace SpecStream
{
    /// <summary>A failed SpecStream call: the HTTP status, the API's error code and the answer it sent.</summary>
    public sealed class SpecStreamException : Exception
    {
        /// <summary>Creates the error. <paramref name="status"/> is 0 when no answer arrived.</summary>
        public SpecStreamException(string message, int status = 0, JsonElement? body = null, string? rawBody = null, Exception? inner = null)
            : base(message, inner)
        {
            Status = status;
            Body = body;
            RawBody = rawBody;
            if (body is JsonElement b && b.ValueKind == JsonValueKind.Object
                && b.TryGetProperty("error", out var error) && error.ValueKind == JsonValueKind.Object)
            {
                if (error.TryGetProperty("code", out var code) && code.ValueKind == JsonValueKind.String)
                {
                    Code = code.GetString();
                }
                if (error.TryGetProperty("details", out var details))
                {
                    Details = details.Clone();
                }
            }
        }

        /// <summary>The HTTP status, or 0 when the request never got an answer.</summary>
        public int Status { get; }

        /// <summary>The API's error code, for example <c>quote_expired</c>, when it sent one.</summary>
        public string? Code { get; }

        /// <summary>The API's error details, when it sent them.</summary>
        public JsonElement? Details { get; }

        /// <summary>The whole JSON answer, when the answer was JSON.</summary>
        public JsonElement? Body { get; }

        /// <summary>The answer's text when it was not JSON.</summary>
        public string? RawBody { get; }
    }
}
