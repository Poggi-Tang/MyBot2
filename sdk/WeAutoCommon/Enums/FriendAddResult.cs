using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using System.Linq;
using OneOf;

namespace WeAutoCommon.Enums
{
    /// <summary>
    /// 通过wxid查询，或者通过手机号查询结果枚举
    /// </summary>
    public enum FriendAddResult
    {
        [Description("已是好友")]
        Friend = 0,
        [Description("不允许被查询，或者通过手机号查询不到")]
        No_Find = 1,
        [Description("增加中,需对方通过验证")]
        Adding = 2,
        [Description("一增加就通过，可能以前增加后自己又删除，或者对方设置权限允许通过")]
        Added = 3,
        [Description("由于对方在群里的隐私设置，不允许添加")]
        PrivacyRestricted = 4,
    }
}
