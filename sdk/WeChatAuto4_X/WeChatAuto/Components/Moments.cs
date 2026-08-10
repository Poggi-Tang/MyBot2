using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.Core.WindowsAPI;
using Microsoft.Extensions.DependencyInjection;
using WeAutoCommon.Models;
using WeAutoCommon.Utils;
using WeChatAuto.Extentions;
using WeChatAuto.Utils;
using WeAutoCommon.Enums;
using System.Threading.Tasks;
using FlaUI.UIA3;
using WeAutoCommon.Extentions;
using System.IO;
using FlaUI.Core;
using MessagePack;
using System.Net.Http;
using System.Drawing;
using WeChatAuto.Options;
using WeChatAuto.Models;
using Emgu.CV.Dai;
using System.Windows.Controls;
using Emgu.CV.Structure;
using WeChatAuto.Services;
using Emgu.CV;
using System.Windows.Media.Imaging;
using System.ComponentModel.DataAnnotations;


namespace WeChatAuto.Components
{
	/// <summary>
	/// 朋友圈操作
	/// </summary>
	public class Moments
	{
		private readonly IServiceProvider _serviceProvider;
		private UIThreadInvoker _uiMainThreadInvoker;
		private AutoLogger<Moments> _logger;
		private WeChatClient _Client;
		internal AutomationElement ToolBar => GetToolBar();

		internal AutomationElement GetToolBar()
		{
			var window = OpenMomentsCore(_uiMainThreadInvoker.Automation);
			if (window == null)
				return null;
			var path = "/Group/Group/Group/ToolBar[@AutomationId='sns_window_tool_bar'][@ClassName='mmui::SNSWindowToolBar']";
			var toolBarRetry = Retry.WhileNull(() => window.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
			return toolBarRetry.Success ? toolBarRetry.Result : null;
		}

		internal Moments(WeChatClient client, UIThreadInvoker uiThreadInvoker, IServiceProvider serviceProvider)
		{
			_logger = serviceProvider.GetRequiredService<AutoLogger<Moments>>();
			_uiMainThreadInvoker = uiThreadInvoker;
			_Client = client;
			_serviceProvider = serviceProvider;
		}

		/// <summary>
		/// 打开朋友圈,如果未打开，则打开朋友圈，如果已经打开了，则窗口提前
		/// </summary>
		/// <returns></returns>
		public async Task<Window> OpenMoments()
		{
			return await WeChatInvoker.Call(OpenMomentsCore);
		}

		internal Window OpenMomentsCore(UIA3Automation automation)
		{
			(bool success, Window win) result = IsOpenMomentsWin(automation);
			if (!result.success)
			{
				this._Client.Navigation.SwitchNavigationCore(automation, NavigationType.朋友圈);
				RandomWait.Wait(600, 1200);
				result = IsOpenMomentsWin(automation);
				if (result.success)
				{
					this._Client.MoveWinToMainCenter(result.win);
					return result.win;
				}
			}
			else
			{
				this._Client.MoveWinToMainCenter(result.win);
				return result.win;
			}
			return null;
		}

		/// <summary>
		/// 是否打开朋友圈
		/// </summary>
		/// <param name="automation"></param>
		/// <returns></returns>
		internal (bool success, Window win) IsOpenMomentsWin(UIA3Automation automation)
		{
			var desktop = automation.GetDesktop();
			var winRetry = Retry.WhileNull(() => desktop.FindFirstChild(cf => cf.ByProcessId(this._Client.MainWindow.Properties.ProcessId).And(cf.ByName("朋友圈")).And(cf.ByAutomationId("SNSWindow"))), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
			return (winRetry.Success, winRetry.Result.AsWindow());
		}
		/// <summary>
		/// 关闭朋友圈
		/// </summary>
		/// <returns></returns>
		public async Task CloseMoments()
		{
			await WeChatInvoker.Call(CloseMomentsCore);
		}

		internal void CloseMomentsCore(UIA3Automation automation)
		{
			(bool success, Window win) result = IsOpenMomentsWin(automation);
			if (result.success)
			{
				result.win.Focus();
				RandomWait.Wait(600, 1200);
				result.win.Close();
				RandomWait.Wait(600, 900);
			}
		}

		/// <summary>
		/// 发送朋友圈
		/// </summary>
		/// <param name="imageFiles">图片列表，可以一个，也可以多个,如果是多个文件，要求在同一个目录中</param>
		/// <param name="content">朋友圈内容</param>
		/// <param name="options">发送选项，请参考<see cref="MomentsOptions"/></param>
		/// <returns>成功还是失败</returns>
		public async Task<bool> AddMoments(List<string> imageFiles, string content, MomentsOptions options = null)
		{
			return await WeChatInvoker.Call(AddMomentsCore, imageFiles, content, options);
		}

		internal bool AddMomentsCore(UIA3Automation automation, List<string> imageFiles, string content, MomentsOptions options)
		{
			var pathResult = CheckImagesValid(imageFiles);
			if (!pathResult.sucess)
				return false;
			var win = OpenMomentsCore(automation);  //打开朋友圈,返回朋友圈窗口
			if (win == null)
				return false;
			var toolBar = this.ToolBar;
			if (toolBar == null)
				return false;
			var sendButton = toolBar.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("发表")));
			var noticeButotn = toolBar.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("消息")));
			var point = noticeButotn.BoundingRectangle.SafeRandomPoint();
			Mouse.Position = point;
			RandomWait.Wait(200, 700);
			SupperMouseKey.MoveTo(sendButton.BoundingRectangle.SafeRandomPoint());
			RandomWait.Wait(200, 700);
			SupperMouseKey.LeftClick();
			var pathRoot = pathResult.path;

