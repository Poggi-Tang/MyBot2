using FlaUI.Core.AutomationElements;
using WeAutoCommon.Enums;
using Newtonsoft.Json;

namespace WeAutoCommon.Models
{
    /// <summary>
    /// 会话
    /// </summary>
    public class Conversation
    {
        /// <summary>
        /// 会话类型
        /// </summary>
        public ConversationType ConversationType { get; set; }
        /// <summary>
        /// 会话标题
        /// </summary>
        public string ConversationTitle { get; set; }
        /// <summary>
        /// 会话内容
        /// </summary>
        public string ConversationContent { get; set; }

        /// <summary>
        /// 是否是企业群
        /// </summary>
        public bool IsCompanyGroup { get; set; } = false;
        /// <summary>
        /// 会话头像按钮
        /// </summary>
        public Button ImageButton { get; set; }
        /// <summary>
        /// 是否有未读消息
        /// </summary>
        public bool HasNotRead { get; set; } = false;
        /// <summary>
        /// 会话时间
        /// </summary>
        public string Time { get; set; }
        /// <summary>
        /// 是否免打扰
        /// </summary>
        public bool IsDoNotDisturb { get; set; } = false;  //是否免打扰

        /// <summary>
        /// 是否置顶
        /// </summary>
        public bool IsTop { get; set; } = false;

        public override string ToString()
        {
            // 创建一个匿名对象来避免循环引用
            var serializableObject = new
            {
                ConversationType = this.ConversationType.ToString(),
                ConversationTitle = this.ConversationTitle,
                ConversationContent = this.ConversationContent,
                IsCompanyGroup = this.IsCompanyGroup,
                HasNotRead = this.HasNotRead,
                Time = this.Time,
                IsDoNotDisturb = this.IsDoNotDisturb,
                IsTop = this.IsTop,
            };

            return JsonConvert.SerializeObject(serializableObject, Formatting.Indented);
        }
    }
    /// <summary>
    /// 简单的会话对象，因为我们无须关注那些临时信息
    /// </summary>
    public class SimpleConversation
    {
        /// <summary>
        /// 会话标题
        /// </summary>
        [JsonProperty("conversation_title")]
        public string ConversationTitle { get; set; }

        /// <summary>
        /// 是否免打扰
        /// </summary>
        [JsonProperty("is_do_not_disturb")]
        public bool IsDoNotDisturb { get; set; } = false;  //是否免打扰

        /// <summary>
        /// 是否置顶
        /// </summary>
        [JsonProperty("is_top")]
        public bool IsTop { get; set; } = false;
        /// <summary>
        /// 未读消息数
        /// </summary>
        [JsonProperty("not_read_numbr")]
        public int NotReadNumbr { get; set; } = 0;

        /// <summary>
        /// 会话列表中显示的最后一条消息预览。
        /// </summary>
        [JsonProperty("conversation_content")]
        public string ConversationContent { get; set; } = string.Empty;

        /// <summary>
        /// 会话列表中显示的最后消息时间。
        /// </summary>
        [JsonProperty("time")]
        public string Time { get; set; } = string.Empty;

        public override string ToString()
        {
            return JsonConvert.SerializeObject(this);
        }

    }


}
