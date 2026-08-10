using System.Collections.Generic;
using System.Threading.Tasks;
using Newtonsoft.Json;
using WeAutoCommon.Enums;

namespace WeAutoCommon.Models
{
    /// <summary>
    /// 标题信息
    /// </summary>
    public class HeaderInfo
    {
        /// <summary>
        /// 标题,也就是好友/群聊名称
        /// </summary>
        [JsonProperty("title")]
        public string Title { get; set; }
        /// <summary>
        /// 标题类型,<seealso cref="ChatType"/>
        /// </summary>
        [JsonProperty("header_type")]
        public ChatType HeaderType { get; set; } = ChatType.其他;
        /// <summary>
        /// 如果HeaderType是ChatType.群聊,则显示群聊人数数量，如果不是群聊，这里的数量恒为1
        /// </summary>
        [JsonProperty("chat_number")]
        public int ChatNumber { get; set; } = 1;

        /// <summary>
        /// 是否是可以聊天类型
        /// </summary>
        /// <returns></returns>
        public bool CanTalk() => this.HeaderType == ChatType.好友 || this.HeaderType == ChatType.企业微信 || this.HeaderType == ChatType.群聊;

        public override string ToString()
        {
            return $"Title={this.Title} - HeaderType={this.HeaderType.ToString()} - ChatNumber={this.ChatNumber.ToString()}";
        }
    }
}