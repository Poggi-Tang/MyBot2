using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using FlaUI.Core.AutomationElements;

namespace WeChatAuto.Utils
{
    /// <summary>
    /// AutomationElement比较器，基于runtimeid进行比较
    /// </summary>
    public class AutomationRuntimeComparer : IEqualityComparer<AutomationElement>
    {
        public bool Equals(AutomationElement e1, AutomationElement e2)
        {
            var rt1 = e1.Properties.RuntimeId.Value;
            var rt2 = e2.Properties.RuntimeId.Value;
            if (rt1.Length != rt2.Length)
                return false;
            var result = true;
            for (int i = 0; i < rt1.Length; i++)
            {
                if (rt1[i] != rt2[i])
                {
                    result = false;
                    break;
                }
            }
            return result;
        }

        public int GetHashCode(AutomationElement element)
        {
            var runtime = element.Properties.RuntimeId.Value;
            var runtimeStr = string.Join("-", runtime);

            return runtimeStr.GetHashCode();
        }
    }

    public class AutomationIntArrayComparer : IEqualityComparer<int[]>
    {
        public bool Equals(int[] e1, int[] e2)
        {
            var rt1 = e1;
            var rt2 = e2;
            if (rt1.Length != rt2.Length)
                return false;
            var result = true;
            for (int i = 0; i < rt1.Length; i++)
            {
                if (rt1[i] != rt2[i])
                {
                    result = false;
                    break;
                }
            }
            return result;
        }

        public int GetHashCode(int[] values)
        {
            var runtime = values;
            var runtimeStr = string.Join("-", runtime);

            return runtimeStr.GetHashCode();
        }
    }
}