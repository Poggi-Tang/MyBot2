using System;
using System.Collections.Generic;
using System.Linq;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using WeAutoCommon.Enums;
using WeAutoCommon.Interface;
using WeAutoCommon.Utils;
using WeChatAuto.Extentions;
using WeChatAuto.Utils;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.DependencyInjection;
using WeAutoCommon.Models;
using System.Threading.Tasks;
using System.Drawing;
using FlaUI.Core;
using FlaUI.Core.Identifiers;
using FlaUI.Core.Conditions;
using System.IO;
using FlaUI.UIA3;
using WeAutoCommon.Extentions;

namespace WeChatAuto.Components
{
    /// <summary>
    /// 对微信导航栏的封装.
    /// </summary>
    public class Navigation
    {
        private readonly IServiceProvider _serviceProvider;
        private WeChatClient _Client;
        internal AutomationElement rootElement => _GetNavigationRoot();
        private readonly AutoLogger<Navigation> _logger;
        private UIThreadInvoker _uiMainThreadInvoker;

        /// <summary>
        /// 导航栏构造函数
        /// 不应该自行初始化，而是通过<see cref="WeChatClient.Navigation"/>获取.
        /// </summary>
        /// <param name="client">本对象所属的<see cref="WeChatClient"/>类</param>
        /// <param name="uiThreadInvoker">UI线程执行器</param>
        /// <param name="serviceProvider">服务提供者</param>
        internal Navigation(WeChatClient client, UIThreadInvoker uiThreadInvoker, IServiceProvider serviceProvider)
        {
            _logger = serviceProvider.GetRequiredService<AutoLogger<Navigation>>();
            _uiMainThreadInvoker = uiThreadInvoker;
            _Client = client;
            _serviceProvider = serviceProvider;
        }

        private AutomationElement _GetNavigationRoot()
        {
            var path = @"/Group/Custom/Group/ToolBar[@Name='导航']";
            var itemRetry = Retry.WhileNull(() => _Client.MainWindow.FindFirstByXPath(path), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));
            if (itemRetry.Success)
                return itemRetry.Result;

            // WeChat 4.x builds may expose the toolbar under MainView instead
            // of the legacy XPath shape. AutomationId is stable across those builds.
            return _Client.MainWindow.FindFirstDescendant(cf =>
                cf.ByControlType(ControlType.ToolBar).And(cf.ByAutomationId("MainView.main_tabbar")));
        }
        /// <summary>
        /// <para>保存个人头像,大部分情况不需要调用此方法，因为系统初始化的时候已经将头像保存在.\Avator\wxid.png</para>
        /// <para>建议用<see cref="WeChatClient.AvatorPath"/>获取个人头像</para>
        /// </summary>
        /// <param name="savePath">保存的目录与文件名，如: c:\temp\avator.jpg</param>
        /// <returns></returns>
        public async Task SaveOwnerAvator(string savePath)
        {
            if (File.Exists(Path.Combine(AppContext.BaseDirectory, "Avator", $"{_Client.WxId}.png")))
            {
                byte[] bytes = File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Avator", $"{_Client.WxId}.png"));
                File.WriteAllBytes(savePath, bytes);
                return;
            }
        }

        internal void SaveOwnerAvatorCore(string savePath)
        {
            _Client.MainWindow.Focus();
            var path = @"/Group/Custom/Group/ToolBar/Button[1]";
            var button = _Client.MainWindow.FindFirstByXPath(path);
            var point1 = button.GetClickablePoint();
            var point2 = new Point(point1.X, point1.Y - 55);
            Mouse.Position = point2;
            Mouse.LeftClick();
            RandomWait.Wait(300, 800);
            var windowResult = Retry.WhileNull<AutomationElement>(() => _Client.MainWindow.Parent.FindFirstChild(cf => cf.ByName("Weixin").
                And(cf.ByProcessId(_Client.MainWindow.Properties.ProcessId))),
                timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
            if (windowResult.Success)
            {
                var window = windowResult.Result.AsWindow();
                window.DrawHighlightExt();
                button = window.FindFirstDescendant(cf => cf.ByAutomationId("head_image_v_view.head_view_").And(cf.ByControlType(ControlType.Button))
                    .And(cf.ByProcessId(_Client.MainWindow.Properties.ProcessId)));
                button?.DrawHighlightExt();
                // button?.ClickEnhance(_Client.MainWindow);
                var bitmap = button.Capture();
                bitmap.Save(savePath);
                _Client.MainWindow.Focus();
            }
        }
        /// <summary>
        /// 切换导航栏
        /// </summary>
        /// <param name="navigationType">导航栏类型</param>
        public async Task SwitchNavigation(NavigationType navigationType)
        {
            await WeChatInvoker.Call(SwitchNavigationCore, navigationType);
        }

        internal void SwitchNavigationCore(UIA3Automation automation, NavigationType navigationType)
        {
            var name = navigationType.ToString();
            var navigation = rootElement;
            var button = navigation?.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName(name))).AsButton();
            button ??= _Client.MainWindow.FindFirstDescendant(cf =>
                cf.ByControlType(ControlType.Button).And(cf.ByName(name))).AsButton();
            if (button == null)
            {
                _logger.Warn($"未找到导航按钮: {name}");
                return;
            }
            _logger.Trace($"找到导航按钮: {name}, AutomationId={button.AutomationId}");

