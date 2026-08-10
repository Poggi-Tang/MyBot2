using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Diagnostics;
using System.Drawing;

namespace WeChatAuto.Utils
{
    /// <summary>
    /// Windows剪贴板工具类
    /// </summary>
    public static class ClipboardHelper
    {
        public static void SetText(string text)
        {
            Exception ex = null;

            var thread = new Thread(() =>
            {
                try
                {
                    System.Windows.Clipboard.SetText(text);
                }
                catch (Exception e)
                {
                    ex = e;
                }
            });

            thread.SetApartmentState(ApartmentState.STA);

            thread.Start();
            thread.Join();

            if (ex != null)
                throw ex;
        }

        public static bool TryClear(TimeSpan timeout)
        {
            return RunSta(() =>
            {
                var stopwatch = Stopwatch.StartNew();
                do
                {
                    try
                    {
                        System.Windows.Forms.Clipboard.Clear();
                        return true;
                    }
                    catch (ExternalException)
                    {
                        Thread.Sleep(80);
                    }
                }
                while (stopwatch.Elapsed < timeout);
                return false;
            });
        }

        public static Bitmap TryGetImage(TimeSpan timeout)
        {
            return RunSta(() =>
            {
                var stopwatch = Stopwatch.StartNew();
                do
                {
                    try
                    {
                        using var image = System.Windows.Forms.Clipboard.GetImage();
                        if (image != null)
                            return new Bitmap(image);
                    }
                    catch (ExternalException)
                    {
                        // WeChat can briefly own the clipboard while rendering media.
                    }
                    Thread.Sleep(100);
                }
                while (stopwatch.Elapsed < timeout);
                return null;
            });
        }

        public static string DescribeFormats()
        {
            return RunSta(() =>
            {
                try
                {
                    return string.Join(",", System.Windows.Forms.Clipboard.GetDataObject()?.GetFormats() ?? Array.Empty<string>());
                }
                catch (ExternalException)
                {
                    return "clipboard_busy";
                }
            });
        }

        private static T RunSta<T>(Func<T> action)
        {
            T result = default;
            Exception error = null;
            var thread = new Thread(() =>
            {
                try
                {
                    result = action();
                }
                catch (Exception exception)
                {
                    error = exception;
                }
            });
            thread.SetApartmentState(ApartmentState.STA);
            thread.IsBackground = true;
            thread.Start();
            thread.Join();
            if (error != null)
                throw error;
            return result;
        }
    }
}
