using System;
using Newtonsoft.Json;

namespace WeChatAuto.Models
{
    /// <summary>
    /// 时间范围，即定义：开始时间与结束时间
    /// </summary>
    public class TimeOnlyRange
    {
        /// <summary>
        /// 开始时间
        /// </summary>
        [JsonProperty("star_time")]
        public TimeOnly StarTime { get; set; }
        /// <summary>
        /// 结束时间
        /// </summary>
        [JsonProperty("end_time")]
        public TimeOnly EndTime { get; set; }

        public override string ToString()
        {
            return $"{StarTime.ToString("HH:mm:ss")} - {EndTime.ToString("HH:mm:ss")}";
        }
    }

}