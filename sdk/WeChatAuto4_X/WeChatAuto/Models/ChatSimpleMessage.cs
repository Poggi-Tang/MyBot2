using System;
using System.Globalization;
using System.Text.Json.Serialization;
using Newtonsoft.Json;

namespace WeChatAuto.Models
{
    public class ChatSimpleMessage
    {
        /// <summary>
        /// 微信名称
        /// </summary>
        [JsonProperty("who")]
        public string Who { get; set; }
        /// <summary>
        /// 消息
        /// </summary>
        [JsonProperty("message")]
        public string Message { get; set; }
        /// <summary>
        /// 消息日期
        /// </summary>
        [JsonProperty("send_date_time")]
        public string SendDateTime { get; set; }
        /// <summary>
        /// 消息日期,日期时间格式
        /// </summary>
        [JsonProperty("date_time")]
        public DateTime DateTime { get; set; }

        /// <summary>
        /// 唯一字符串
        /// </summary>
        [JsonProperty("unique_string")]
        public string UniqueString { get; set; }

        public override string ToString()
        {
            return JsonConvert.SerializeObject(this);
        }
    }
}