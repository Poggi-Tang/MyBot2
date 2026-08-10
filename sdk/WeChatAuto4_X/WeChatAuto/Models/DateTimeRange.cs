using System.Collections.Generic;

namespace WeChatAuto.Models
{
    /// <summary>
    /// 日期时间范围
    /// </summary>
    internal class DateTimeRange
    {
        /// <summary>
        /// 是否检查日期
        /// </summary>
        public bool IsCheckDate { get; set; } = false;
        /// <summary>
        /// 时间段列表
        /// </summary>
        public List<TimeOnlyRange> TimeList { get; set; }
    }

}