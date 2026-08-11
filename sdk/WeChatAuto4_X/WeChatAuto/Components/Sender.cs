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
using FlaUI.UIA3.Patterns;
using FlaUI.UIA3;
using WeChatAuto.Models;
using WeAutoCommon.Models;
using Emgu.CV;
using Emgu.CV.CvEnum;
using System.Reflection.Metadata.Ecma335;
using System.Windows.Media.Imaging;
using NAudio.CoreAudioApi;
using NAudio.Wave;
using WeChatAuto.Options;
using WeChatAuto.Services;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;

namespace WeChatAuto.Components
{
	/// <summary>
	/// 聊天内容区发送者
	/// </summary>
	public class Sender
	{
		private readonly AutoLogger<Sender> _logger;
		private UIThreadInvoker _uiThreadInvoker;
		private readonly IServiceProvider _serviceProvider;
		private WeChatClient _Client;
		private ChatContent content;
		private readonly StickerCatalogStore _stickerCatalog = new StickerCatalogStore();
		/// <summary>
		/// 聊天内容区发送者构造函数
		/// </summary>
		internal Sender(WeChatClient client, UIThreadInvoker uiThreadInvoker, IServiceProvider serviceProvider, ChatContent content)
		{
			_uiThreadInvoker = uiThreadInvoker;
			_serviceProvider = serviceProvider;
			_logger = serviceProvider.GetRequiredService<AutoLogger<Sender>>();
			this._Client = client;
			this.content = content;
		}

		/// <summary>
		/// 发起单人语音聊天
		/// </summary>
		/// <param name="who">好友昵称</param>
		public async Task SendVoiceChat(string who)
		{
			await WeChatInvoker.Call(SendVoiceChatCore, who);
		}

		internal void SendVoiceChatCore(UIA3Automation automation, string who)
		{
			if (string.IsNullOrWhiteSpace(who))
			{
				var chatInfo = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
				if (!chatInfo.CanTalk())
				{
					return;
				}
			}
			else
			{
				var result = _Client.Conversations.SearchWhoCore(automation, who);
				if (!result)
					return;
			}
			RandomWait.Wait(300, 1200);
			var root = this.content.Root;
			if (root == null)
				return;
			var button = root.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("语音通话").And(cf.ByAutomationId("voip_button"))))?.AsButton();
			if (button == null)
				return;
			button.DrawHighlightExt();
			// var point = button.BoundingRectangle.SafeRandomPoint();
			button.ClickEnhance(_Client.MainWindow);
			//等候语音通话窗口出现，最多等候2秒钟
			var windowResult = Retry.WhileNull(() => _Client.MainWindow.FindFirstByXPath("/Window[@Name='Weixin']/MenuItem[@Name='语音通话']"), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
			if (windowResult.Success)
			{
				var menuItem = windowResult.Result.AsMenuItem();
				menuItem.DrawHighlightExt();
				menuItem.ClickEnhance(_Client.MainWindow);
			}
		}

		/// <summary>
		/// 发起单人视频聊天
		/// </summary>
		/// <param name="who">好友昵称,可以为空，如果为空，则发送到当前聊天窗口</param>
		public async Task SendVedioChat(string who)
		{
			await WeChatInvoker.Call(SendVedioChatCore, who);
		}

