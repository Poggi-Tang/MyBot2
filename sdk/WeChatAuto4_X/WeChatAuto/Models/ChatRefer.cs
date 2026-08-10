using System;
using System.Text.Json.Serialization;
using Newtonsoft.Json;

namespace WeChatAuto.Models
{
    /// <summary>
    /// 消息引用
    /// </summary>
    public class ChatRefer
    {
        /// <summary>
        /// 日期,如果不设置则不进行日期筛选
        /// </summary>
        [JsonProperty("date")]
        public DateOnly Date { get; set; } = DateOnly.MinValue;
        /// <summary>
        /// 要引入用的内容，具体请参考:<see cref="ChatSimpleMessage"/>
        /// </summary>
        [JsonProperty("message")]
        public ChatSimpleMessage Message { get; set; }
        /// <summary>
        /// 是否关闭查找窗口，默认是关闭，如果设置为false,则不关闭查找窗口，速度会略快，但需要自行关闭查找窗口.
        /// </summary>
        [JsonProperty("is_close_search_win")]
        public bool IsCloseSearchWin { get; set; } = true;
    }
}