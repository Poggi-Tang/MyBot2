

using Newtonsoft.Json;

namespace WeChatAuto.Models
{
    /// <summary>
    /// 个人信息
    /// </summary>
    public class OwerInfo
    {
        /// <summary>
        /// 微信昵称
        /// </summary>
        [JsonProperty("nick_name")]
        public string NickName { get; set; }
        /// <summary> 
        /// 微信号
        /// </summary>
        [JsonProperty("wx_id")]
        public string WxId { get; set; }
        /// <summary>
        /// 头像路径
        /// </summary>
        [JsonProperty("avator_path")]
        public string AvatorPath { get; set; }
    }
}