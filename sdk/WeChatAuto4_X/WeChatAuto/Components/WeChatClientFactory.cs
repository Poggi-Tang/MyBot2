using System.Collections.Generic;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using WeAutoCommon.Utils;
using System;
using System.Linq;
using WeChatAuto.Utils;
using FlaUI.Core.Tools;
using WeChatAuto.Services;
using Microsoft.Extensions.DependencyInjection;
using System.Threading;
using FlaUI.UIA3;
using WeAutoCommon.Models;
using WeChatAuto.Extentions;
using FlaUI.Core.Input;
using System.Drawing;
using WeChatAuto.Models;
using System.IO;
using WeAutoCommon.Extentions;
using System.Windows.Controls;
using System.Diagnostics;

namespace WeChatAuto.Components
{
    /// <summary>
    /// 微信客户端工厂,封装的微信客户端工厂，支持多微信实例
    /// </summary>
    public class WeChatClientFactory : IDisposable
    {
        // TODO: 每次微信版本变化应该检查这里是否需要修改.
        private const string CURRENT_WEIXIN_CLASSNAME = "Qt51514QWindowIcon";
        private bool _IsInit = false;
        private readonly AutoLogger<WeChatClientFactory> _logger;
        private IServiceProvider _serviceProvider;
        private readonly Dictionary<string, WeChatClient> _wxClientList = new Dictionary<string, WeChatClient>();
        private bool _disposed = false;
        private readonly WeChatRecordVideo _recordVideo;
        private SemaphoreSlim monitorEvent = new SemaphoreSlim(1, 1);    //所有自动监听都应该受这个约束

        public readonly static string MainActionThreadName = "wechatauto.sdk";
        public static UIThreadInvoker MainActionThreadInvoker;   //就是多微信的情况下，也是启用一个线程,因为这样虽然慢，但能实现更强的功能.

        /// <summary>
        /// 微信自动化客户端工厂
        /// </summary>
        /// <remarks>
        /// 注意：不应该自行调用，而是通过依赖注入获取实例。
        ///
        /// 示例：
        /// <![CDATA[
        /// var clientFactory = serviceProvider.GetRequiredService<WeChatClientFactory>();
        /// ]]>
        /// </remarks>
        public WeChatClientFactory(IServiceProvider serviceProvider)
        {
            MainActionThreadInvoker = new UIThreadInvoker(WeChatClientFactory.MainActionThreadName);
            _serviceProvider = serviceProvider;
            _logger = _serviceProvider.GetRequiredService<AutoLogger<WeChatClientFactory>>();
            _recordVideo = _serviceProvider.GetRequiredService<WeChatRecordVideo>();
            if (WeAutomation.Config.EnableRecordVideo)
            {
                var videoPath = _recordVideo.RecordVideo().GetAwaiter().GetResult();
                _logger.Trace($"开始录制视频,保存路径: {videoPath}");
            }
            _logger.Trace("微信客户端工厂初始化完成");
            InitOCRService();
        }

        /// <summary>
        /// 初始化OCR引擎
        /// </summary>
        private void InitOCRService()
        {
            OCRService oCRService = _serviceProvider.GetRequiredService<OCRService>();
            oCRService.InitOCREngin(WeAutomation.Config);
        }

        /// <summary>
        /// 微信客户端列表
        /// </summary>
        public Dictionary<string, WeChatClient> WeChatClientList
        {
            get
            {
                Init();
                return _wxClientList;
            }
        }
        /// <summary>
        /// 获取客户端名称列表
        /// </summary>
        /// <returns></returns>
        public List<string> GetWeChatClientNames()
        {
            Init();
            return _wxClientList.Keys.ToList();
        }

        /// <summary>
        /// 初始化微信窗口
        /// </summary>
        private void Init()
        {
            if (!_IsInit || _wxClientList.Count == 0)
            {
                _FetchAllWxClients();
                _IsInit = true;
            }
        }

        /// <summary>
        /// 获取微信客户端
        /// </summary>
        /// <param name="name">微信客户端名称</param>
        /// <returns>微信客户端<see cref="WeChatClient"/></returns>
        /// <exception cref="Exception"></exception>
        public WeChatClient GetWeChatClient(string name)
        {
            Init();
            if (_wxClientList.ContainsKey(name))
            {
                return _wxClientList[name];
            }
            _logger.Error($"微信客户端[{name}]不存在，请检查微信是否打开");
            throw new Exception($"微信客户端[{name}]不存在，请检查微信是否打开");
        }

        /// <summary>
        /// 获取微信客户端列表
        /// 微信客户端请参见<see cref="WeChatClient"/>
        /// </summary>
        /// <returns>微信客户端列表</returns>
        public Dictionary<string, WeChatClient> GetWeChatClientList()
        {
            Init();
            return _wxClientList;
        }

