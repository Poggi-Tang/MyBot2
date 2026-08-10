using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
using FlaUI.Core.AutomationElements;
using WeAutoCommon.Utils;

namespace WeChatAuto.Utils
{
    public static class AutoWaiting
    {
        public static void Stability(this AutomationElement element)
        {
            Rectangle last = Rectangle.Empty;
            int stableCount = 0;

            while (stableCount < 3)
            {
                var rect = element.BoundingRectangle;

                if (rect == last)
                    stableCount++;
                else
                    stableCount = 0;

                last = rect;

                RandomWait.Wait(50,200);
            }
        }
    }
}