
using System;
using Emgu.CV.XImgproc;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Input;
using WeAutoCommon.Configs;
using WeAutoCommon.Models;
using WeAutoCommon.Utils;
using WeChatAuto.Components;
using WeChatAuto.Services;

namespace WeChatAuto.Utils
{
    public static class MouseScrollHelper
    {
        /// <summary>
        /// 向下滚动
        /// </summary>
        /// <param name="scrollPoint"></param>
        /// <param name="maxStep"></param>
        public static void DownStep(System.Drawing.Point scrollPoint, int maxStep)
        {
            Random random = new Random((int)DateTime.Now.Ticks);
            for (int i = 0; i < maxStep; i++)
            {
                Mouse.Position = scrollPoint;
                RandomWait.Wait(5, 50);
                if (i == 0)
                {
                    // Mouse.Scroll(-1 * random.Next(1, 3));
                    SupperMouseKey.Scroll(-1 * random.Next(1, 3));
                }
                if (i == maxStep - 1)
                {
                    //Mouse.Scroll(-1 * random.Next(3, 5));
                    SupperMouseKey.Scroll(-1 * random.Next(3, 5));
                }
                RandomWait.Wait(30, 50);
            }
        }
        /// <summary>
        /// 向上滚动
        /// </summary>
        /// <param name="scrollPoint"></param>
        /// <param name="maxStep"></param>
        public static void UpStep(System.Drawing.Point scrollPoint, int maxStep)
        {
            Random random = new Random((int)DateTime.Now.Ticks);
            for (int i = 0; i < maxStep; i++)
            {
                Mouse.Position = scrollPoint;
                RandomWait.Wait(30, 150);
                if (i == 0)
                {
                    // Mouse.Scroll(random.Next(1, 3));
                    SupperMouseKey.Scroll(random.Next(1, 3));
                }
                if (i == maxStep - 1)
                {
                    // Mouse.Scroll(random.Next(3, 5));
                    SupperMouseKey.Scroll(random.Next(3,5));
                }
                RandomWait.Wait(30, 150);
            }
        }


    }
}