        /// <summary>
        /// 获取微信客户端
        /// </summary>
        /// <exception cref="Exception"></exception>
        private void _FetchAllWxClients()
        {
            if (_disposed)
            {
                return;
            }
            _wxClientList.Clear();
            _logger.Trace("开始重新获取微信窗口");
            try
            {
                MainActionThreadInvoker.Run(automation =>
                {
                    try
                    {
                        _GetTaskBarRoot(automation)
                        .Bind(taskBar => _GetNotifyIcons(taskBar))
                        .Bind(buttons => _ProcessNotifyButtons(automation, buttons));
                    }
                    catch (Exception ex)
                    {
                        _logger.Trace($"通过系统托盘获取微信窗口失败，将尝试主窗口: {ex.Message}");
                    }
                    if (_wxClientList.Count == 0)
                    {
                        _ProcessMainWindows(automation);
                    }
                }).ConfigureAwait(false).GetAwaiter().GetResult();
            }
            catch (Exception ex)
            {
                _logger.Error($"获取微信窗口失败: {ex.Message}");
                throw new Exception($"获取微信窗口失败: {ex.Message}");
            }
            finally
            {

            }
        }

        /// <summary>
        /// 系统托盘图标可能被隐藏或不可访问，直接从微信主进程恢复客户端。
        /// </summary>
        private void _ProcessMainWindows(UIA3Automation automation)
        {
            var index = 0;
            foreach (var process in Process.GetProcessesByName("Weixin"))
            {
                try
                {
                    if (process.MainWindowHandle == IntPtr.Zero)
                    {
                        continue;
                    }
                    var element = automation.FromHandle(process.MainWindowHandle);
                    if (element == null || (element.Name != "微信" && element.Name != "微信 "))
                    {
                        continue;
                    }
                    index++;
                    _InitWechatAutomationFramework(automation, process.Id, index);
                }
                catch (Exception ex)
                {
                    _logger.Error($"通过微信主窗口初始化客户端失败: {ex.Message}");
                }
                finally
                {
                    process.Dispose();
                }
            }
            _logger.Trace($"通过微信主窗口发现客户端数量: 共{_wxClientList.Count}个");
        }


        /// <summary>
        /// 获取任务栏根元素
        /// </summary>
        /// <param name="automation"></param>
        /// <returns></returns>
        private Maybe<AutomationElement> _GetTaskBarRoot(UIA3Automation automation)
        {
            var result = Retry.WhileNull(() => automation.GetDesktop().FindFirstChild(cf =>
                          cf.ByName(WeChatConstant.WECHAT_SYSTEM_TASKBAR).And(cf.ByClassName("Shell_TrayWnd"))),
                          timeout: TimeSpan.FromSeconds(5),
                          interval: TimeSpan.FromMilliseconds(200)).Result;
            if (result == null)
            {
                _logger.Error($"{nameof(WeChatClientFactory)} - {nameof(_GetTaskBarRoot)}:本系统的UI Tree可能不被支持，因为找不到任务栏");
            }
            return result.ToMaybe();
        }

        private Maybe<AutomationElement[]> _GetNotifyIcons(AutomationElement taskBar) => ShellNotifyHelper.GetNotifyIcons(taskBar);

        private Maybe<bool> _ProcessNotifyButtons(UIA3Automation automation, AutomationElement[] buttons)
        {
            var index = 0;
            foreach (var wxNotifyButton in buttons)
            {
                index++;
                _InitWechatAutomationFramework(automation, wxNotifyButton, index);
            }
            this._IsInit = true;
            _logger.Trace($"当前微信客户端数量: 共{_wxClientList.Count}个");
            return _IsInit.ToMaybe();
        }
        /// <summary>
        /// 初始化微信自动化整个框架
        /// </summary>
        /// <param name="automation"></param>
        /// <param name="wxNotifyButton"></param>
        /// <param name="index">任务栏索引</param>
        private void _InitWechatAutomationFramework(UIA3Automation automation, AutomationElement wxNotifyButton, int index)
        {
            DrawHightlightHelper.DrawHighlightExt(wxNotifyButton);
            RandomWait.Wait(100, 600);
            wxNotifyButton.AsButton().Click();
            RandomWait.Wait(100, 800);
            var topWindowProcessId = _GetTopWindowProcessIdResult();  //当前微信的processid
            _InitWechatAutomationFramework(automation, topWindowProcessId.Result, index);
        }

        private void _InitWechatAutomationFramework(UIA3Automation automation, int processId, int index)
        {
            (OwerInfo info, Window window) result = __GetCurrentWxNickName(processId, automation);
            result.window.Focus();
            var client = new WeChatClient(processId, _serviceProvider, this, result.window, MainActionThreadInvoker, result.info, index, monitorEvent);
            _wxClientList.Add(result.info.NickName, client);
        }


