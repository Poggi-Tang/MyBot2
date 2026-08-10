using System;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Input;
using Microsoft.Extensions.DependencyInjection;
using WeAutoCommon.Utils;
using WeChatAuto.Utils;
using FlaUI.Core.Definitions;
using System.Threading;
using WeChatAuto.Extentions;
using System.Threading.Tasks;
using FlaUI.UIA3;

namespace WeChatAuto.Components
{
    /// <summary>
    /// 微信窗口工具栏封装,可以进行最大化/还原，置顶/反置顶操作
    /// </summary>
    public class ToolBar
    {
        private readonly IServiceProvider _serviceProvider;
        private UIThreadInvoker _uiMainThreadInvoker;
        private Window _MainWindow;
        private AutoLogger<ToolBar> _logger;

        private AutomationElement _ToolBarRoot => GetToolBarRoot();
        /// <summary>
        /// 工具栏构造函数
        /// </summary>
        /// <param name="mainWindow">主窗口</param>
        /// <param name="uiThreadInvoker">UI线程执行器</param>
        /// <param name="serviceProvider">服务提供者</param>
        internal ToolBar(Window mainWindow, UIThreadInvoker uiThreadInvoker, IServiceProvider serviceProvider)
        {
            _MainWindow = mainWindow;
            _uiMainThreadInvoker = uiThreadInvoker;
            _serviceProvider = serviceProvider;
            _logger = serviceProvider.GetRequiredService<AutoLogger<ToolBar>>();
        }

        private AutomationElement GetToolBarRoot()
        {
            var path = "/Group/ToolBar/Button[@Name='关闭']";
            var root = _MainWindow.FindFirstByXPath(path);
            return root.GetParent();
        }


        /// <summary>
        /// 置顶/反置顶
        /// </summary>
        /// <param name="isTop">如果为true:则置顶，如果为false,则反置顶</param>
        public async Task Top(bool isTop = true)
        {
            await WeChatInvoker.Call(TopCore, isTop);
        }

        private void TopCore(UIA3Automation automation, bool isTop)
        {
            try
            {
                if (isTop)
                {
                    var button = _ToolBarRoot.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("置顶")));
                    if (button != null)
                    {
                        Mouse.MoveTo(button.GetClickablePoint());
                        button.DrawHighlightExt();
                        button.Click();
                        RandomWait.Wait(600, 1500);
                    }
                }
                else
                {
                    var button = _ToolBarRoot.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("取消置顶")));
                    if (button != null)
                    {
                        Mouse.MoveTo(button.GetClickablePoint());
                        button.DrawHighlightExt();
                        button.Click();
                        RandomWait.Wait(600, 1500);
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"{nameof(ToolBar)} - {nameof(Top)}:{ex.ToString()}");
            }
        }



        /// <summary>
        /// 最大化
        /// </summary>
        public async Task Max()
        {
            await WeChatInvoker.Call(MaxCore);
        }

        private void MaxCore(UIA3Automation automation)
        {
            try
            {
                var button = _ToolBarRoot.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("最大化")));
                if (button != null)
                {
                    button.DrawHighlightExt();
                    Mouse.Position = button.GetClickablePoint();
                    button.Click();
                    RandomWait.Wait(500, 1500);
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"{nameof(ToolBar)} - {nameof(Max)}:{ex.ToString()}");
            }
        }


        /// <summary>
        /// 还原
        /// </summary>
        public async Task Restore()
        {
            await WeChatInvoker.Call(RestoreCore);
        }

        private void RestoreCore(UIA3Automation automation)
        {
            try
            {
                var button = _ToolBarRoot.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("还原")));
                if (button != null)
                {
                    button.HightLight();
                    Mouse.Position = button.GetClickablePoint();
                    button.Click();
                    RandomWait.Wait(500, 1500);
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"{nameof(ToolBar)} - {nameof(Restore)}:{ex.ToString()}");
            }
        }
    }
}