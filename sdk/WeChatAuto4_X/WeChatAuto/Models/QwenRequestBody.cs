using Newtonsoft.Json;

namespace WeChatAuto.Models;

public class QwenRequestBody
{
    /// <summary>
    /// 模型名称
    /// </summary>
    [JsonProperty("model")]
    public string Model { get; set; }
    /// <summary>
    /// 语音合成的输入参数。
    /// </summary>
    [JsonProperty("input")]
    public RequestInput Input { get; set; }

}

public class RequestInput
{
    /// <summary>
    /// 待合成的文本内容，支持多语言混合输入。Qwen-TTS 最大支持 512 tokens 输入，其他模型最大支持 600 个字符。
    /// </summary>
    [JsonProperty("text")]
    public string Text { get; set; }
    [JsonProperty("voice")]
    public string Voice { get; set; }
    [JsonProperty("language_type")]
    public string LanguageType { get; set; } = "Auto";
    [JsonProperty("instructions")]
    public string Instructions { get; set; } = null;
    [JsonProperty("optimize_instructions")]
    public bool OptimizeInstructions { get; set; } = false;
    [JsonProperty("stream")]
    public bool Stream { get; set; } = false;

}