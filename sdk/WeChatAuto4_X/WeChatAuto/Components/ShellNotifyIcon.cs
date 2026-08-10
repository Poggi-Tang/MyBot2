using FlaUI.Core;
using FlaUI.Core.Definitions;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.Core.EventHandlers;
using FlaUI.Core.AutomationElements;
using System.Collections.Generic;
using System.Linq;
using WeAutoCommon.Enums;
using WeAutoCommon.Utils;
using WeChatAuto.Utils;
using FlaUI.UIA3.Converters;
using FlaUI.Core.WindowsAPI;
using System;
using WeChatAuto.Extentions;
using WeAutoCommon.Interface;
using System.Text;
using OneOf;
using Microsoft.Extensions.DependencyInjection;
using System.Threading;
using System.Windows.Controls.Primitives;
using FlaUI.Core.Patterns;
using System.Drawing;
using System.Threading.Tasks;
using WeAutoCommon.Extentions;
using System.Windows;
using FlaUI.UIA3.Patterns;
using FlaUI.UIA3;
using WeAutoCommon.Models;

namespace WeChatAuto.Components
{
    /// <summary>
    /// 任务栏图标
    /// </summary>
    public class ShellNotifyIcon
    {
        public readonly int WechatIndex;
        private WeChatClient _Client;
        private AutoLogger<ShellNotifyIcon> _Logger;
        private IServiceProvider serviceProvider;

        internal ShellNotifyIcon(WeChatClient client, IServiceProvider serviceProvider, int index)
        {
            this.WechatIndex = index;
            this._Client = client;
            this.serviceProvider = serviceProvider;
            _Logger = serviceProvider.GetRequiredService<AutoLogger<ShellNotifyIcon>>();
        }

        public async Task<List<Button>> GetButtons()
        {
            return await WeChatInvoker.Call(GetButtons);
        }

        internal List<Button> GetButtons(UIA3Automation automation)
        {
            var toolBar = _GetTaskBarRoot(automation);
            var elements = ShellNotifyHelper.GetNotifyIcons(toolBar);
            return elements.Value.Select(x => x.AsButton()).ToList();
        }

        public async Task<Button> GetButton()
        {
            return await WeChatInvoker.Call(GetButtonCore);
        }

        internal Button GetButtonCore(UIA3Automation automation)
        {
            var toolBar = _GetTaskBarRoot(automation);
            var elements = ShellNotifyHelper.GetNotifyIcons(toolBar);
            if (elements.Value.Count() >= WechatIndex)
            {
                return elements.Value[WechatIndex - 1].AsButton();
            }
            throw new Exception("发生错误：可能按钮索引超出范围");
        }


        private AutomationElement _GetTaskBarRoot(UIA3Automation automation)
        {
            var result = Retry.WhileNull(() => automation.GetDesktop().FindFirstChild(cf =>
                          cf.ByName(WeChatConstant.WECHAT_SYSTEM_TASKBAR).And(cf.ByClassName("Shell_TrayWnd"))),
                          timeout: TimeSpan.FromSeconds(5),
                          interval: TimeSpan.FromMilliseconds(200)).Result;
            if (result == null)
            {
                _Logger.Error($"{nameof(WeChatClientFactory)} - {nameof(_GetTaskBarRoot)}:本系统的UI Tree可能不被支持，因为找不到任务栏");
            }
            return result;
        }
    }
}