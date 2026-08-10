using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace WeChatAuto.Utils
{
    public static class WinMouse
    {
        [StructLayout(LayoutKind.Sequential)]
        struct INPUT
        {
            public uint type;
            public InputUnion U;
        }

        [StructLayout(LayoutKind.Explicit)]
        struct InputUnion
        {
            [FieldOffset(0)]
            public MOUSEINPUT mi;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct MOUSEINPUT
        {
            public int dx;
            public int dy;
            public uint mouseData;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        const int INPUT_MOUSE = 0;

        const uint MOUSEEVENTF_MOVE = 0x0001;
        const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
        const uint MOUSEEVENTF_LEFTUP = 0x0004;
        const uint MOUSEEVENTF_ABSOLUTE = 0x8000;

        [DllImport("user32.dll")]
        static extern uint SendInput(
            uint nInputs,
            INPUT[] pInputs,
            int cbSize);

        [DllImport("user32.dll")]
        static extern bool SetCursorPos(int x, int y);

        public static void Drag(Point source, Point target)
        {
            // 移动到起点
            SetCursorPos(source.X, source.Y);

            Thread.Sleep(50);

            // 按下左键
            MouseEvent(MOUSEEVENTF_LEFTDOWN);

            Thread.Sleep(50);

            // 模拟平滑拖动
            int steps = 30;

            for (int i = 1; i <= steps; i++)
            {
                int x = source.X + (target.X - source.X) * i / steps;
                int y = source.Y + (target.Y - source.Y) * i / steps;

                SetCursorPos(x, y);

                Thread.Sleep(10);
            }

            Thread.Sleep(50);

            // 松开
            MouseEvent(MOUSEEVENTF_LEFTUP);
        }

        static void MouseEvent(uint flags)
        {
            INPUT input = new INPUT();

            input.type = INPUT_MOUSE;

            input.U.mi.dwFlags = flags;

            SendInput(
                1,
                new INPUT[] { input },
                Marshal.SizeOf(typeof(INPUT)));
        }
    }
}