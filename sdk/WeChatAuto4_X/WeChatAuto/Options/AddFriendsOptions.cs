using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using OneOf;
using WeChatAuto.Components;
using WeChatAuto.Models;

namespace WeChatAuto.Options
{
    /// <summary>
    /// 增加朋友选项
    /// </summary>
    public class AddFriendsOptions
    {
        /// <summary>
        /// 间隔时间,以秒为单位，默认为三秒，如果担心风控，可以把此时间设置长一点
        /// </summary>
        [JsonProperty("interval_time")]
        public int IntervalTime { get; set; } = 5;
        /// <summary>
        /// 是否关闭增加朋友窗口,默认关闭，可以设置为false不关闭
        /// </summary>
        [JsonProperty("is_close_win")]
        public bool IsCloseWin { get; set; } = true;

        /// <summary>
        /// 加好友时打招呼内容,如果为空，则保持微信默认
        /// </summary>
        [JsonProperty("say_hi")]
        public string SayHi { get; set; }

        /// <summary>
        /// 备注后缀，如：设置suffix为"test",则备注为:xxxx_test,可以未来以备注的后缀来区分不同的好友分类
        /// </summary>
        [JsonProperty("suffix")]
        public string Suffix { get; set; }

        /// <summary>
        /// 设置标签
        /// </summary>
        [JsonProperty("label")]
        public string Label { get; set; }
    }
}