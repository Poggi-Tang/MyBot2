using System;
using System.Runtime.InteropServices;
using System.Text;

namespace WeChatAuto.Utils
{
    public class CursorHelper
    {
        [StructLayout(LayoutKind.Sequential)]
        public struct CURSORINFO
        {
            public int cbSize;
            public int flags;
            public IntPtr hCursor;
            public POINTAPI ptScreenPos;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct POINTAPI
        {
            public int x;
            public int y;
        }

        [DllImport("user32.dll")]
        public static extern bool GetCursorInfo(out CURSORINFO pci);

        const int CURSOR_SHOWING = 0x00000001;

        public static IntPtr GetCurrentCursorHandle()
        {
            CURSORINFO info = new CURSORINFO();
            info.cbSize = Marshal.SizeOf(info);

            if (GetCursorInfo(out info))
            {
                if ((info.flags & CURSOR_SHOWING) != 0)
                {
                    return info.hCursor;
                }
            }

            return IntPtr.Zero;
        }
    }
}