			bool result = _ProcessImageFiles(pathRoot, win, imageFiles);
			if (!result)
				return false;

			result = _ProcessContent(automation, content, options, win);
			if (options == null || options.IsCloseMoments)
			{
				win?.Focus();
				RandomWait.Wait(100, 600);
				win?.Close();
				RandomWait.Wait(100, 600);
				this._Client.MainWindow.Focus();
			}

			return result;
		}

		private bool _ProcessContent(UIA3Automation automation, string content, MomentsOptions options, Window window)
		{
			var publishRootRetry = Retry.WhileNull(() => window.FindFirstByXPath("/Group/Group/Group/Group/Group[@AutomationId='SnsPublishPanel']"), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
			if (publishRootRetry.Success)
			{
				ClipboardHelper.SetText(content);
				var pubishRoot = publishRootRetry.Result;
				var buttonRoot = pubishRoot.FindFirstByXPath("/Group/Group[2]");
				var contentRoot = pubishRoot.FindFirstByXPath("/Group/Group[1]/Group[@AutomationId='qt_scrollarea_viewport']");
				var edit = contentRoot.FindFirstDescendant(cf => cf.ByControlType(ControlType.Edit).And(cf.ByClassName("mmui::XValidatorTextEdit")));
				var point = edit.BoundingRectangle.SafeRandomPoint();
				SupperMouseKey.MoveTo(point);
				RandomWait.Wait(100, 300);
				SupperMouseKey.MoveTo(point.Confusion(5, 3));
				RandomWait.Wait(200, 900);
				SupperMouseKey.LeftClick();
				RandomWait.Wait(300, 1200);
				SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
				if (options != null)
				{
					__ProcessAnthoer(automation, options, window, contentRoot);
				}

				var sendButton = buttonRoot.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("发表")));
				point = sendButton.BoundingRectangle.SafeRandomPoint();
				SupperMouseKey.MoveTo(point);
				RandomWait.Wait(100, 300);
				SupperMouseKey.MoveTo(point.Confusion(3, 2));
				RandomWait.Wait(200, 900);
				SupperMouseKey.LeftClick();
				RandomWait.Wait(300, 1200);
				return true;
			}
			return false;
		}

		private void __ProcessAnthoer(UIA3Automation automation, MomentsOptions options, Window window, AutomationElement root)
		{
			if (options.AtUsrs != null)
			{
				//@好友处理
				__ProcessAtUser(automation, options, window, root);
			}
			if (options.Labels != null)
			{
				__ProcessLabel(automation, options, window, root);
			}
		}

		private void __ProcessAtUser(UIA3Automation automation, MomentsOptions options, Window window, AutomationElement root)
		{
			var atUserLink = root.FindFirstDescendant(cf => cf.ByName("提醒谁看").And(cf.ByClassName("mmui::PublishComponent").And(cf.ByControlType(ControlType.Group))));
			if (atUserLink == null)
				return;
			var point = atUserLink.BoundingRectangle.SafeRandomPoint();
			SupperMouseKey.MoveTo(point);
			RandomWait.Wait(100, 500);
			SupperMouseKey.MoveTo(point.Confusion(5, 2));
			RandomWait.Wait(100, 900);
			SupperMouseKey.LeftClick();
			//处理@好友
			var atList = options.AtUsrs.ToHashSet().ToList();
			var winRetry = Retry.WhileNull(() => window.FindFirstChild(cf => cf.ByName("微信提醒谁看").And(cf.ByControlType(ControlType.Window))), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
			if (winRetry.Success)
			{
				var popWin = winRetry.Result.AsWindow();
				var edit = popWin.FindFirstByXPath("/Group/Group/Group/Edit[@Name='搜索'][@ClassName='mmui::XValidatorTextEdit']");
				point = edit.BoundingRectangle.SafeRandomPoint();
				SupperMouseKey.MoveTo(point);
				RandomWait.Wait(100, 500);
				var path = "";
				foreach (var f in atList)
				{
					SupperMouseKey.MoveTo(point.Confusion(5, 2));
					RandomWait.Wait(100, 300);
					SupperMouseKey.MoveTo(point.Confusion(5, 2));
					RandomWait.Wait(100, 300);
					SupperMouseKey.LeftClick();
					RandomWait.Wait(100, 900);
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
					RandomWait.Wait(100, 900);
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
					ClipboardHelper.SetText(f);
					RandomWait.Wait(100, 900);
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
					RandomWait.Wait(100, 900);
					path = "/Group/Group/List[@Name='请勾选需要添加的联系人'][@AutomationId='sp_search_result_list']";
					var list = popWin.FindFirstByXPath(path);
					if (list != null)
					{
						var chkList = list.FindAllChildren(cf => cf.ByControlType(ControlType.CheckBox));
						var fItem = chkList.Where(item => item.Name.Trim().Equals(f.Trim())).FirstOrDefault();
						if (fItem != null)
						{
							var point2 = fItem.BoundingRectangle.SafeRandomPoint();
							SupperMouseKey.MoveTo(point2);
							RandomWait.Wait(100, 300);
							SupperMouseKey.MoveTo(point2.Confusion(5, 2));
							RandomWait.Wait(300, 1200);
							SupperMouseKey.LeftClick();
							RandomWait.Wait(300, 1500);
						}
					}
				}

				//检查结果集.
				path = "/Group/Group/Text/Group[@AutomationId='sp_choice_contact_list.qt_scrollarea_viewport']";
				var resultPaneRetry = Retry.WhileNull(() => popWin.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
				if (resultPaneRetry.Success)
				{
					var resultPane = resultPaneRetry.Result;
					var buttonRoot = resultPane.FindFirstChild(cf => cf.ByControlType(ControlType.Group));
					var buttonList = buttonRoot.FindAllChildren(cf => cf.ByControlType(ControlType.Button));
					if (buttonList.Length > 0)
					{
						path = "/Group/Group/Button[@Name='完成']";
						var finishButton = popWin.FindFirstByXPath(path);
						if (finishButton != null)
						{
							var point2 = finishButton.BoundingRectangle.SafeRandomPoint();
							SupperMouseKey.MoveTo(point2);
							RandomWait.Wait(100, 300);
							SupperMouseKey.MoveTo(point2.Confusion(5, 2));
							RandomWait.Wait(300, 1200);
							SupperMouseKey.LeftClick();
							return;
						}
					}
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
					RandomWait.Wait(300, 1500);
				}
				else
				{
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
					RandomWait.Wait(300, 1500);
				}
			}
		}

		private void __ProcessLabel(UIA3Automation automation, MomentsOptions options, Window window, AutomationElement root)
		{
			var labels = options.Labels;
			var selectNumber = 0;
			if (labels.Count == 0)
				return;
			var path = "/Group/Button[@ClassName='mmui::PublishPrivacyView']";
			var lableLinkRetry = Retry.WhileNull(() => root.FindFirstByXPath(path), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
			if (!lableLinkRetry.Success)
				return;
			var point = lableLinkRetry.Result.BoundingRectangle.SafeRandomPoint();
			SupperMouseKey.MoveTo(point);
			RandomWait.Wait(100, 500);
			SupperMouseKey.MoveTo(point.Confusion(5, 2));
			RandomWait.Wait(100, 900);
			SupperMouseKey.LeftClick();
			path = "/Window[@Name='Weixin']";
			var rootPopWinRetry = Retry.WhileNull(() => window.FindFirstByXPath("/Window[@Name='Weixin']"), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
			if (rootPopWinRetry.Success)
			{
				var rootPopWin = rootPopWinRetry.Result;
				path = "/Group/RadioButton[@Name='谁可以看']";
				var whoVisibleButton = rootPopWin.FindFirstByXPath(path);
				point = whoVisibleButton.BoundingRectangle.SafeRandomPoint();
				SupperMouseKey.MoveTo(point);
				RandomWait.Wait(100, 500);
				SupperMouseKey.MoveTo(point.Confusion(5, 3));
				RandomWait.Wait(100, 900);
				SupperMouseKey.LeftClick();
				//处理谁可以看.
				path = "/Window/Window[@Name='微信谁可以看']";
				var whoVisibleWinRetry = Retry.WhileNull(() => window.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
				if (whoVisibleWinRetry.Success)
				{
					var whoVisibleWin = whoVisibleWinRetry.Result;
					path = "/Group/Group/List[@Name='请勾选需要添加的联系人'][@AutomationId='sp_to_select_contact_list']";
					var list = whoVisibleWin.FindFirstByXPath(path);
					var chkBoxs = list.FindAllChildren(cf => cf.ByControlType(ControlType.CheckBox));
					foreach (var item in chkBoxs)
					{
						var s = item.Name.Trim().Split(' ');
						var label = s[0];
						if (labels.Contains(label))
						{
							labels.Remove(label);
							point = item.BoundingRectangle.SafeRandomPoint();
							SupperMouseKey.MoveTo(point);
							RandomWait.Wait(50, 300);
							SupperMouseKey.MoveTo(point.Confusion(10, 3));
							RandomWait.Wait(300, 900);
							SupperMouseKey.LeftClick();
							RandomWait.Wait(300, 1200);
							selectNumber++;
						}
					}
					if (labels.Count > 0)
					{
						foreach (var item in labels)
						{
							//搜索
							path = "/Group/Group/Group/Edit[@Name='搜索']";
							var edit = whoVisibleWin.FindFirstByXPath(path);
							point = edit.BoundingRectangle.SafeRandomPoint();
							SupperMouseKey.MoveTo(point);
							RandomWait.Wait(50, 300);
							SupperMouseKey.MoveTo(point.Confusion(10, 3));
							RandomWait.Wait(300, 900);
							SupperMouseKey.LeftClick();
							RandomWait.Wait(300, 1200);
							SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
							RandomWait.Wait(300, 900);
							SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
							RandomWait.Wait(300, 900);
							ClipboardHelper.SetText(item);
							SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
							RandomWait.Wait(600, 1500);
							path = "/Group/Group/List[@Name='请勾选需要添加的联系人'][@AutomationId='sp_to_select_contact_list']";
							list = whoVisibleWin.FindFirstByXPath(path);
							chkBoxs = list.FindAllChildren(cf => cf.ByControlType(ControlType.CheckBox));
							if (chkBoxs.Count() > 0)
							{
								foreach (var subItem in chkBoxs)
								{
									var s = subItem.Name.Trim().Split(' ');
									var label = s[0];
									if (label.Equals(item))
									{
										point = subItem.BoundingRectangle.SafeRandomPoint();
										SupperMouseKey.MoveTo(point);
										RandomWait.Wait(50, 300);
										SupperMouseKey.MoveTo(point.Confusion(10, 3));
										RandomWait.Wait(300, 900);
										SupperMouseKey.LeftClick();
										RandomWait.Wait(300, 1200);
										selectNumber++;
									}
								}
							}
						}
					}
					//关闭
					if (selectNumber > 0)
					{
						//点击完成
						path = "/Group/Group/Button[@Name='完成'][@AutomationId='confirm_btn']";
						var finishButton = whoVisibleWin.FindFirstByXPath(path);
						point = finishButton.BoundingRectangle.SafeRandomPoint();
						SupperMouseKey.MoveTo(point);
						RandomWait.Wait(50, 300);
						SupperMouseKey.MoveTo(point.Confusion(10, 3));
						RandomWait.Wait(300, 900);
						SupperMouseKey.LeftClick();
						RandomWait.Wait(300, 1200);

						//点击确定
						path = "/Window/Group/Button[@Name='确定']";
						var confirmButton = window.FindFirstByXPath(path);
						if (confirmButton != null)
						{
							point = confirmButton.BoundingRectangle.SafeRandomPoint();
							SupperMouseKey.MoveTo(point);
							RandomWait.Wait(50, 300);
							SupperMouseKey.MoveTo(point.Confusion(10, 3));
							RandomWait.Wait(300, 900);
							SupperMouseKey.LeftClick();
							RandomWait.Wait(300, 1200);
						}
					}
					else
					{
						whoVisibleWin.Focus();
						SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
						RandomWait.Wait(600, 1200);

						//关闭下一层窗口
						rootPopWin.Focus();
						SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
						RandomWait.Wait(600, 1200);

					}
				}
			}
		}

		private bool _ProcessImageFiles(string pathRoot, Window window, List<string> imageFiles)
		{
			var path = "/Window[@Name='选择文件']";
			var rootRetry = Retry.WhileNull(() => window.FindFirstByXPath(path), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
			if (rootRetry.Success)
			{
				var fileWin = rootRetry.Result.AsWindow();
				var editRetry = Retry.WhileNull(() => fileWin.FindFirstDescendant(cf => cf.ByName("文件名(N):").And(cf.ByControlType(ControlType.Edit))), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
				if (editRetry.Success)
				{
					var point = editRetry.Result.BoundingRectangle.SafeRandomPoint();
					SupperMouseKey.MoveTo(point);
					RandomWait.Wait(200, 600);
					SupperMouseKey.LeftClick();
					ClipboardHelper.SetText(pathRoot);
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
					RandomWait.Wait(200, 900);
					SupperMouseKey.Enter();
					RandomWait.Wait(600, 1200);
					point = point.Confusion(20, 3);
					SupperMouseKey.MoveTo(point);
					RandomWait.Wait(200, 600);
					SupperMouseKey.LeftClick();
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
					RandomWait.Wait(200, 900);
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
					RandomWait.Wait(200, 900);
					//组装字符串
					var fileNameList = imageFiles.Select(x => Path.GetFileName(x)).ToHashSet().ToList().Select(x => $"\"{x}\"").ToList();
					string fileStr = string.Join(" ", fileNameList);
					ClipboardHelper.SetText(fileStr);
					SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
					RandomWait.Wait(200, 900);
					//点击打开
					var openButton = fileWin.FindFirstByXPath("/Button[@Name='打开(O)']");
					if (openButton != null)
					{
						point = openButton.BoundingRectangle.SafeRandomPoint();
						SupperMouseKey.MoveTo(point);
						RandomWait.Wait(200, 600);
						SupperMouseKey.MoveTo(point.Confusion(5, 2));
						RandomWait.Wait(200, 600);
						SupperMouseKey.LeftClick();
						RandomWait.Wait(600, 1200);
						return true;
					}
				}

			}

			return false;
		}

		private (bool sucess, string path) CheckImagesValid(List<string> imageFiles)
		{
			if (imageFiles.Count == 0)
				return (false, "");
			//检查图片路径是否存在
			foreach (var file in imageFiles)
			{
				if (!File.Exists(file))
				{
					_logger.Error("错误：传入的imageFiles参数列表有图片文件在磁盘中不存在!");
					return (false, "");
				}
			}

			var dicsPath = imageFiles.Select(x => Path.GetDirectoryName(x)).ToHashSet();
			if (dicsPath.Count != 1)
			{
				_logger.Error("错误：传入的imageFiles参数列表中文件必须在一个目录中!");
				return (false, "");
			}

			var pathRoot = dicsPath.First();

			var supportSuffix = new string[] { ".png", ".jpg", ".jpeg", ".bmp" };
			var imgSuffix = imageFiles.Select(x => Path.GetExtension(x).ToLower()).ToList();
			var exceptList = imgSuffix.Except(supportSuffix).ToList();
			if (exceptList.Count() > 0)
			{
				_logger.Error($"错误：传入的imageFiles参数列表有图片格式不被支持，微信仅支持如下图片格式:{string.Join(",", supportSuffix)}");
				return (false, "");
			}

			return (true, pathRoot);
		}

		/// <summary>
		/// 移除自己发送的朋友圈
		/// </summary>
		/// <param name="content">朋友圈文字内容</param>
		/// <returns>是否成功删除</returns>
		public async Task<bool> RemoveMoments(string content)
		{
			return await WeChatInvoker.Call(RemoveMomentsCore, content);
		}

		internal bool RemoveMomentsCore(UIA3Automation automation, string content)
		{
			if (string.IsNullOrWhiteSpace(content))
			{
				_logger.Error(content);
				return false;
			}
			var mainWin = OpenMomentsCore(automation);
			//首先点击刷新按钮到顶部
			var toolBar = ToolBar;
			if (toolBar == null)
				return false;
			var refreshButton = toolBar.FindFirstChild(cf => cf.ByName("刷新").And(cf.ByControlType(ControlType.Button)));
			var point = refreshButton.BoundingRectangle.Center();
			SupperMouseKey.MoveTo(point.Confusion(4, 4));
			RandomWait.Wait(100, 300);
			SupperMouseKey.MoveTo(point.Confusion(4, 4));
			RandomWait.Wait(300, 900);
			SupperMouseKey.LeftClick();
			RandomWait.Wait(1000, 2500);
			var container = mainWin.FindFirstByXPath("/Group/Group/Group/Custom/Group/List[@Name='朋友圈'][@AutomationId='sns_list']");
			point = container.BoundingRectangle.SafeRandomPoint();
			SupperMouseKey.MoveTo(point);
			RandomWait.Wait(100, 300);
			SupperMouseKey.MoveTo(point.Confusion(10, 10));
			RandomWait.Wait(300, 900);
			var index = 0;
			var result = false;
			//滚动并且删除.
			while (index < WeAutomation.Config.MonentsScrollMaxStep)
			{
				var childItems = container.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem));
				var filterItems = childItems.Where(x => !x.ClassName.Equals("mmui::TimelineCell") && !x.ClassName.Equals("mmui::TimelineCommentCell") && !string.IsNullOrWhiteSpace(x.Name)).ToList();
				foreach (var item in filterItems)
				{
					if (item.Name.StartsWith(this._Client.NickName) && item.Name.Contains(content))
					{
						if (item.BoundingRectangle.Y + item.BoundingRectangle.Height <= container.BoundingRectangle.Y + container.BoundingRectangle.Height - 60)
						{
							//点击删除按钮.
							RandomWait.Wait(600, 1500);
							result = __ProcessDeleteItem(item, mainWin);
							if (result)
								break;
						}
					}
				}
				if (result)
					break;
				var currentPoint = point.Confusion(5, 5);
				SupperMouseKey.MoveTo(currentPoint);
				RandomWait.Wait(100, 300);
				MouseScrollHelper.DownStep(currentPoint, 1);
				index++;
			}

			mainWin.Focus();
			CloseMomentsCore(automation);
			return result;
		}

		private bool __ProcessDeleteItem(AutomationElement item, Window mainWin)
		{
			using var mat1 = this._Client.OcrEngee.GetMatFromElement(item);
			var roi = new Rectangle(0, mat1.Height - 25, mat1.Width - 80, 25);
			using var mat2 = new Mat(mat1, roi);
			//放大3倍
			using var mat3 = new Mat();
			CvInvoke.Resize(mat2, mat3, Size.Empty, 3, 3, Emgu.CV.CvEnum.Inter.Cubic);
			var result = this._Client.OcrEngee.Detect(mat3.ToBitmap(), 0, mat3.Width, boxScoreThresh: 0.8f, boxThresh: 0.85f, isTest: false, doAngle: false, mostAngle: false);
			_logger.Debug(result.ToString());
			var texts = result.TextBlocks.Where(u => !string.IsNullOrWhiteSpace(u.Text) && u.CharScores.Average() > 0.85f).ToList();
			if (texts.Count == 0)
			{
				_logger.Warn("删除朋友圈时未识别到操作文本，跳过当前动态。");
				return false;
			}
			var rightPos = texts.Max(u => u.BoxPoints[1].X);
			var text = texts.Where(u => u.BoxPoints[1].X == rightPos).FirstOrDefault();
			if (text == null)
				return false;
			var point = new Point(text.BoxPoints[1].X, text.BoxPoints[1].Y + (int)((text.BoxPoints[2].Y - text.BoxPoints[1].Y) / 2));
			point = new Point(point.X / 3, point.Y / 3);
			point = new Point(item.BoundingRectangle.X + point.X, item.BoundingRectangle.Y + item.BoundingRectangle.Height - 25 + point.Y);
			SupperMouseKey.MoveTo(point);
			RandomWait.Wait(800, 1500);
			bool success = TryClick(new Point(point.X + 5 + 23, point.Y), mainWin);
			return success || TryClick(new Point(point.X + 5, point.Y), mainWin);
		}

		private bool TryClick(Point point, Window mainWin)
		{
			var point2 = new Point(point.X + 12, point.Y);
			SupperMouseKey.MoveTo(point2);
			RandomWait.Wait(100, 300);
			SupperMouseKey.MoveTo(point2.Confusion(4, 2));
			RandomWait.Wait(300, 900);
			SupperMouseKey.LeftClick();
			RandomWait.Wait(300, 900);
			//等候删除按钮出来.
			var path = "/Window/Group/Text[@Name='删除该朋友圈？']";
			var deleWinRetry = Retry.WhileNull(() => mainWin.FindFirstByXPath(path), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
			if (deleWinRetry.Success)
			{
				path = "/Window/Group/Group/Group/Button[@Name='删除'][@ClassName='mmui::XOutlineButton']";
				var delButton = mainWin.FindFirstByXPath(path);
				if (delButton != null)
				{
					point2 = delButton.BoundingRectangle.SafeRandomPoint();
					SupperMouseKey.MoveTo(point2);
					RandomWait.Wait(100, 300);
					SupperMouseKey.MoveTo(point2.Confusion(4, 2));
					RandomWait.Wait(300, 900);
					SupperMouseKey.LeftClick();
					RandomWait.Wait(300, 900);
					return true;
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
	}
}
