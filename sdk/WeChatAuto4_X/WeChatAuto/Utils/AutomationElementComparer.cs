using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using FlaUI.Core.AutomationElements;

namespace WeChatAuto.Utils
{
    /// <summary>
    /// AutomationElement比较器，基于名称进行比较，不考虑重复名称的情况
    /// </summary>
    public class AutomationElementComparer : IEqualityComparer<AutomationElement>
    {
        public bool Equals(AutomationElement x, AutomationElement y)
        {
            if (x == null || y == null)
                return false;

            return x.Name == y.Name;
        }

        public int GetHashCode(AutomationElement obj)
        {
            return obj.Name.GetHashCode();
        }
    }
}