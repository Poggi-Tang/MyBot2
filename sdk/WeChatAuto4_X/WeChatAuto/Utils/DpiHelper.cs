using System;
using System.Runtime.InteropServices;
using WeChatAuto.Services;

namespace WeChatAuto.Utils
{
public static class DpiHelper
{
    [DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(IntPtr hWnd);

    /// <summary>
    /// 获取窗口缩放比例
    /// 100%=1.0
    /// 125%=1.25
    /// 150%=1.5
    /// </summary>
    public static decimal GetScaleForWindow(IntPtr hwnd)
    {
        return GetDpiForWindow(hwnd) / 96m;
    }
}
}