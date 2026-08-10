using System;
using FlaUI.Core.Capturing;
using System.IO;
using WeChatAuto.Services;
using System.Linq;
using FlaUI.Core;

namespace WeChatAuto.Utils
{
    /// <summary>
    /// RuntimeId的扩展
    /// </summary>
    public static class RuntimeIDExtensions
    {
        public static string ToUniqueString(this AutomationProperty<int[]> runtimeId)
        {
            var aryRuntimeId = runtimeId.Value;
            return string.Join("-",aryRuntimeId);
        }
    }
}