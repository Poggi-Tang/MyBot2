
using System;
using System.Runtime.InteropServices;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.WindowsAPI;
using WeAutoCommon.Configs;
using WeAutoCommon.Models;
using WeAutoCommon.Utils;
using WeChatAuto.Components;
using WeChatAuto.Services;

namespace WeChatAuto.Utils
{
    public static class ElementVisibleHelper
    {
        [DllImport("user32.dll")]
        static extern IntPtr WindowFromPoint(POINT Point);

        [DllImport("user32.dll")]
        static extern IntPtr GetAncestor(
            IntPtr hWnd,
            uint gaFlags);

        const uint GA_ROOT = 2;
        private static bool IsElementVisible(int x, int y, IntPtr wechatMainHandle)
        {
            var hwnd = WindowFromPoint(new POINT()
            {
                X = x,
                Y = y,
            });
            if (hwnd == IntPtr.Zero)
                return false;
            var topHwnd = GetAncestor(hwnd, GA_ROOT);
            return wechatMainHandle == topHwnd;
        }

        /// <summary>
        /// 检查元素是被挡住
        /// </summary>
        /// <param name="element"></param>
        /// <param name="wechatMainHandle"></param>
        /// <returns></returns>
        public static bool IsElementActuallyVisible(this AutomationElement element, IntPtr wechatMainHandle)
        {
            if (element.BoundingRectangle.IsEmpty)
                return false;
            var result = true;
            result = result && IsElementVisible(element.BoundingRectangle.X, element.BoundingRectangle.Y, wechatMainHandle);
            result = result && IsElementVisible(element.BoundingRectangle.X + element.BoundingRectangle.Width, element.BoundingRectangle.Y, wechatMainHandle);
            result = result && IsElementVisible(element.BoundingRectangle.X + element.BoundingRectangle.Width, element.BoundingRectangle.Y + element.BoundingRectangle.Height, wechatMainHandle);
            result = result && IsElementVisible(element.BoundingRectangle.X, element.BoundingRectangle.Y + element.BoundingRectangle.Height, wechatMainHandle);
            return result;
        }
    }
}