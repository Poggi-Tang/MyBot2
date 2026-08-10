using System;
using FlaUI.Core.AutomationElements;
using Microsoft.Extensions.DependencyInjection;
using WeAutoCommon.Enums;
using WeAutoCommon.Models;
using System.Text.RegularExpressions;
using WeChatAuto.Extentions;
using WeChatAuto.Utils;
using WeAutoCommon.Utils;
using FlaUI.UIA3;
using System.Threading.Tasks;
using FlaUI.Core.Definitions;

namespace WeChatAuto.Components
{
	/// <summary>
	/// 聊天内容区标题区
	/// </summary>
	public class ChatHeader
	{
		private readonly IServiceProvider _serviceProvider;
		private readonly AutoLogger<ChatHeader> _logger;
		private UIThreadInvoker _uiMainThreadInvoker;
		private WeChatClient _Client;
		private ChatContent content;
		/// <summary>
		/// 标题的root element,有可能为空
		/// </summary>
		internal AutomationElement HeaderRoot
		{
			get
			{
				var root = _Client.MainWindow.FindFirstDescendant(cf => cf.ByAutomationId("content_view.top_content_view.title_h_view.left_v_view.left_content_v_view.left_ui_")
					.And(cf.ByClassName("mmui::XView").And(cf.ByControlType(FlaUI.Core.Definitions.ControlType.Group))));
				return root;
			}
		}

		/// <summary>
		/// 聊天内容区标题区构造函数
		/// </summary>
		internal ChatHeader(WeChatClient client, IServiceProvider serviceProvider, UIThreadInvoker _uiMainThreadInvoker, ChatContent content)
		{
			this._uiMainThreadInvoker = _uiMainThreadInvoker;
			_logger = serviceProvider.GetRequiredService<AutoLogger<ChatHeader>>();
			_serviceProvider = serviceProvider;
			this._Client = client;
			this.content = content;
		}
		/// <summary>
		/// 获取当前窗口的标题对象
		/// </summary>
		/// <returns>标题对象，请参考:<see cref="HeaderInfo"/></returns>
		public async Task<HeaderInfo> GetTitle()
		{
			return await WeChatInvoker.Call(GetTitleCore);
		}

		/// <summary>
		/// 获取当前标窗的标题
		/// </summary>
		/// <returns>当前窗口的标题名称</returns>
		public async Task<string> GetOnlyTitle()
		{
			var headerInfo = await GetTitle();
			return headerInfo.Title;
		}

		internal HeaderInfo GetTitleCore(UIA3Automation automation)
		{
			HeaderInfo headerInfo = new HeaderInfo();
			var root = HeaderRoot;
			if (root == null)
				return headerInfo;
			var textRoot = root.FindFirstChild(cf => cf.ByAutomationId("content_view.top_content_view.title_h_view.left_v_view.left_content_v_view.left_ui_.big_title_line_h_view").And(cf.ByControlType(FlaUI.Core.Definitions.ControlType.Text))).AsLabel();
			var fullTitle = textRoot.Name.Trim();
			var texts = textRoot.FindAllChildren(cf => cf.ByControlType(FlaUI.Core.Definitions.ControlType.Text));
			bool hasHistoryButton = IsHasHistoryButton();
			if (texts.Length == 2 && hasHistoryButton)
			{
				//群聊
				headerInfo.HeaderType = ChatType.群聊;
				headerInfo.Title = texts[0].Name.Trim();
				headerInfo.ChatNumber = int.TryParse(texts[1].Name.Trim().Substring(1, texts[1].Name.Trim().Length - 2), out var result) ? result : 0;
				return headerInfo;
			}

			//非群聊,可能是好友，也可能不是.
			if (texts.Length == 1)
			{
				headerInfo.Title = texts[0].Name.Trim();
				if (IsHasVoIpButton() && IsHasHistoryButton())
				{
					//这里区分出是普通好友还是企业微信.
					var atText = root.FindFirstDescendant(cf => cf.ByAutomationId("content_view.top_content_view.title_h_view.left_v_view.left_content_v_view.left_ui_.openim_name_view.current_chat_openim_name").And(cf.ByClassName("mmui::XTextView").And(cf.ByControlType(ControlType.Text))));
					if (atText != null && atText.Name.StartsWith("@"))
					{
						headerInfo.HeaderType = ChatType.企业微信;
						return headerInfo;
					}
					headerInfo.HeaderType = ChatType.好友;
					return headerInfo;
				}
				if (headerInfo.Title.Equals("文件传输助手") && !IsHasVoIpButton())
				{
					headerInfo.HeaderType = ChatType.文件传输助手;
					return headerInfo;
				}

				if (headerInfo.Title.Equals("公众号") && !IsHasVoIpButton())
				{
					headerInfo.HeaderType = ChatType.公众号;
					return headerInfo;
				}

				if (headerInfo.Title.Equals("服务通知") && !IsHasVoIpButton())
				{
					headerInfo.HeaderType = ChatType.服务通知;
					return headerInfo;
				}
				if (headerInfo.Title.Equals("腾讯新闻") && !IsHasVoIpButton())
				{
					headerInfo.HeaderType = ChatType.腾讯新闻;
					return headerInfo;
				}
			}


			return headerInfo;
		}

		private bool IsHasHistoryButton()
		{
			var button = _Client.MainWindow.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("聊天记录")).And(cf.ByClassName("mmui::XButton")));
			return button == null ? false : true;
		}

		private bool IsHasVoIpButton()
		{
			var button = _Client.MainWindow.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("语音通话")).And(cf.ByClassName("mmui::XButton").And(cf.ByAutomationId("voip_button"))));
			return button == null ? false : true;
		}
	}
}