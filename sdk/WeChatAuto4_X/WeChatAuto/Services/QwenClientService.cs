using System;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using WeChatAuto.Models;
using WeChatAuto.Options;

namespace WeChatAuto.Services;

/// <summary>
/// 千问http客户端
/// </summary>
public class QwenClientService
{
    private readonly HttpClient _http;

    public QwenClientService(HttpClient http)
    {
        _http = http;
        _http.Timeout = TimeSpan.FromSeconds(30);
        _http.DefaultRequestHeaders.Add("User-Agent", "WeChatAuto.SDK");

    }

    /// <summary>
    /// 封装千问python api的MultiModalConversation.Call方法
    /// </summary>
    /// <param name="apiKey">千问的api key</param>
    /// <param name="message">转语音的文字内容</param>
    /// <param name="options">文字转语音的控制选项，详情请参见<see cref="VoiceOptions"/></param>
    /// <param name="isOptimize">文字message是否在进行tts前用LLM进行优化</param>
    /// <returns>文字转语音结束后的本地文件</returns>
    public async Task<string> MultiModalConversationCall(string apiKey, string message, VoiceOptions options = null, bool isOptimize = false)
    {
        _ = string.IsNullOrWhiteSpace(apiKey) ? throw new Exception("错误：apiKey不能为空！") : "";
        options = options == null ? new VoiceOptions() : options;
        //检查音色是否为系统包含的音色
        if (!VoicePresetList.AllVoicePresets.Any(x => x.Id.Equals(options.Voice)))
            throw new Exception($"错误：传入的音色 {options.Voice}不存在！");
        var url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation";
        var httpRequest = new HttpRequestMessage(HttpMethod.Post, url);
        httpRequest.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", apiKey);
        //获取发送json字符串
        var inputJson = _GetInputJson(options, message);
        StringContent content = new StringContent(inputJson, Encoding.UTF8, "application/json");
        httpRequest.Content = content;
        var response = await _http.SendAsync(httpRequest);
        if (response.IsSuccessStatusCode)
        {
            var resultStr = await response.Content.ReadAsStringAsync();
            var result = JsonConvert.DeserializeObject<QwenResponseBody>(resultStr);
            var remoteUrl = result.Output.Audio.Url;
            //下载文件
            var path = Path.Join(AppContext.BaseDirectory, "Temp");
            if (!Directory.Exists(path))
            {
                Directory.CreateDirectory(path);
            }
            var localFileName = Path.Join(path, Guid.NewGuid().ToString("N").ToString() + ".wav");
            using var fileResponse = await _http.GetAsync(remoteUrl, HttpCompletionOption.ResponseHeadersRead);
            fileResponse.EnsureSuccessStatusCode();
            await using var httpStream = await fileResponse.Content.ReadAsStreamAsync();
            await using var fileStream = File.Create(localFileName);
            await httpStream.CopyToAsync(fileStream);
            await Task.Delay(1000);
            return localFileName;
        }
        else
        {
            throw new HttpRequestException($"请求发生错误，错误代码:{response.StatusCode}");
        }
    }

    private string _GetInputJson(VoiceOptions options, string message)
    {
        var result = new QwenRequestBody();
        var model = string.IsNullOrWhiteSpace(options.Instructions) ? "qwen3-tts-flash" : "qwen3-tts-instruct-flash";
        var flashModels = new string[] { "Bodega", "Sonrisa", "Alek", "Dolce", "Sohee", "Ono Anna", "Lenn", "Emilien", "Andre", "Radio Gol", "Jada", "Dylan", "Li", "Marcus", "Roy", "Peter", "Sunny", "Eric", "Rocky", "Kiki" };
        result.Model = model;
        if (flashModels.Contains(options.Voice))
        {
            result.Model = "qwen3-tts-flash";
        }
        var input = new RequestInput();
        input.Text = message;
        input.Voice = options.Voice;
        input.LanguageType = options.LanguageType;
        input.Instructions = options.Instructions;
        input.OptimizeInstructions = options.OptimizeInstructions;
        input.Stream = options.IsStream;
        result.Input = input;
        return JsonConvert.SerializeObject(result);
    }
}