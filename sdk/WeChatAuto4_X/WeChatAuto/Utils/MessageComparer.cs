using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.InteropServices;
using System.Text;
using FlaUI.Core.AutomationElements;
using WeChatAuto.Models;

namespace WeChatAuto.Utils
{
    /// <summary>
    /// 消息是否相等比较器
    /// </summary>
    public class MessageComparer : IEqualityComparer<SimpleMessageBubble>
    {
        public bool Equals(SimpleMessageBubble x, SimpleMessageBubble y)
        {
            if (x == null || x == y)
                return false;
            if (x.Message == y.Message && x.Who == y.Who)
            {
                return true;
            }
            return false;
        }

        public int GetHashCode([DisallowNull] SimpleMessageBubble obj)
        {
            return $"{obj.Who}-{obj.Message}".GetHashCode();
        }
    }
}