        //得到最新窗口的nickName等信息.
        private (OwerInfo info, Window window) __GetCurrentWxNickName(int handle, UIA3Automation automation)
        {
            try
            {
                var desktop = automation.GetDesktop();
                var windowRetry = Retry.WhileNull(() => desktop.FindFirstChild(cf => cf.ByControlType(ControlType.Window).And(cf.ByProcessId(handle)).And((cf.ByName("微信").Or(cf.ByName("微信 "))))),
                    timeout: TimeSpan.FromSeconds(5),
                    interval: TimeSpan.FromMilliseconds(200));
                if (windowRetry.Success)
                {
                    var wxTempwindow = windowRetry.Result.AsWindow();
                    RandomWait.Wait(300, 600);
                    OwerInfo info = new OwerInfo();
                    wxTempwindow.Focus();
                    RandomWait.Wait(300, 600);
                    var toolBar = wxTempwindow.FindFirstDescendant(cf => cf.ByAutomationId("MainView.main_tabbar").And(cf.ByName("导航")).And(cf.ByControlType(ControlType.ToolBar)));
                    var button = toolBar.FindFirstChild(cf => cf.ByName("微信").And(cf.ByClassName("mmui::XTabBarItem")).And(cf.ByControlType(ControlType.Button)));
                    var point1 = button.GetClickablePoint();
                    var topInterval = (int)(WeAutomation.Config.AvatorToWeixinButtonOffsetY * DpiHelper.GetScaleForWindow(wxTempwindow.Properties.NativeWindowHandle));
                    var point2 = new Point(point1.X, point1.Y - topInterval);
                    //Mouse.MoveTo(point2);
                    Mouse.Position = point2;
                    Mouse.LeftClick();
                    RandomWait.Wait(300, 800);
                    var windowResult = Retry.WhileNull<AutomationElement>(() => desktop.FindFirstChild(cf => cf.ByName("Weixin").
                        And(cf.ByProcessId(wxTempwindow.Properties.ProcessId))),
                        timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
                    if (windowResult.Success)
                    {
                        var window = windowResult.Result.AsWindow();
                        window.DrawHighlightExt();
                        button = window.FindFirstDescendant(cf => cf.ByAutomationId("head_image_v_view.head_view_").And(cf.ByControlType(ControlType.Button))
                            .And(cf.ByProcessId(wxTempwindow.Properties.ProcessId)));
                        button?.DrawHighlightExt();
                        if (button != null)
                        {
                            var wxid = button.GetParent().GetParent().FindFirstDescendant(cf => cf.ByName("微信号：").And(cf.ByControlType(ControlType.Text)));
                            if (wxid != null)
                            {
                                wxid.DrawHighlightExt();
                                wxid = wxid.GetSibling(1);
                                if (wxid != null)
                                {
                                    info.WxId = wxid.Name.Trim();
                                    info.NickName = button.Name.Trim();
                                    var avatorPath = Path.Combine(AppContext.BaseDirectory, "Avator");
                                    if (!Directory.Exists(avatorPath))
                                    {
                                        Directory.CreateDirectory(avatorPath);
                                    }
                                    avatorPath = Path.Combine(avatorPath, $"{info.WxId}.png");
                                    button.CaptureToFile(avatorPath);
                                    info.AvatorPath = avatorPath;
                                }
                            }
                            RandomWait.Wait(50, 600);
                        }
                    }
                    return (info, wxTempwindow);
                }
                else
                {
                    throw new Exception("没有获取到窗口");
                }
            }
            catch (Exception ex)
            {
                _logger.Error(ex.ToString());
                throw;
            }
        }

        /// <summary>
        /// 获取顶部窗口进程ID
        /// </summary>
        /// <returns></returns>
        private RetryResult<int> _GetTopWindowProcessIdResult()
        => Retry.WhileException(() => WinApi.GetTopWindowProcessIdByClassName(CURRENT_WEIXIN_CLASSNAME),
            timeout: TimeSpan.FromSeconds(5),
            interval: TimeSpan.FromMilliseconds(200));

        /// <summary>
        /// 释放资源
        /// </summary>
        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }
        ~WeChatClientFactory()
        {
            Dispose(false);
        }
        protected virtual void Dispose(bool disposing)
        {
            if (_disposed)
            {
                return;
            }
            _disposed = true;
            if (WeAutomation.Config.EnableMouseKeyboardSimulator)
            {
                KMSimulatorService.CloseDevice();
            }

            if (WeAutomation.Config.EnableRecordVideo)
            {
                _recordVideo?._VideoRecorder?.Stop();
                _recordVideo?._VideoRecorder?.Dispose();
            }
            if (_wxClientList != null && _wxClientList.Count > 0)
            {
                foreach (var client in _wxClientList)
                {
                    client.Value?.Dispose();
                }
            }
            MainActionThreadInvoker.Dispose();   //将微信自动化的线程释放.
        }
    }
}
