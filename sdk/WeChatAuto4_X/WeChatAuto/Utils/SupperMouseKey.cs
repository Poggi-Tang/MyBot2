using System.Diagnostics;
using System.IO;
using System;
using System.Threading.Tasks;
using System.Runtime.InteropServices;
using System.Configuration;
using FlaUI.Core;
using FlaUI.UIA3;
using WeChatAuto.Components;
using WeAutoCommon.Models;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Tools;
using WeAutoCommon.Utils;
using FlaUI.Core.Definitions;
using WeChatAuto.Services;
using FlaUI.Core.Input;
using System.Drawing;
using FlaUI.Core.WindowsAPI;
using System.Linq;

namespace WeChatAuto.Utils
{
    public static class SupperMouseKey
    {
        #region 鼠标操作
        /// <summary>
        /// 移动鼠标
        /// </summary>
        /// <param name="x"></param>
        /// <param name="y"></param>
        public static void MoveTo(int x, int y)
        {
            // Position assignment maps directly to SetCursorPos. Movement is
            // intentionally instantaneous; clicks still use the configured backend.
            Mouse.Position = new Point(x, y);
        }
        /// <summary>
        /// 移动鼠标
        /// </summary>
        /// <param name="point"></param>
        public static void MoveTo(Point point) => MoveTo(point.X, point.Y);
        /// <summary>
        /// 鼠标左键单击
        /// </summary>
        public static void LeftClick()
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.LeftClick();
            }
            else
            {
                Mouse.LeftClick();
            }
        }
        /// <summary>
        /// 鼠标左键单击
        /// </summary>
        public static void LeftClick(int x, int y)
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.LeftClick(new Point(x, y));
            }
            else
            {
                Mouse.LeftClick(new Point(x, y));
            }
        }
        /// <summary>
        /// 鼠标左键单击
        /// </summary>
        public static void LeftClick(Point point) => LeftClick(point.X, point.Y);
        /// <summary>
        /// 右键单击
        /// </summary>
        public static void RightClick()
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.RightClick();
            }
            else
            {
                Mouse.RightClick();
            }
        }
        /// <summary>
        /// 右键单击
        /// </summary>
        public static void RightClick(int x, int y)
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.RightClick(x, y);
            }
            else
            {
                Mouse.RightClick(new Point(x, y));
            }
        }
        /// <summary>
        /// 右键单击
        /// </summary>
        public static void RightClick(Point point) => RightClick(point.X, point.Y);

        /// <summary>
        /// 鼠标滚动
        /// 向上滚动是正数，向下滚动是负数。
        /// </summary>
        /// <param name="count"></param>
        public static void MouseWheel(int count = 3)
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.MouseWheel(count);
            }
            else
            {
                Mouse.Scroll(count);
            }
        }
        /// <summary>
        /// 鼠标滚动
        /// 向上滚动是正数，向下滚动是负数。
        /// </summary>
        /// <param name="count"></param>
        public static void Scroll(int count = 3) => MouseWheel(count);
        /// <summary>
        /// 双击
        /// </summary>
        public static void DoubleClick()
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.LeftDoubleClick();
            }
            else
            {
                Mouse.LeftDoubleClick();
            }
        }
        /// <summary>
        /// 双击
        /// </summary>
        /// <param name="x"></param>
        /// <param name="y"></param>
        public static void DoubleClick(int x, int y)
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.LeftDoubleClick(x, y);
            }
            else
            {
                Mouse.LeftDoubleClick(new Point(x, y));
            }
        }
        /// <summary>
        /// 双击
        /// </summary>
        /// <param name="point"></param>
        public static void DoubleClick(Point point) => DoubleClick(point.X, point.Y);
        /// <summary>
        /// 鼠标左键按下
        /// </summary>
        public static void LeftDown()
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.LeftDown();
            }
            else
            {
                Mouse.Down();
            }
        }
        public static void LeftUp()
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.LeftUp();
            }
            else
            {
                Mouse.Up();
            }
        }
        #endregion
        #region 键盘操作
        public static void Type(string input)
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.KeyPressString(input);
            }
            else
            {
                Keyboard.Type(input);
            }
        }

        /// <summary>
        /// 回车
        /// </summary>
        public static void Enter()
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.Enter();
            }
            else
            {
                Keyboard.TypeSimultaneously(VirtualKeyShort.ENTER);
            }
        }

        /// <summary>
        /// 输入联合的键
        /// </summary>
        /// <param name="virtualKeys"></param>
        public static void TypeSimultaneously(params VirtualKeyShort[] virtualKeys)
        {
            if (virtualKeys.Length == 0)
                return;
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                string keys = _GetKeys(virtualKeys);
                KMSimulatorService.KeyPress(keys);
            }
            else
            {
                Keyboard.TypeSimultaneously(virtualKeys);
            }
        }

        private static string _GetKeys(VirtualKeyShort[] virtualKeys)
        {
            VirtualKeyShort[] virtualKeySupports = new VirtualKeyShort[] { VirtualKeyShort.BACK, VirtualKeyShort.TAB, VirtualKeyShort.ENTER, VirtualKeyShort.SHIFT, VirtualKeyShort.CONTROL, VirtualKeyShort.ALT, VirtualKeyShort.PAUSE, VirtualKeyShort.ESC, VirtualKeyShort.SPACE, VirtualKeyShort.PRIOR, VirtualKeyShort.NEXT, VirtualKeyShort.END, VirtualKeyShort.HOME, VirtualKeyShort.SCROLL, VirtualKeyShort.NUMLOCK, VirtualKeyShort.LMENU, VirtualKeyShort.RMENU, VirtualKeyShort.LCONTROL, VirtualKeyShort.RCONTROL, VirtualKeyShort.LSHIFT, VirtualKeyShort.RSHIFT, VirtualKeyShort.LWIN, VirtualKeyShort.RWIN, VirtualKeyShort.KEY_A, VirtualKeyShort.KEY_C, VirtualKeyShort.KEY_V };
            string[] codeSupports = new string[] { "Backspace", "Tab", "Enter", "Shift", "Ctrl", "Alt", "Pause", "Esc", "Space", "Page Up", "Page Down", "End", "Home", "Scroll Lock", "Num Lock", "Left Alt", "Right Alt", "Left Ctrl", "Right Ctrl", "Left Shift", "Right Shift", "Left Win", "Right Win", "A", "C", "V" };
            if (virtualKeySupports.Length != codeSupports.Length)
                throw new Exception("错误：虚拟键设置有问题！");
            var existList = virtualKeys.Intersect(virtualKeySupports);
            if (existList.Count() != virtualKeys.Length)
            {
                throw new Exception("错误：有一些键没有在配置中，请配置对应的键！");
            }
            var keys = "";
            foreach (var key in virtualKeys)
            {
                var index = Array.FindIndex(virtualKeySupports, x => x == key);
                var code = codeSupports[index];
                if (string.IsNullOrWhiteSpace(keys))
                {
                    keys = code;
                }
                else
                {
                    keys = keys + "+" + code;
                }
            }

            return keys;
        }
        /// <summary>
        /// 按着某键不放
        /// </summary>
        /// <param name="key"></param>
        public static void KeyDown(VirtualKeyShort key)
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                var keyStr = _GetKeys(new VirtualKeyShort[] { key });
                KMSimulatorService.KeyDown(keyStr);
            }
            else
            {
                KeyDownCore(key);
            }
        }
        /// <summary>
        /// 释放某键
        /// </summary>
        /// <param name="key"></param>
        public static void KeyUp(VirtualKeyShort key)
        {
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                var keyStr = _GetKeys(new VirtualKeyShort[] { key });
                KMSimulatorService.KeyUp(keyStr);
            }
            else
            {
                KeyUpCore(key);
            }
        }
        #endregion


        // 在你的类内部申明 Windows 原生 API 
        [DllImport("user32.dll", SetLastError = true)]
        private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

        private const uint KEYEVENTF_KEYDOWN = 0x0000;
        private const uint KEYEVENTF_KEYUP = 0x0002;

        /// <summary>
        /// 按着某键不放
        /// </summary>
        private static void KeyDownCore(VirtualKeyShort key)
        {
            keybd_event((byte)key, 0, KEYEVENTF_KEYDOWN, UIntPtr.Zero);
        }

        /// <summary>
        /// 释放某键
        /// </summary>
        private static void KeyUpCore(VirtualKeyShort key)
        {
            keybd_event((byte)key, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
        }
    }
}
