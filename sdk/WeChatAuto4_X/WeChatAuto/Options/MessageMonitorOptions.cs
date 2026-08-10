using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using OneOf;
using WeAutoCommon.Utils;
using WeChatAuto.Components;
using WeChatAuto.Models;
using FlaUI.Core.AutomationElements;
using Newtonsoft.Json;

namespace WeChatAuto.Options
{
    /// <summary>
    /// 消息监听器选项.
    /// </summary>
    public class MessageMonitorOptions
    {
        /// <summary>
        /// 如果此好友在缓存中不存在，是否获取此好友的用户信息(包括wxid),并更新缓存，对于基于wxid的企业级开发很有用
        /// </summary>
        [JsonProperty("fetch_friend_info")]
        public bool FetchFriendInfo { get; set; } = false;

        /// <summary>
        /// 如果聊天记录中有图片，是否获取图片
        /// </summary>
        [JsonProperty("fetch_image")]
        public bool FetchImage { get; set; } = false;

        /// <summary>
        /// 如果聊天记录中有文件，是否查找微信已下载的本地文件路径。
        /// </summary>
        [JsonProperty("fetch_file")]
        public bool FetchFile { get; set; } = false;

        /// <summary>
        /// 收到文件后通过微信“另存为”保存到此目录。SDK 会按会话创建私有 inbox。
        /// </summary>
        [JsonProperty("file_save_directory")]
        public string FileSaveDirectory { get; set; } = string.Empty;

        /// <summary>
        /// 如果聊天记录有微信语音，则取出微信语音的内容，这个依赖微信的设置: 设置 --> 通用 --> 打开"聊天中的语音消息自动转成文字"
        /// </summary>
        [JsonProperty("fetch_voice_chat")]
        public bool FetchVoiceChat {get;set;} = false;
        /// <summary>
        /// 如果聊天记录中有红包、转账，是否点击
        /// </summary>
        [JsonProperty("click_red_envelope")]
        public bool ClickRedEnvelope { get; set; } = false;

        /// <summary>
        /// 手动处理消息，SDK只默认处理了文字消息、微信语音、图片消息、红包/转账消息，其他的消息可以自行处理，如：自行处理打开链接抓取链接内容等.
        /// </summary>
        public Action<AutomationElement,SimpleMessageBubble> CustomProcessMessageAction = null;

        /// <summary>
        /// 是否预防风控,如果待监控的群不多，建议设置为False,如果监测的群/好友很多，并且聊天很频繁，建议将设置为True.
        /// 因为人不可能一天24小时进行操作的,否则极易被微信风控退出。
        /// </summary>
        [JsonProperty("is_risk_prevention")]
        public bool IsRiskPrevention { get; set; } = false;

        /// <summary>
        /// 是否轮询指定监听对象中已读的会话。默认监听只处理未读会话；启用后可
        /// 在用户正打开会话导致消息立即标记为已读时，仍然检测新的聊天气泡。
        /// 仅对固定对象监听生效，开放式监听不使用此选项。
        /// </summary>
        [JsonProperty("monitor_read_conversations")]
        public bool MonitorReadConversations { get; set; } = false;

        /// <summary>
        /// 预防风控方法
        /// 如果上面IsRiskPrevention设置为True,则预防风控方法生效，预设预防风控行为是等候一段时间，你也可以覆盖此方法，加入更多不可预测行为.
        /// 如：你可以加入随机与某人聊一句，或者运行其他的方法，甚至晚上一段时间停止等
        /// 触发时间：运4行6-10分钟之内的某个随机时间触发
        /// 预防风控方法运行时，消息监听会暂停，预防风控方法运行结束，消息监听继续.
        /// </summary>
        public Func<WeChatClient,Task> RiskPreventionAction { get; set; } = async client =>
        {
            await RandomWait.WaitAsync(60 * 1_000, 3 * 60 * 1_000);  //随机等候1..3分钟.
        };
    }
}