		internal void SendVedioChatCore(UIA3Automation automation, string who)
		{
			if (string.IsNullOrWhiteSpace(who))
			{
				var chatInfo = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
				if (!chatInfo.CanTalk())
				{
					return;
				}
			}
			else
			{
				var result = _Client.Conversations.SearchWhoCore(automation, who);
				if (!result)
					return;
			}
			RandomWait.Wait(300, 1200);
			var root = this.content.Root;
			if (root == null)
				return;
			var button = root.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("语音通话").And(cf.ByAutomationId("voip_button"))))?.AsButton();
			if (button == null)
				return;
			button.DrawHighlightExt();
			// var point = button.BoundingRectangle.SafeRandomPoint();
			button.ClickEnhance(_Client.MainWindow);
			//等候语音通话窗口出现，最多等候2秒钟
			var windowResult = Retry.WhileNull(() => _Client.MainWindow.FindFirstByXPath("/Window[@Name='Weixin']/MenuItem[@Name='视频通话']"), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
			if (windowResult.Success)
			{
				var menuItem = windowResult.Result.AsMenuItem();
				menuItem.DrawHighlightExt();
				menuItem.ClickEnhance(_Client.MainWindow);
			}
		}

		/// <summary>
		/// 发起多人语音聊天，适用于群聊发起语音聊天
		/// </summary>
		/// <param name="who">群聊名称,可以为空，如果为空，则发送到当前聊天窗口</param>
		/// <param name="partner">参与者，好友昵称列表,必须是群聊成员</param>
		public async Task SendVoiceChats(string who, string[] partner)
		{
			await WeChatInvoker.Call(SendVoiceChatsCore, who, partner);
		}

		private void SendVoiceChatsCore(UIA3Automation automation, string who, string[] partner)
		{
			if (string.IsNullOrWhiteSpace(who))
			{
				//可能没有选择聊天对象，如果没有选择聊天对象，则不发送.
				// if (unSelectChatItem())
				//     return;
				var chatInfo = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
				if (!chatInfo.CanTalk())
				{
					return;
				}
			}
			else
			{
				var result = _Client.Conversations.SearchWhoCore(automation, who);
				if (!result)
					return;
			}
			RandomWait.Wait(300, 1200);
			var filter = partner.Where(u => u != _Client.NickName).ToList().ToArray();
			var root = this.content.Root;
			if (root == null)
				return;
			var button = root.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("语音通话").And(cf.ByAutomationId("voip_button"))))?.AsButton();
			if (button == null)
				return;
			button.DrawHighlightExt();
			// var point = button.BoundingRectangle.SafeRandomPoint();
			button.ClickEnhance(_Client.MainWindow);
			//等候语音通话窗口出现，最多等候2秒钟
			var windowResult = Retry.WhileNull(() => _Client.MainWindow.FindFirstByXPath("/Window[@Name='微信选择成员']"), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
			if (windowResult.Success)
			{
				var selectWindow = windowResult.Result;
				selectWindow.DrawHighlightExt();
				var listBox = selectWindow.FindFirstDescendant(cf => cf.ByControlType(ControlType.List).And(cf.ByAutomationId("sp_to_select_contact_list")).And(cf.ByName("请勾选需要添加的联系人")))?.AsListBox();
				listBox?.DrawHighlightExt();
				if (listBox != null)
				{
					var lastItemName = string.Empty;
					var point = listBox.BoundingRectangle.SafeRandomPoint();
					Mouse.Position = point;
					var index = 0;
					var oldItems = new AutomationElement[] { };
					var compare = new AutomationElementComparer();
					while (index < 2)
					{
						var items = listBox.FindAllChildren(cf => cf.ByControlType(ControlType.CheckBox));
						var exceptItems = items.Except(oldItems, new AutomationElementComparer()).ToArray();
						if (exceptItems.Length > 0)
						{
							oldItems = items;
						}
						else
						{
							break;
						}
						foreach (var item in items)
						{
							var name = item.Name;
							if (filter.Contains(name))
							{
								var checkBox = item.AsCheckBox();
								if (checkBox.IsPatternSupported(checkBox.Automation.PatternLibrary.TogglePattern))
								{
									var pattern = checkBox.Patterns.Toggle.Pattern;
									if (pattern.ToggleState != ToggleState.On)
									{
										//可能有些项目超出底部可视范围了，需要滚动才能看到，滚动到该项目位置
										if (item.BoundingRectangle.Y + item.BoundingRectangle.Height > listBox.BoundingRectangle.Y + listBox.BoundingRectangle.Height)
										{
											Mouse.Position = point;
											Mouse.Scroll(-1);
											RandomWait.Wait(200, 500);
										}
										if (item.BoundingRectangle.Y < listBox.BoundingRectangle.Y)
										{
											Mouse.Position = point;
											Mouse.Scroll(1);
											RandomWait.Wait(200, 500);
										}
										item.DrawHighlightExt();
										var itemPoint = item.BoundingRectangle.SafeRandomPoint();
										Mouse.Position = itemPoint;
										Mouse.Click();
										RandomWait.Wait(200, 500);
									}
								}
							}
						}
						if (items.LastOrDefault() != null)
						{
							if (lastItemName.Equals(items.LastOrDefault().Name))
							{
								index++;
								break;
							}
							else
							{
								index = 0;
							}
							lastItemName = items.LastOrDefault().Name;
						}
						else
						{
							break;
						}
						Mouse.Position = point;
						Mouse.Scroll(-3);
						RandomWait.Wait(50, 500);
					}

					//点击确定按钮
					var path = @"/Window/Group/Group/Button[@AutomationId='confirm_btn'][@Name='完成']";
					var confirmButtonResult = Retry.WhileNull(() => _Client.MainWindow.FindFirstByXPath(path)?.AsButton(), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
					if (confirmButtonResult.Success)
					{
						var confirmButton = confirmButtonResult.Result;
						confirmButton.DrawHighlightExt();
						confirmButton.ClickEnhance(_Client.MainWindow);
					}
				}
			}
		}

		/// <summary>
		/// 发送语音消息,此功能依赖虚拟声卡：Cable input/Cable output
		/// 请在声音-->设置-->将输入设备改成: Cable output
		/// 如果没有安装虚拟声卡，请在:https://github.com/alexzhao189/wechatautosdk/blob/main/Resources/VBCABLE_Driver_Pack45.zip下载
		/// </summary>
		/// <param name="who">好友昵称或群聊名称</param>
		/// <param name="filePath">语音文件路径</param>
		public async Task SendVoiceMessage(string who, string filePath)
		{
			if (string.IsNullOrWhiteSpace(who))
			{
				var chatInfo = await _Client.ChatContent.ChatHeader.GetTitle();
				if (!chatInfo.CanTalk())
				{
					return;
				}
			}
			else
			{
				var result = await _Client.Conversations.Search(who);
				if (!result)
					return;
			}
			RandomWait.Wait(300, 1200);

			await WeChatInvoker.Call(SendVoiceMessageCore, filePath);
		}
		/// <summary>
		/// 给本聊天窗口发送语音消息，请确保本聊天窗口可用.
		/// 请在声音-->设置-->将输入设备改成: Cable output
		/// 如果没有安装虚拟声卡，请在:https://github.com/alexzhao189/wechatautosdk/blob/main/Resources/VBCABLE_Driver_Pack45.zip下载
		/// </summary>
		/// <param name="filePath">语音文件路径</param>
		/// <returns></returns>
		public async Task SendVoiceMessage(string filePath)
		{
			await WeChatInvoker.Call(SendVoiceMessageCore, filePath);
		}

		public async Task SendStreamingVoiceMessage(string who, string requestBody)
		{
			if (string.IsNullOrWhiteSpace(who))
			{
				var chatInfo = await _Client.ChatContent.ChatHeader.GetTitle();
				if (!chatInfo.CanTalk())
					throw new InvalidOperationException("The current WeChat conversation cannot receive voice messages.");
			}
			else
			{
				var result = await _Client.Conversations.Search(who);
				if (!result)
					throw new InvalidOperationException($"WeChat conversation was not found: {who}");
			}
			if (string.IsNullOrWhiteSpace(requestBody) || requestBody.Length > 10_000)
				throw new ArgumentException("CosyVoice stream request is empty or too large.", nameof(requestBody));

			await WeChatInvoker.Call(SendStreamingVoiceMessageCore, requestBody);
		}
		/// <summary>
		/// 文字转语音发送
		/// 工作原理： 通过音频大模型从文字转成语音后，再通过微信发送指定的好友/群聊
		/// 注：系统默认支持: 阿里千问 Qwen3-TTS系列 模型
		/// 为什么选择阿里千问 Qwen3-TTS系列 模型？
		/// 1. 阿里千问 Qwen3-TTS系列 在国际上的语音合成领域也是第一T队;
		/// 2. 完美支持：声音克隆、声音设计、可以通过指令方便控制语速、情感和语言风格、聊天自然，可以停顿、笑等、为未来的AI 电话/语音 聊天做准备
		/// 注：本方法仅支持 通义千问 的系统音色，如果需要克隆声音或者创建声音，请使用其他的api
		/// </summary>
		/// <param name="apiKey">千问的api key</param>
		/// <param name="who">好友或者群聊，可以为空，如果为空，则为当前焦点聊天窗口</param>
		/// <param name="message">文本消息</param>
		/// <param name="options">声音选项，用于指定模型、音色等</param>
		/// <param name="customProcess">如果系统提供的大模型不满足使用，可以自定义文字转语音方法</param>
		/// <returns></returns>
		public async Task SendVoiceMessageWithTTS(string who, string apiKey, string message, VoiceOptions options = null, Func<string, string> customProcess = null)
		{
			if (string.IsNullOrWhiteSpace(who))
			{
				var chatInfo = await _Client.ChatContent.ChatHeader.GetTitle();
				if (!chatInfo.CanTalk())
				{
					return;
				}
			}
			else
			{
				var result = await _Client.Conversations.Search(who);
				if (!result)
					return;
			}
			RandomWait.Wait(300, 1200);
			await WeChatInvoker.Call(SendVoiceMessageFromTTSCore, apiKey, message, options, customProcess);
		}

		internal void SendVoiceMessageFromTTSCore(UIA3Automation automation, string apiKey, string message, VoiceOptions options, Func<string, string> customProcess)
		{
			var filePath = "";
			if (customProcess != null)
			{
				//使用自定义的TTS方法
				filePath = customProcess(message);
			}
			else
			{
				//使用系统提供的TTS方法
				filePath = _SystemVoiceProvider(apiKey, message, options);
			}
			SendVoiceMessageCore(automation, filePath);
		}


		private string _SystemVoiceProvider(string apiKey, string message, VoiceOptions options)
		{
			var service = _serviceProvider.GetRequiredService<QwenClientService>();
			var result = service.MultiModalConversationCall(apiKey, message, options).GetAwaiter().GetResult();
			return result;
		}

		private void SendVoiceMessageCore(UIA3Automation automation, string filePath)
		{
			var chatInfo = this._Client.ChatContent.ChatHeader.GetTitleCore(automation);
			if (!chatInfo.CanTalk())
				return;
			var device = _CheckVirtualSoudDevices();
			using var captureRoute = AudioEndpointRoute.UseCaptureDevice("CABLE Output");
			this._Client.MainWindow.Focus();
			using var audioFile = new AudioFileReader(filePath);
			var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Custom/Group/Group/Group/ToolBar/Group/Group/Button[@Name='发语音 ( 按住右 Alt )']";
			var buttonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(3), TimeSpan.FromMilliseconds(200));
			if (!buttonRetry.Success)
				return;
			var point = buttonRetry.Result.BoundingRectangle.SafeRandomPoint();
			Mouse.Position = point;
			RandomWait.Wait(300, 900);
			SupperMouseKey.LeftClick();
			try
			{
				RandomWait.Wait(600, 1200);
				using var output = new WasapiOut(
					device,
					AudioClientShareMode.Shared,
					false,
					100);
				output.Init(audioFile);
				output.Play();

				while (output.PlaybackState == PlaybackState.Playing)
				{
					Thread.Sleep(100);
				}

				RandomWait.Wait(600, 1500);
			}
			finally
			{
				point = point.Confusion(30, 2);
				Mouse.MoveTo(point);
				RandomWait.Wait(300, 900);
				SupperMouseKey.LeftClick();
				RandomWait.Wait(300, 900);
				point = point.Confusion(100, 100);
				Mouse.MoveTo(point);
			}
		}

		private void SendStreamingVoiceMessageCore(UIA3Automation automation, string requestBody)
		{
			var chatInfo = this._Client.ChatContent.ChatHeader.GetTitleCore(automation);
			if (!chatInfo.CanTalk())
				return;
			var device = _CheckVirtualSoudDevices();
			using var captureRoute = AudioEndpointRoute.UseCaptureDevice("CABLE Output");
			WinApi.ActivateWindow((IntPtr)this._Client.MainWindow.Properties.NativeWindowHandle.Value);
			this._Client.MainWindow.Focus();

			using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(120) };
			using var request = new HttpRequestMessage(
				HttpMethod.Post,
				"http://127.0.0.1:50001/v1/audio/speech/stream"
			);
			request.Content = new StringContent(requestBody, Encoding.UTF8, "application/json");
			using var response = http.SendAsync(
				request,
				HttpCompletionOption.ResponseHeadersRead
			).GetAwaiter().GetResult();
			response.EnsureSuccessStatusCode();
			if (!response.Headers.TryGetValues("X-Audio-Format", out var formats)
				|| !formats.Contains("pcm_s16le"))
				throw new InvalidDataException("CosyVoice returned an unexpected stream format.");

			using var input = response.Content.ReadAsStreamAsync().GetAwaiter().GetResult();
			var provider = new BufferedWaveProvider(new WaveFormat(24_000, 16, 1))
			{
				BufferDuration = TimeSpan.FromMinutes(5),
				DiscardOnBufferOverflow = false,
				ReadFully = true,
			};
			var readBuffer = new byte[9_600];
			var initialBytes = 0;
			while (initialBytes < readBuffer.Length)
			{
				var read = input.Read(readBuffer, initialBytes, readBuffer.Length - initialBytes);
				if (read == 0)
					break;
				initialBytes += read;
			}
			if (initialBytes == 0)
				throw new InvalidDataException("CosyVoice returned an empty PCM stream.");
			provider.AddSamples(readBuffer, 0, initialBytes);

			var producer = Task.Run(() =>
			{
				while (true)
				{
					var read = input.Read(readBuffer, 0, readBuffer.Length);
					if (read == 0)
						break;
					provider.AddSamples(readBuffer, 0, read);
				}
			});

			var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Custom/Group/Group/Group/ToolBar/Group/Group/Button[@Name='发语音 ( 按住右 Alt )']";
			var buttonRetry = Retry.WhileNull(
				() => this._Client.MainWindow.FindFirstByXPath(path),
				TimeSpan.FromSeconds(3),
				TimeSpan.FromMilliseconds(200)
			);
			if (!buttonRetry.Success)
				throw new InvalidOperationException("WeChat voice-record button was not found.");
			var point = buttonRetry.Result.BoundingRectangle.SafeRandomPoint();
			Mouse.Position = point;
			SupperMouseKey.LeftClick();

			try
			{
				// WeChat needs time to switch the toolbar into recording state.
				// Starting playback too early silently drops the first (or entire)
				// stream while still returning success to the caller.
				Thread.Sleep(700);
				using var output = new WasapiOut(
					device,
					AudioClientShareMode.Shared,
					false,
					100
				);
				output.Init(provider);
				output.Play();
				while (!producer.IsCompleted || provider.BufferedBytes > 0)
					Thread.Sleep(20);
				producer.GetAwaiter().GetResult();
				// Let WeChat consume the virtual capture tail before stopping.
				Thread.Sleep(900);
				output.Stop();
			}
			finally
			{
				point = point.Confusion(30, 2);
				Mouse.MoveTo(point);
				SupperMouseKey.LeftClick();
				Thread.Sleep(700);
				Mouse.MoveTo(point.Confusion(100, 100));
			}
		}

		private MMDevice _CheckVirtualSoudDevices()
		{
			MMDevice device = null;
			var enumerator = new MMDeviceEnumerator();
			// 播放设备
			var renderDevices = enumerator.EnumerateAudioEndPoints(
				DataFlow.Render,
				DeviceState.Active);
			device = renderDevices.Where(x => x.FriendlyName.Contains("CABLE Input")).FirstOrDefault();
			if (device == null)
				throw new Exception("请先安装Cable input/Cable output,可以在：https://github.com/alexzhao189/wechatautosdk/blob/main/Resources/VBCABLE_Driver_Pack45.zip 下载安装");
			var captureDevices = enumerator.EnumerateAudioEndPoints(
				DataFlow.Capture,
				DeviceState.Active);
			if (captureDevices.Where(x => x.FriendlyName.Contains("CABLE Output")).Count() == 0)
				throw new Exception("请先安装Cable input/Cable output,可以在：https://github.com/alexzhao189/wechatautosdk/blob/main/Resources/VBCABLE_Driver_Pack45.zip 下载安装");
			return device;
		}

		/// <summary>
		/// 通过文本发送语音消息，需要下载模型并配置好环境，文本转语音后发送
		/// </summary>
		/// <param name="who">好友昵称或群聊名称</param>
		/// <param name="message">要转换为语音的文本消息</param>
		/// <param name="textToVoiceFunc">文本转语音的函数，参数为要转换的文本，返回值为生成的语音文件路径,如果不提供，则使用默认的文本转语音功能(默认使用whisper)，当然你也可以提供自己的实现（如连接到外部平台的API）</param>
		/// <returns></returns>
		public async Task SendVoiceMessage(string who, string message, Func<string, Task<string>> textToVoiceFunc = default)
		{

		}


		internal TextBox _GetContentArea(AutomationElement root)
		{
			var text = root.FindFirstByXPath(@"/Custom/Group/Group/Group/Group/Edit[@AutomationId='chat_input_field']").AsTextBox();
			return text;
		}
		/// <summary>
		/// 发送消息
		/// </summary>
		/// <param name="who">被发送消息的好友名称/群聊名称</param>
		/// <param name="message">文本消息内容</param>
		/// <param name="atUser">@的好友，可以多个，在群聊中使用</param>
		/// <param name="refer">引用的对话内容,请参考<see cref="ChatRefer"/></param>
		/// <param name="cancellationToken">Cancels the prepared message before the final send action.</param>
		/// <returns></returns>
		public async Task SendMessage(string who, string message, OneOf<string, string[], List<string>> atUser = default, ChatRefer refer = null, CancellationToken cancellationToken = default)
		{
			if (string.IsNullOrWhiteSpace(message))
				return;
			await WeChatInvoker.Call(automation => SendMessageExt(automation, who, message, atUser, refer, cancellationToken));
		}
		/// <summary>
		/// 发送消息,给当前窗口发送消息
		/// </summary>
		/// <param name="message">消息内容</param>
		/// <param name="atUser">被@的好友</param>
		/// <param name="refer">引用的对话内容,请参考<see cref="ChatRefer"/></param>
		/// <param name="cancellationToken">Cancels the prepared message before the final send action.</param>
		public async Task SendMessage(string message, OneOf<string, string[], List<string>> atUser = default, ChatRefer refer = null, CancellationToken cancellationToken = default)
		{
			if (string.IsNullOrWhiteSpace(message))
				return;
			await WeChatInvoker.Call(automation => SendMessageCore(automation, message, atUser, refer, cancellationToken));
		}

		private void SendMessageExt(UIA3Automation automation, string who, string message, OneOf<string, string[], List<string>> atUser = default, ChatRefer refer = null, CancellationToken cancellationToken = default)
		{
			cancellationToken.ThrowIfCancellationRequested();
			string targetTitle;
			if (string.IsNullOrWhiteSpace(who))
			{
				var chatInfo = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
				if (!chatInfo.CanTalk())
				{
					return;
				}
				targetTitle = chatInfo.Title;
			}
			else
			{
				var result = _Client.Conversations.SearchWhoCore(automation, who);
				if (!result)
					throw new InvalidOperationException($"找不到会话：{who}");
				targetTitle = who;
			}
			cancellationToken.ThrowIfCancellationRequested();
			RandomWait.Wait(300, 1200);
			SendMessageCore(automation, message, atUser, refer, cancellationToken);
			_Client.MessageMonitor.RecordOutgoingMessageCore(automation, targetTitle, message);
		}
		public async Task SendFile(string who, string[] files)
		{
			if (string.IsNullOrWhiteSpace(who) || files.Length == 0)
				return;
			await WeChatInvoker.Call(SendFileExt, who, files);
		}
		private void SendFileExt(UIA3Automation automation, string who, string[] files)
		{
			if (string.IsNullOrWhiteSpace(who))
			{
				//可能没有选择聊天对象，如果没有选择聊天对象，则不发送.
				// if (unSelectChatItem())
				//     return;
				var chatInfo = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
				if (!chatInfo.CanTalk())
				{
					return;
				}
			}
			else
			{
				var result = _Client.Conversations.SearchWhoCore(automation, who);
				if (!result)
					return;
			}
			RandomWait.Wait(100, 600);
			SendFileCore(automation, files);
		}
		/// <summary>
		/// 检查是否是选中状态.
		/// </summary>
		/// <returns></returns>
		internal bool unSelectChatItem() => !this._Client.Conversations.CheckSelectState();


		internal void SendMessageCore(UIA3Automation automation, string message, OneOf<string, string[], List<string>> atUser, ChatRefer refer = null, CancellationToken cancellationToken = default)
		{
			cancellationToken.ThrowIfCancellationRequested();
			if (string.IsNullOrWhiteSpace(message))
				return;
			var root = this.content.Root;
			if (root == null)
				return;
			root.DrawHighlightExt();
			var ContentArea = _GetContentArea(root);
			if (ContentArea == null)
				return;
			ContentArea.DrawHighlightExt();

			if (refer != null && refer.Message != null)
			{
				var referenced = _PopupMenu(refer) || _DoReferAction(refer, automation);
				if (!referenced)
					throw new InvalidOperationException("找不到要引用的消息，已取消发送以避免降级为普通回复。");
			}
			if (cancellationToken.IsCancellationRequested)
			{
				CancelPreparedMessage(ContentArea);
				cancellationToken.ThrowIfCancellationRequested();
			}

			if (atUser.Value == default)
			{
				_Client.MainWindow.Focus();
				__InputText(ContentArea, message, cancellationToken);
			}
			else
			{
				var atUserList = atUser.IsT0 ? new List<string> { atUser.AsT0 } : atUser.IsT1 ?
					atUser.AsT1.ToList() : atUser.AsT2;
				__AtUserInputText(atUserList, ContentArea, message, cancellationToken);
			}
		}

		private bool _DoReferAction(ChatRefer refer, UIA3Automation automation)
		{
			var historyButton = this._Client.ChatContent.MessageBubbleList.HistoryButton;
			if (historyButton == null)
				return false;
			HeaderInfo title = this._Client.ChatContent.ChatHeader.GetTitleCore(automation);
			if (!title.CanTalk())
				return false;
			Window subWin = _GetPopupHistoryWin(automation, title, historyButton);
			if (subWin == null)
				return false;
			// int targetX = _Client.MainWindow.BoundingRectangle.X + (int)((_Client.MainWindow.BoundingRectangle.Width - subWin.BoundingRectangle.Width) / 2);
			// int targetY = _Client.MainWindow.BoundingRectangle.Y + (int)((_Client.MainWindow.BoundingRectangle.Height - subWin.BoundingRectangle.Height) / 2);
			// subWin.Move(targetX, targetY);  //移动子窗口至主窗口中间
			_Client.MoveWinToMainCenter(subWin);
			RandomWait.Wait(600, 1200);
			var referenced = false;
			try
			{
				if (refer.Date != DateOnly.MinValue)
				{
					var isSelected = _SelectDate(refer.Date, subWin);
					if (!isSelected)
						return false;
				}
				//筛选内容.
				_FilterContent(refer, subWin);   //筛选框填入内容
				referenced = _FindContent(refer, subWin);
			}
			finally
			{
				if (refer.IsCloseSearchWin)
				{
					subWin.Focus();
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
					this._Client.MainWindow.Focus();
				}
			}
			return referenced;
		}

		private bool _FindContent(ChatRefer refer, Window subWin)
		{
			var path = "/Group/Group/Group/Group/List[@AutomationId='search_message_list']";
			var listRetry = Retry.WhileNull(() => subWin.FindFirstByXPath(path), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
			if (listRetry.Success)
			{
				var list = listRetry.Result.AsListBox();
				var subList = list.Items;
				AutomationElement el = null;
				foreach (var item in subList.Reverse())
				{
					if (ReferenceMessageMatches(item.Name, refer.Message.Message))
					{
						el = item;
						break;
					}
				}
				if (el == null)
					return false;
				var index = 0;
				while (el.BoundingRectangle.Y < list.BoundingRectangle.Y && index < 3)
				{
					SupperMouseKey.Scroll(2);
					RandomWait.Wait(200, 600);
					index++;
				}
				index = 0;
				while (el.BoundingRectangle.Y + 70 > list.BoundingRectangle.Y + list.BoundingRectangle.Height)
				{
					SupperMouseKey.Scroll(-2);
					RandomWait.Wait(200, 600);
					index++;
				}


				Mouse.Position = el.BoundingRectangle.SafeRandomPoint();
				RandomWait.Wait(300, 900);
				var point = Mouse.Position.Confusion(20, 2);
				SupperMouseKey.MoveTo(point);
				RandomWait.Wait(300, 600);
				//确定聊天信息
				using Mat mat = this._Client.OcrEngee.GetMatFromElement(el);
				var result = this._Client.OcrEngee.Detect(mat.ToBitmap(), 0, mat.Width, doAngle: false, mostAngle: false, isTest: false);
				_logger.Debug(result.ToString());
				var locationItem = result.TextBlocks.Where(u => !string.IsNullOrWhiteSpace(u.Text) && u.Text.Equals("定位到聊天位置")).FirstOrDefault();
				if (locationItem != null)
				{
					point = new Point(el.BoundingRectangle.X + locationItem.BoxPoints[0].X + ((int)((locationItem.BoxPoints[2].X - locationItem.BoxPoints[0].X) / 2)),
					el.BoundingRectangle.Y + locationItem.BoxPoints[0].Y + ((int)((locationItem.BoxPoints[2].Y - locationItem.BoxPoints[0].Y) / 2)));
					Mouse.Position = point;
					RandomWait.Wait(200, 1200);
					SupperMouseKey.LeftClick();
					RandomWait.Wait(200, 1200);
					//这里弹窗
					return _PopupMenu(refer);
				}
			}
			return false;
		}

		private bool _PopupMenu(ChatRefer refer)
		{
			var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Custom/Group/Group/List[@AutomationId='chat_message_list'][@ClassName='mmui::RecyclerListView'][@Name='消息'] | /Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Custom/Group/List[@AutomationId='chat_message_list'][@ClassName='mmui::RecyclerListView'][@Name='消息']"; ;
			var listRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
			if (listRetry.Success)
			{
				var list = listRetry.Result.AsListBox();
				var listItems = list.Items;
				foreach (var item in listItems.Reverse())
				{
					if (ReferenceMessageMatches(item.Name, refer.Message.Message))
					{
						var index = 0;
						while (item.BoundingRectangle.Y < list.BoundingRectangle.Y && index < 2)
						{
							SupperMouseKey.Scroll(2);
							RandomWait.Wait(100, 250);
							index++;
						}
						var incoming = !string.Equals(
							refer.Message.Who?.Trim(),
							"我",
							StringComparison.Ordinal);
						var success = incoming ? LeftRetry(item) : RightRetry(item);
						if (success)
							return true;
					}
				}
			}
			return false;
		}

		private static bool ReferenceMessageMatches(string itemName, string referenceMessage)
		{
			var item = NormalizeReferenceMessage(itemName);
			var reference = NormalizeReferenceMessage(referenceMessage);
			return item.Length > 0
				&& reference.Length > 0
				&& (string.Equals(item, reference, StringComparison.Ordinal)
					|| item.Contains(reference, StringComparison.Ordinal)
					|| reference.Contains(item, StringComparison.Ordinal));
		}

		private static string NormalizeReferenceMessage(string value)
		{
			var normalized = (value ?? string.Empty).Trim();
			if (normalized.Length >= 2 && normalized[0] == '[' && normalized[^1] == ']')
				normalized = normalized[1..^1].Trim();
			return normalized;
		}

		private bool LeftRetry(ListBoxItem item)
		{
			var point = new Point(item.BoundingRectangle.X + 96 + 8, item.BoundingRectangle.Y + 23 + 8);
			Mouse.Position = point;
			RandomWait.Wait(40, 120);
			SupperMouseKey.RightClick();
			RandomWait.Wait(80, 180);
			var menuItemRetry = Retry.WhileNull(() => this._Client.MainWindow.Automation.GetDesktop()
				.FindFirstDescendant(cf => cf.ByControlType(ControlType.MenuItem).And(cf.ByName("引用"))),
				TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
			if (menuItemRetry.Success)
			{
				point = menuItemRetry.Result.BoundingRectangle.SafeRandomPoint();
				SupperMouseKey.MoveTo(point);
				RandomWait.Wait(40, 120);
				SupperMouseKey.LeftClick();
				RandomWait.Wait(100, 250);
				return true;
			}

			return false;
		}

		private bool RightRetry(ListBoxItem item)
		{
			var point = new Point(item.BoundingRectangle.X + item.BoundingRectangle.Width - 96 - 8, item.BoundingRectangle.Y + 23 + 8);
			Mouse.Position = point;
			RandomWait.Wait(40, 120);
			SupperMouseKey.RightClick();
			RandomWait.Wait(80, 180);
			var menuItemRetry = Retry.WhileNull(() => this._Client.MainWindow.Automation.GetDesktop()
				.FindFirstDescendant(cf => cf.ByControlType(ControlType.MenuItem).And(cf.ByName("引用"))),
				TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
			if (menuItemRetry.Success)
			{
				point = menuItemRetry.Result.BoundingRectangle.SafeRandomPoint();
				SupperMouseKey.MoveTo(point);
				RandomWait.Wait(40, 120);
				SupperMouseKey.LeftClick();
				RandomWait.Wait(100, 250);
				return true;
			}

			return false;
		}

		private void _FilterContent(ChatRefer refer, Window subWin)
		{
			var path = "/Group/Group/Group/Group/Edit[@Name='搜索'][@ClassName='mmui::XValidatorTextEdit']";
			var searchRetry = Retry.WhileNull(() => subWin.FindFirstByXPath(path).AsTextBox(), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));
			if (searchRetry.Success)
			{
				var searchEdit = searchRetry.Result;
				subWin.Focus();
				var point = searchEdit.BoundingRectangle.SafeRandomPoint();
				SupperMouseKey.MoveTo(point);
				RandomWait.Wait(200, 1200);
				SupperMouseKey.LeftClick();
				RandomWait.Wait(200, 900);
				SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
				RandomWait.Wait(200, 900);
				SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
				RandomWait.Wait(200, 900);
				string[] contents = refer.Message.Message.Split('\n');
				ClipboardHelper.SetText(NormalizeReferenceMessage(contents[0]));
				SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
				RandomWait.Wait(200, 1500);

			}
		}

		private bool _SelectDate(DateOnly date, Window window)
		{
			var yearStr = date.Year.ToString() + "年";
			var monthStr = date.Month.ToString() + "月";
			var path = "/Group/Group/Group/Group/Group/Group/Tab/TabItem[@AutomationId='qt_scrollarea_viewport.button_container.record_type_datetime'][@Name='日期']";
			var tabItemRetry = Retry.WhileNull(() => window.FindFirstByXPath(path), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));
			if (tabItemRetry.Success)
			{
				var item = tabItemRetry.Result;
				var point = item.BoundingRectangle.SafeRandomPoint();
				SupperMouseKey.LeftClick(point);
				RandomWait.Wait(300, 900);
				var popupWinRetry = Retry.WhileNull(() => window.Automation.GetDesktop().FindFirstByXPath("/Window[@Name='Weixin']/Group/Text[@Name='选择发送日期']"), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));
				if (popupWinRetry.Success)
				{
					var smallTitle = popupWinRetry.Result;
					var popWin = smallTitle.GetParent().GetParent();
					popWin.DrawHighlightExt();
					//检查年份与月份，如果月份不合适，则选择月份.
					var yearButton = smallTitle.GetSibling(1);  //目前暂时实现不跨年，会员提示再改
					var monthButton = yearButton.GetSibling(1);
					var currentMonth = monthButton.FindFirstChild(cf => cf.ByControlType(ControlType.Text)).Name.Trim();
					if (currentMonth != monthStr)
					{
						point = monthButton.BoundingRectangle.SafeRandomPoint();
						SupperMouseKey.MoveTo(point);
						RandomWait.Wait(800, 1500);
						SupperMouseKey.LeftClick();
						//等候需要的月份出现.
						RandomWait.Wait(600, 1200);
						var monthWinRetry = Retry.WhileNull(() => popWin.FindFirstChild(cf => cf.ByName("Weixin")), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));
						if (monthWinRetry.Success)
						{
							var childItem = monthWinRetry.Result.FindFirstChild(cf => cf.ByControlType(ControlType.MenuItem).And(cf.ByName(monthStr)));
							if (childItem != null)
							{
								point = childItem.BoundingRectangle.SafeRandomPoint();
								SupperMouseKey.MoveTo(point);
								RandomWait.Wait(150, 900);
								SupperMouseKey.LeftClick();
								RandomWait.Wait(100, 300);
							}
							else
							{
								return false;
							}
						}
						else
						{
							return false;
						}
					}
					//ocr识别日期，然后点击,注意：有些日期可能没有记录，点击不进去
					var container = monthButton.GetSibling(1);
					if (container != null)
					{
						using Mat mat1 = this._Client.OcrEngee.GetMatFromElement(container);
						var dpi100Top = 20;   //dpi在100%时候顶部距离
						var baseTop = (int)(dpi100Top * DpiHelper.GetScaleForWindow(this._Client.MainWindow.Properties.NativeWindowHandle));
						Rectangle rectangle = new Rectangle(0, baseTop, mat1.Width, mat1.Height - baseTop);
						using Mat mat2 = new Mat(mat1, rectangle);  //将上面的裁剪25,以保持日期列
						var clickPoint = this._Client.OcrEngee.GetPointFromDateTime(mat2, date, 15, false);
						clickPoint = new Point(clickPoint.X + container.BoundingRectangle.X, clickPoint.Y + baseTop + container.BoundingRectangle.Y);
						SupperMouseKey.MoveTo(clickPoint);
						RandomWait.Wait(800, 1200);
						SupperMouseKey.LeftClick();
						RandomWait.Wait(200, 800);
						//检查日期是否可以点击.
						var findResult = Retry.WhileNotNull(() => window.Automation.GetDesktop().FindFirstByXPath("/Window[@Name='Weixin']/Group/Text[@Name='选择发送日期']"), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));

						return findResult.Success ? findResult.Result : false;
					}
					return false;
				}
			}
			return false;
		}

		//弹出窗口.
		private Window _GetPopupHistoryWin(UIA3Automation automation, HeaderInfo title, Button historyButton)
		{
			var desktop = automation.GetDesktop();
			Window subWin = null;
			var winResult = Retry.WhileNull(() => desktop.FindAllChildren(cf => cf.ByClassName("mmui::SearchMsgUniqueChatWindow").And(cf.ByControlType(ControlType.Window).And(cf.ByProcessId(_Client.MainWindow.Properties.ProcessId)))), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
			if (winResult.Success && winResult.Result.Length > 0)
			{
				//发现窗口，但不确定是否是本窗口
				var subWins = winResult.Result;
				subWin = subWins.FirstOrDefault(u =>
				{
					var name = u.Name.Replace("“", "").Replace("”", "");
					if (name.Contains($"{title.Title}"))
					{
						return true;
					}
					else
					{
						return false;
					}
				}).AsWindow();
				if (subWin == null)
				{
					__ClickChatHistoryButton(historyButton);
				}
				else
				{
					subWin.Focus();
					return subWin;
				}
			}
			else
			{
				//点击弹出历史消息按钮.
				__ClickChatHistoryButton(historyButton);
			}
			//再次检查
			winResult = Retry.WhileNull(() => desktop.FindAllChildren(cf => cf.ByClassName("mmui::SearchMsgUniqueChatWindow").And(cf.ByControlType(ControlType.Window).And(cf.ByProcessId(_Client.MainWindow.Properties.ProcessId)))), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
			if (winResult.Success && winResult.Result.Length > 0)
			{
				var subWins = winResult.Result;
				subWin = subWins.FirstOrDefault(u =>
				{
					var name = u.Name.Replace("“", "").Replace("”", "");
					if (name.Contains($"{title.Title}"))
					{
						return true;
					}
					else
					{
						return false;
					}
				}).AsWindow();
				if (subWin != null)
				{
					subWin.Focus();
					return subWin;
				}
			}
			return null;
		}

		private void __ClickChatHistoryButton(Button invokeButton)
		{
			RandomWait.Wait(100, 800);
			Mouse.Position = invokeButton.BoundingRectangle.SafeRandomPoint();
			RandomWait.Wait(100, 400);
			_Client.MainWindow.Focus();
			SupperMouseKey.LeftClick();
			RandomWait.Wait(300, 900);
		}

		private void __AtUserInputText(List<string> atUsers, TextBox textBox, string message, CancellationToken cancellationToken = default)
		{
			textBox.Focus();
			ClipboardHelper.SetText(message);
			var point = textBox.BoundingRectangle.SafeRandomPoint();
			Mouse.Position = point;
			Mouse.Click();
			__AtUserList(atUsers, textBox);
			textBox.Focus();
			ClipboardHelper.SetText(message);
			RandomWait.Wait(50, 300);
			Keyboard.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
			RandomWait.Wait(50, 800);
			if (cancellationToken.IsCancellationRequested)
			{
				CancelPreparedMessage(textBox);
				cancellationToken.ThrowIfCancellationRequested();
			}
			Keyboard.TypeSimultaneously(VirtualKeyShort.ENTER);
		}

		private void __AtUserList(List<string> atUsers, TextBox textBox)
		{
			RandomWait.Wait(50, 300);
			Keyboard.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
			RandomWait.Wait(50, 300);
			Keyboard.TypeSimultaneously(VirtualKeyShort.BACK);
			RandomWait.Wait(50, 300);

			var path = "/Window[@Name='Weixin']/Group/List[@AutomationId='chat_mention_list']";
			foreach (var name in atUsers)
			{
				if (string.IsNullOrWhiteSpace(name))
					continue;
				var point = textBox.BoundingRectangle.SafeRandomPoint();
				Mouse.Position = point;
				Mouse.Click();
				Keyboard.Type("@");
				var popWinResult = Retry.WhileNull(() => _Client.MainWindow.FindFirstByXPath(path),
					timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
				if (popWinResult.Success)
				{
					var listBox = popWinResult.Result.AsListBox();
					listBox.DrawHighlightExt();
					point = listBox.BoundingRectangle.SafeRandomPoint();
					Mouse.Position = point;
					var isEnd = false;
					var lastItemName = string.Empty;
					while (!isEnd)
					{
						var children = listBox.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem));
						var item = children.FirstOrDefault(u => u.Name.Equals(name));
						if (item != null)
						{
							if (item.BoundingRectangle.Y + item.BoundingRectangle.Height > listBox.BoundingRectangle.Y + listBox.BoundingRectangle.Height)
							{
								Mouse.Scroll(-1);
							}
							item.DrawHighlightExt();
							point = item.BoundingRectangle.SafeRandomPoint();
							Mouse.MoveTo(point);
							Mouse.Click();
							break;
						}
						if (children.LastOrDefault() != null)
						{
							if (lastItemName.Equals(children.LastOrDefault().Name))
							{
								Keyboard.Type(VirtualKeyShort.ESC);
								RandomWait.Wait(200, 800);
								Keyboard.Type(VirtualKeyShort.BACK);
								break;
							}
							lastItemName = children.LastOrDefault().Name;
						}
						else
						{
							break;
						}
						Mouse.Scroll(-2);
						RandomWait.Wait(50, 500);
					}
				}
				else
				{
					Keyboard.Type(virtualKeys: VirtualKeyShort.BACK);
				}
				RandomWait.Wait(500, 1200);
			}
		}

		private void __InputText(TextBox textBox, string message, CancellationToken cancellationToken = default)
		{
			textBox.Focus();
			ClipboardHelper.SetText(message);
			var point = textBox.BoundingRectangle.SafeRandomPoint();
			Mouse.Position = point;
			Mouse.Click();
			RandomWait.Wait(50, 300);
			Keyboard.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
			RandomWait.Wait(50, 300);
			Keyboard.TypeSimultaneously(VirtualKeyShort.BACK);
			RandomWait.Wait(50, 300);
			Keyboard.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
			RandomWait.Wait(50, 800);
			if (cancellationToken.IsCancellationRequested)
			{
				CancelPreparedMessage(textBox);
				cancellationToken.ThrowIfCancellationRequested();
			}
			Keyboard.TypeSimultaneously(VirtualKeyShort.ENTER);
		}

		private static void CancelPreparedMessage(TextBox textBox)
		{
			textBox.Focus();
			Keyboard.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
			Keyboard.TypeSimultaneously(VirtualKeyShort.BACK);
			Keyboard.TypeSimultaneously(VirtualKeyShort.ESC);
		}

		/// <summary>
		/// 发送文件,给当前窗口发送
		/// </summary>
		/// <param name="files">文件路径列表</param>
		public async Task SendFile(string[] files)
		{
			if (files.Length == 0)
				return;
			await WeChatInvoker.Call(SendFileCore, files);
		}

		internal void SendFileCore(UIA3Automation automation, string[] files)
		{
			var root = this.content.Root;
			if (root == null)
				return;
			var textBox = _GetContentArea(root);
			if (textBox == null)
				return;

			textBox.Focus();
			var point = textBox.BoundingRectangle.SafeRandomPoint();
			Mouse.Position = point;
			Mouse.Click();

			_Client.MainWindow.SilencePasteSimple(files, textBox);
			RandomWait.Wait(300, 1200);
			Keyboard.Type(VirtualKeyShort.ENTER);
		}

		/// <summary>
		/// 发送表情
		/// </summary>
		/// <param name="who">被发送消息的好友名称/群聊名称</param>
		/// <param name="emoji">表情名称或者描述或者索引</param>
		/// <param name="atUserList">被@的好友列表</param>
		public async Task SendEmoji(string who, OneOf<int, string> emoji, List<string> atUserList = null)
		{
			var message = "";
			emoji.Switch(
				(int emojiId) =>
				{
					message = EmojiListHelper.Items.FirstOrDefault(item => item.Index == emojiId)?.Value ?? EmojiListHelper.Items[0].Value;
				},
				(string emojiName) =>
				{
					message = emojiName;
					if (!(message.StartsWith("[") && message.EndsWith("]")))
					{
						message = EmojiListHelper.Items.FirstOrDefault(item => item.Description == emojiName)?.Value ?? message;
					}
				}
			);
			await this.SendMessage(who, message, atUserList);
		}

		/// <summary>
		/// 扫描发送表情面板中的全部分类。普通分类记录控件 Name，自定义表情记录 dHash。
		/// </summary>
		public async Task<StickerCatalogScanResult> ScanAllStickers()
		{
			return await WeChatInvoker.Call<StickerCatalogScanResult>(automation =>
			{
				var root = this.content.Root;
				if (root == null)
					throw new InvalidOperationException("当前没有可用的聊天窗口。");
				var button = root.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("发送表情(Alt+E)")))?.AsButton();
				if (button == null)
					throw new InvalidOperationException("找不到发送表情按钮。");
				button.ClickEnhance(_Client.MainWindow);
				RandomWait.Wait(180, 350);
				try
				{
					var popup = FindStickerPopup(automation);
					if (popup == null)
						throw new InvalidOperationException("找不到微信表情面板弹窗。");
					return this._stickerCatalog.ScanAll(popup, _Client.MainWindow);
				}
				finally
				{
					FocuseSenderCore(automation);
					RandomWait.Wait(80, 180);
				}
			});
		}

		private AutomationElement FindStickerPopup(UIA3Automation automation)
		{
			var processId = _Client.MainWindow.Properties.ProcessId;
			var popupRetry = Retry.WhileNull(
				() => automation.GetDesktop()
					.FindAllChildren(cf => cf.ByProcessId(processId).And(cf.ByClassName("mmui::XPopover")))
					.FirstOrDefault(x => StickerCatalogStore.FindTabs(x).Length > 0),
				timeout: TimeSpan.FromSeconds(2),
				interval: TimeSpan.FromMilliseconds(100));
			return popupRetry.Success ? popupRetry.Result : null;
		}

		/// <summary>
		/// 发送已扫描目录中的表情。普通分类使用 Name，自定义分类使用 dHash。
		/// </summary>
		public async Task SendSticker(string who, string category, string nameOrHash)
		{
			if (string.IsNullOrWhiteSpace(nameOrHash))
				throw new ArgumentException("表情名称或哈希不能为空。", nameof(nameOrHash));
			await WeChatInvoker.Call<string, string, string>(SendStickerCore, who, category ?? "", nameOrHash);
		}

		private void SendStickerCore(UIA3Automation automation, string who, string category, string nameOrHash)
		{
			if (!string.IsNullOrWhiteSpace(who) && !_Client.Conversations.SearchWhoCore(automation, who))
				throw new InvalidOperationException($"找不到会话：{who}");
			RandomWait.Wait(250, 700);
			var root = this.content.Root;
			if (root == null)
				throw new InvalidOperationException("当前没有可用的聊天窗口。");
			var item = string.IsNullOrWhiteSpace(category)
				? this._stickerCatalog.Items.FirstOrDefault(x =>
					x.Name.Equals(nameOrHash, StringComparison.OrdinalIgnoreCase)
					|| x.Hash.Equals(nameOrHash, StringComparison.OrdinalIgnoreCase))
				: this._stickerCatalog.Resolve(category, nameOrHash);
			if (item == null)
				throw new InvalidOperationException("目录中没有这个表情，请先执行 ScanAllStickers。");
			var emojiButton = root.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("发送表情(Alt+E)")))?.AsButton();
			if (emojiButton == null)
				throw new InvalidOperationException("找不到发送表情按钮。");
			emojiButton.ClickEnhance(_Client.MainWindow);
			RandomWait.Wait(180, 350);
			var popup = FindStickerPopup(automation);
			if (popup == null)
				throw new InvalidOperationException("找不到微信表情面板弹窗。");
			var tab = StickerCatalogStore.FindTabs(popup)
				.FirstOrDefault(x => x.Name.Equals(item.Category, StringComparison.Ordinal));
			if (tab == null)
				throw new InvalidOperationException($"找不到表情分类：{item.Category}");
			tab.ClickEnhance(_Client.MainWindow);
			RandomWait.Wait(150, 300);
			var panel = StickerCatalogStore.FindPanel(popup);
			StickerCatalogStore.ScrollToStart(panel);
			AutomationElement selected = null;
			var seenPages = new HashSet<string>(StringComparer.Ordinal);
			var firstCandidatePage = Math.Max(0, item.Page - 1);
			var lastCandidatePage = Math.Min(39, item.Page + 1);
			for (var page = 0; page <= lastCandidatePage && selected == null; page++)
			{
				var cells = item.Mode == "visual"
					? StickerCatalogStore.FindVisualCells(panel)
					: StickerCatalogStore.FindSemanticCells(panel);
				if (cells.Length == 0)
					break;
				var signature = string.Join("|", cells.Select(x => item.Mode == "visual" ? HashOf(x) : x.Name.Trim()));
				if (!seenPages.Add(signature))
					break;
				if (page < firstCandidatePage)
				{
					selected = null;
				}
				else if (item.Mode == "visual")
				{
					var exact = cells.FirstOrDefault(x => HashOf(x).Equals(item.Hash, StringComparison.OrdinalIgnoreCase));
					if (exact != null)
					{
						selected = exact;
					}
					else
					{
						var near = cells.Where(x => HashDistance(HashOf(x), item.Hash) <= 2).ToArray();
						if (near.Length == 1)
							selected = near[0];
					}
				}
				else
				{
					selected = cells.FirstOrDefault(x => x.Name.Trim().Equals(item.Name, StringComparison.OrdinalIgnoreCase));
				}
				if (selected == null)
				{
					var rect = cells[0].BoundingRectangle;
					Mouse.Position = rect.Center();
					Mouse.Scroll(-6);
					RandomWait.Wait(120, 250);
				}
			}
			if (selected == null)
				throw new InvalidOperationException("表情目录已变化或匹配失败，请重新执行 ScanAllStickers。");
			var insertsIntoComposer = item.Category.Equals("默认表情", StringComparison.Ordinal);
			var contentArea = insertsIntoComposer ? _GetContentArea(root) : null;
			if (insertsIntoComposer && contentArea == null)
				throw new InvalidOperationException("找不到聊天输入框，无法发送默认表情。");
			if (insertsIntoComposer && !string.IsNullOrWhiteSpace(contentArea!.Text))
				throw new InvalidOperationException("聊天输入框中已有草稿，为避免误发未发送表情。");
			Mouse.Position = selected.BoundingRectangle.SafeRandomPoint();
			Mouse.Click();
			RandomWait.Wait(250, 500);
			if (insertsIntoComposer)
			{
				var sendButton = root.FindFirstDescendant(cf =>
					cf.ByControlType(ControlType.Button).And(cf.ByName("发送")))?.AsButton();
				if (sendButton == null || !sendButton.IsEnabled)
					throw new InvalidOperationException("表情已插入输入框，但发送按钮不可用。");
				Mouse.Position = sendButton.BoundingRectangle.SafeRandomPoint();
				Mouse.Click();
				RandomWait.Wait(250, 500);
			}
		}

		private static string HashOf(AutomationElement element)
		{
			using var bitmap = element.Capture();
			return bitmap == null ? "" : StickerCatalogStore.DHash(bitmap);
		}

		private static int HashDistance(string left, string right)
		{
			if (string.IsNullOrWhiteSpace(left) || string.IsNullOrWhiteSpace(right))
				return int.MaxValue;
			if (!long.TryParse(left, System.Globalization.NumberStyles.HexNumber, null, out var a)
				|| !long.TryParse(right, System.Globalization.NumberStyles.HexNumber, null, out var b))
				return int.MaxValue;
			var bits = (ulong)(a ^ b);
			var count = 0;
			while (bits != 0) { count += (int)(bits & 1); bits >>= 1; }
			return count;
		}

		/// <summary>
		/// 当前窗口的Sender区域点击，以获得焦点，可以取消系统的消息提醒或者关闭右侧Pane
		/// </summary>
		/// <returns></returns>
		public async Task FocuseSenderInput()
		{
			await WeChatInvoker.Call(FocuseSenderCore);
		}

		internal void FocuseSenderCore(UIA3Automation automation)
		{
			var root = this.content.Root;
			if (root == null)
				return;
			var input = root.FindFirstDescendant(cf => cf.ByAutomationId("chat_input_field").And(cf.ByClassName("mmui::ChatInputField").And(cf.ByControlType(ControlType.Edit)))).AsTextBox();
			if (input == null)
				return;
			//检查是否有右侧边Panel.
			var clickRoot = input.GetParent().GetParent().GetParent().GetParent();
			clickRoot.DrawHighlightExt();
			var rightPane = root.FindFirstDescendant(cf => cf.ByClassName("mmui::ChatRoomMemberInfoView").And(cf.ByControlType(ControlType.Group)));
			System.Drawing.Point point = System.Drawing.Point.Empty;
			if (rightPane != null)
			{
				rightPane.DrawHighlightExt();
				Rectangle rect = new Rectangle(clickRoot.BoundingRectangle.X, clickRoot.BoundingRectangle.Y,
				clickRoot.BoundingRectangle.Width - rightPane.BoundingRectangle.Width, clickRoot.BoundingRectangle.Height);
				point = rect.SafeRandomPoint();
			}
			else
			{
				rightPane = root.FindFirstDescendant(cf => cf.ByClassName("mmui::XView").And(cf.ByControlType(ControlType.Group).And(cf.ByAutomationId("single_chat_info_view"))));
				if (rightPane != null)
				{
					rightPane.DrawHighlightExt();
					Rectangle rect = new Rectangle(clickRoot.BoundingRectangle.X, clickRoot.BoundingRectangle.Y,
					clickRoot.BoundingRectangle.Width - rightPane.BoundingRectangle.Width, clickRoot.BoundingRectangle.Height);
					point = rect.SafeRandomPoint();
				}
				else
				{
					point = clickRoot.BoundingRectangle.SafeRandomPoint();
				}
			}
			//测试.
			//Mouse.MoveTo(point);
			Mouse.Position = point;
			RandomWait.Wait(300, 900);
			Mouse.LeftClick();
			RandomWait.Wait(100, 800);
		}
	}
}
