using System;
using System.Text.Json.Serialization;
using Newtonsoft.Json;

namespace WeChatAuto.Models;

/// <summary>
/// 千问 TTS 响应结果
/// </summary>
public sealed class QwenResponseBody
{
    [JsonPropertyName("status_code")]
    public int StatusCode { get; set; }

    [JsonPropertyName("request_id")]
    public string RequestId { get; set; }

    [JsonPropertyName("code")]
    public string Code { get; set; }

    [JsonPropertyName("message")]
    public string Message { get; set; }

    [JsonPropertyName("output")]
    public OutputInfo Output { get; set; }

    [JsonPropertyName("usage")]
    public UsageInfo Usage { get; set; }
}

public sealed class OutputInfo
{
    [JsonPropertyName("text")]
    public string Text { get; set; } = null;

    [JsonPropertyName("choices")]
    public object Choices { get; set; } = null;

    [JsonPropertyName("finish_reason")]
    public string FinishReason { get; set; }

    [JsonPropertyName("audio")]
    public AudioInfo Audio { get; set; }
}

public sealed class AudioInfo
{
    [JsonPropertyName("url")]
    public string Url { get; set; }

    [JsonPropertyName("data")]
    public string Data { get; set; }

    [JsonPropertyName("id")]
    public string Id { get; set; }

    /// <summary>
    /// Unix 时间戳（秒）
    /// </summary>
    [JsonPropertyName("expires_at")]
    public long ExpiresAt { get; set; }

    /// <summary>
    /// 过期时间
    /// </summary>
    [System.Text.Json.Serialization.JsonIgnore]
    public DateTimeOffset ExpireTime =>
        DateTimeOffset.FromUnixTimeSeconds(ExpiresAt);
}

public sealed class UsageInfo
{
    [JsonPropertyName("input_tokens")]
    public int InputTokens { get; set; }

    [JsonPropertyName("output_tokens")]
    public int OutputTokens { get; set; }

    [JsonPropertyName("total_tokens")]
    public int TotalTokens { get; set; }

    [JsonPropertyName("characters")]
    public int Characters { get; set; }

    [JsonPropertyName("input_tokens_details")]
    public InputTokensDetails InputTokensDetails { get; set; }

    [JsonPropertyName("output_tokens_details")]
    public OutputTokensDetails OutputTokensDetails { get; set; }
}

public sealed class InputTokensDetails
{
    [JsonPropertyName("text_tokens")]
    public int TextTokens { get; set; }
}

public sealed class OutputTokensDetails
{
    [JsonPropertyName("audio_tokens")]
    public int AudioTokens { get; set; }

    [JsonPropertyName("text_tokens")]
    public int TextTokens { get; set; }
}