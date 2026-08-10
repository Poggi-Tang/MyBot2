
using FlaUI.Core.AutomationElements;
using WeAutoCommon.Configs;
using WeAutoCommon.Models;
using WeAutoCommon.Utils;
using WeChatAuto.Components;
using WeChatAuto.Services;

namespace WeChatAuto.Utils
{
    public static class DrawHightlightHelper
    {
        /// <summary>
        /// 高亮元素，适应无UI线程指定情况下使用
        /// </summary>
        /// <param name="element"></param>
        /// <param name="uiThreadInvoker"></param>
        public static void DrawHightlight(AutomationElement element, UIThreadInvoker uiThreadInvoker)
        {
            if (WeAutomation.Config.DebugMode && element != null)
            {
                uiThreadInvoker.Run(automation => element.DrawHighlight());
            }
        }
        /// <summary>
        /// 高亮元素，适应有UI线程指定情况下使用
        /// </summary>
        /// <param name="element"></param>
        /// <param name="uiThreadInvoker">线程执行器</param>
        public static void DrawHighlightExt(this AutomationElement element, UIThreadInvoker uiThreadInvoker = null)
        {
            if (WeAutomation.Config.DebugMode && element != null)
            {
                if (uiThreadInvoker != null)
                {
                    uiThreadInvoker.Run(automation => element.DrawHighlight());
                }
                else
                {
                    element.DrawHighlight();
                }
            }
        }
        /// <summary>
        /// 高亮元素
        /// </summary>
        /// <param name="element"></param>
        public static void HightLight(this AutomationElement element)
        {
            if (WeAutomation.Config.DebugMode && element != null)
            {
                if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
                {
                    element.DrawHighlight();
                }else
                {
                    WeChatClientFactory.MainActionThreadInvoker.Run(automation=>element.DrawHighlight());
                }
            }
        }
    }
}