            if (button != null)
            {
                var subButton = button.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button)).AsButton();
                if (subButton != null)
                {
                    button = subButton;
                }
            button.HightLight();
            var point = button.BoundingRectangle.SafeRandomPoint();
            _Client.MainWindow.Focus();
            // Current WeChat 4.x mmui controls may expose InvokePattern but
            // silently ignore Invoke(). Use the SDK click path so both normal
            // mouse input and the optional KM simulator are supported.
            SupperMouseKey.MoveTo(point);
            RandomWait.Wait(80, 180);
            SupperMouseKey.LeftClick();
            RandomWait.Wait(600, 1500);
            }
        }

        /// <summary>
        /// 关闭通过导航栏打开的窗口.
        /// 仅支持聊天文件、朋友圈、视频号、看一看、搜一搜、小程序面板等窗口
        /// </summary>
        /// <param name="navigationType">导航栏类型</param>
        public async Task CloseNavWin(NavigationType navigationType)
        {
            await WeChatInvoker.Call(CloseNavigationCore, navigationType);
        }

        internal void CloseNavigationCore(UIA3Automation automation, NavigationType navigationType)
        {
            RetryResult<Window> retryResult = null;
            RetryResult<Button> buttonResult = null;
            switch (navigationType)
            {
                case NavigationType.朋友圈:
                    retryResult = Retry.WhileNull(() => _Client.MainWindow.Parent.FindFirstChild(cf => cf.ByName("朋友圈").And(cf.ByControlType(ControlType.Window)).
                    And(cf.ByProcessId(_Client.MainWindow.Properties.ProcessId))).AsWindow(), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
                    break;
                case NavigationType.视频号:
                    buttonResult = Retry.WhileNull<Button>(() => _Client.MainWindow.Parent.FindFirstByXPath("/Pane[@Name='微信']/Pane[@Name='微信']/Pane/Pane/Button[@Name='关闭']").AsButton(), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
                    if (buttonResult.Success)
                    {
                        buttonResult.Result.DrawHighlightExt();
                        buttonResult.Result.Invoke();
                    }
                    break;
                case NavigationType.搜一搜:
                    buttonResult = Retry.WhileNull<Button>(() => _Client.MainWindow.Parent.FindFirstByXPath("/Pane[@Name='微信']/Pane[@Name='微信']/Pane/Pane/Button[@Name='关闭']").AsButton(), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
                    if (buttonResult.Success)
                    {
                        buttonResult.Result.DrawHighlightExt();
                        buttonResult.Result.Invoke();
                    }
                    break;
                case NavigationType.小程序面板:
                    buttonResult = Retry.WhileNull<Button>(() => _Client.MainWindow.Parent.FindFirstByXPath("/Pane[@Name='微信']/Pane[@Name='微信']/Pane/Pane/Button[@Name='关闭']").AsButton(), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
                    if (buttonResult.Success)
                    {
                        buttonResult.Result.DrawHighlightExt();
                        buttonResult.Result.Invoke();
                    }
                    break;
                case NavigationType.游戏中心:
                    buttonResult = Retry.WhileNull<Button>(() => _Client.MainWindow.Parent.FindFirstByXPath("/Pane[@Name='微信游戏']/Pane/Pane/Pane/Pane/Pane/Button[@Name='关闭']").AsButton(), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
                    if (buttonResult.Success)
                    {
                        buttonResult.Result.DrawHighlightExt();
                        buttonResult.Result.Invoke();
                    }
                    break;
                case NavigationType.手机:
                    _Client.MainWindow.Focus();
                    break;
                case NavigationType.更多:
                    _Client.MainWindow.Focus();
                    break;
                default:
                    break;
            }
            if (retryResult != null && retryResult.Success)
            {
                var window = retryResult.Result;
                window.DrawHighlightExt();
                window.Close();
                _Client.MainWindow.Focus();
            }
        }
    }
}
