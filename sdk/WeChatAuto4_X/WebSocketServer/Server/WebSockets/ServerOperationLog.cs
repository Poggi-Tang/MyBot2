using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;

internal static class ServerOperationLog
{
    private static readonly object Sync = new();
    private static readonly JsonSerializerOptions JsonOptions = new() {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping
    };
    private static readonly string[] SensitiveKeys = {
        "api_key", "authorization", "password", "secret", "token",
        "upload", "base64", "b64_json", "image_base64", "audio_data"
    };

    public static void Started(MessagePackageWrapper wrapper)
    {
        Write(new Dictionary<string, object?> {
            ["timestamp"] = DateTimeOffset.Now.ToString("O"),
            ["event"] = "started",
            ["operation_id"] = wrapper.RequestId,
            ["layer"] = "server",
            ["operation"] = wrapper.FuncName,
            ["account"] = wrapper.FromWechat,
            ["options"] = SummarizePayload(wrapper.Options, "options")
        });
    }

    public static void Finished(
        MessagePackageWrapper wrapper,
        Stopwatch stopwatch,
        bool success,
        string? result = null,
        Exception? error = null)
    {
        Write(new Dictionary<string, object?> {
            ["timestamp"] = DateTimeOffset.Now.ToString("O"),
            ["event"] = "finished",
            ["operation_id"] = wrapper.RequestId,
            ["layer"] = "server",
            ["operation"] = wrapper.FuncName,
            ["account"] = wrapper.FromWechat,
            ["success"] = success,
            ["duration_ms"] = Math.Round(stopwatch.Elapsed.TotalMilliseconds, 3),
            ["result"] = SummarizePayload(result, "result"),
            ["error"] = error == null ? null : SummarizeText(error.ToString(), "error")
        });
    }

    public static void Expired(MessagePackageWrapper wrapper, string phase)
    {
        Write(new Dictionary<string, object?> {
            ["timestamp"] = DateTimeOffset.Now.ToString("O"),
            ["event"] = "expired_command_discarded",
            ["operation_id"] = wrapper.RequestId,
            ["layer"] = "server",
            ["operation"] = wrapper.FuncName,
            ["account"] = wrapper.FromWechat,
            ["phase"] = phase,
            ["expires_at_unix_ms"] = wrapper.ExpiresAtUnixMs,
            ["success"] = false
        });
    }

    public static void WindowWatchdog(
        string account,
        int processId,
        IntPtr handle,
        bool stateKnown,
        bool wasVisible,
        bool wasMinimized,
        bool success,
        bool isVisible,
        bool isMinimized,
        int consecutiveFailures,
        Stopwatch stopwatch,
        Exception? error = null)
    {
        Write(new Dictionary<string, object?> {
            ["timestamp"] = DateTimeOffset.Now.ToString("O"),
            ["event"] = success ? "window_restored" : "window_restore_failed",
            ["operation_id"] = Guid.NewGuid().ToString("N"),
            ["layer"] = "server",
            ["operation"] = "WeChatWindowWatchdog",
            ["account"] = account,
            ["process_id"] = processId,
            ["handle"] = handle.ToInt64(),
            ["state_known"] = stateKnown,
            ["prior_visible"] = wasVisible,
            ["prior_minimized"] = wasMinimized,
            ["visible"] = isVisible,
            ["minimized"] = isMinimized,
            ["consecutive_failures"] = consecutiveFailures,
            ["success"] = success,
            ["duration_ms"] = Math.Round(stopwatch.Elapsed.TotalMilliseconds, 3),
            ["error"] = error == null ? null : SummarizeText(error.ToString(), "error")
        });
    }

    private static object? SummarizePayload(string? payload, string key)
    {
        if (string.IsNullOrEmpty(payload))
            return payload ?? "";
        try
        {
            using var document = JsonDocument.Parse(payload);
            return SummarizeElement(document.RootElement, key, 0);
        }
        catch (JsonException)
        {
            return SummarizeText(payload, key);
        }
    }

    private static object? SummarizeElement(JsonElement element, string key, int depth)
    {
        if (depth > 6)
            return new Dictionary<string, object?> { ["truncated"] = true, ["reason"] = "max_depth" };
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                var result = new Dictionary<string, object?>();
                foreach (var property in element.EnumerateObject())
                    result[property.Name] = SummarizeElement(property.Value, property.Name, depth + 1);
                return result;
            case JsonValueKind.Array:
                var items = new List<object?>();
                var index = 0;
                foreach (var item in element.EnumerateArray())
                {
                    if (index++ >= 20)
                    {
                        items.Add(new Dictionary<string, object?> { ["truncated"] = true });
                        break;
                    }
                    items.Add(SummarizeElement(item, key, depth + 1));
                }
                return items;
            case JsonValueKind.String:
                return SummarizeText(element.GetString() ?? "", key);
            case JsonValueKind.Number:
                return element.TryGetInt64(out var integer) ? integer : element.GetDouble();
            case JsonValueKind.True:
                return true;
            case JsonValueKind.False:
                return false;
            case JsonValueKind.Null:
            case JsonValueKind.Undefined:
                return null;
            default:
                return SummarizeText(element.ToString(), key);
        }
    }

    private static object SummarizeText(string value, string key)
    {
        var lowered = key.ToLowerInvariant();
        var digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))[..16];
        if (SensitiveKeys.Any(lowered.Contains)
            || value.StartsWith("data:", StringComparison.OrdinalIgnoreCase)
                && value[..Math.Min(value.Length, 120)].Contains(";base64,", StringComparison.OrdinalIgnoreCase))
        {
            return new Dictionary<string, object?> {
                ["redacted"] = true,
                ["length"] = value.Length,
                ["sha256"] = digest
            };
        }
        if (value.Length > 600)
        {
            return new Dictionary<string, object?> {
                ["length"] = value.Length,
                ["sha256"] = digest,
                ["preview"] = value[..240]
            };
        }
        return value;
    }

    private static void Write(Dictionary<string, object?> entry)
    {
        try
        {
            lock (Sync)
            {
                var directory = Path.Combine(AppContext.BaseDirectory, "logs");
                Directory.CreateDirectory(directory);
                var path = Path.Combine(directory, $"server-operations-{DateTime.Now:yyyyMMdd}.jsonl");
                File.AppendAllText(path, JsonSerializer.Serialize(entry, JsonOptions) + Environment.NewLine, Encoding.UTF8);
            }
        }
        catch
        {
            // Operation logging must never break the requested SDK action.
        }
    }
}
