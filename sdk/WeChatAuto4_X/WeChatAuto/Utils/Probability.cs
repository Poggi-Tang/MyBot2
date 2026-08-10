using System;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Input;
using WeAutoCommon.Configs;
using WeAutoCommon.Models;
using WeAutoCommon.Utils;
using WeChatAuto.Components;
using WeChatAuto.Services;

namespace WeChatAuto.Utils
{
    /// <summary>
    /// 随机决策
    /// </summary>
    public static class Probability
    {
        public static bool Hit(double probability)
        {
            if (probability < 0 || probability > 1)
                throw new ArgumentOutOfRangeException(nameof(probability));

            return Random.Shared.NextDouble() < probability;
        }
    }

}