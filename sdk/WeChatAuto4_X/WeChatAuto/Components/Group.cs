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
using WeAutoCommon.Models;
using System.Reflection.Metadata.Ecma335;
using Emgu.CV;
using System.Windows.Media.Imaging;

namespace WeChatAuto.Components
{
    /// <summary>
    /// 群聊管理
    /// </summary>
    public class Group
    {
        protected readonly WeChatClient _Client;
        protected readonly UIThreadInvoker uiThreadInvoker;
        protected readonly IServiceProvider serviceProvider;
        internal AutomationElement RootPane => _GetChatRootPane();   //root,包括搜索group与内容group.
        internal AutomationElement PaneRoot => _GetGoupPaneRoot();
        internal AutomationElement SearchEdit => _GetSearEdit();
        internal ListBoxItem[] ChatMemberList => _GetChatMemberList();
        internal Group(WeChatClient client, UIThreadInvoker uiThreadInvoker, IServiceProvider serviceProvider)
        {
            this._Client = client;
            this.uiThreadInvoker = uiThreadInvoker;
            this.serviceProvider = serviceProvider;
        }
        /// <summary>
        /// 关闭信息窗口
        /// </summary>
        internal void CloseChatInfoPane()
        {
            var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group[@ClassName='mmui::ChatRoomMemberInfoView']";
            var groupRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200)); ;
            if (groupRetry.Success)
            {
                //已经存在.
                var button = RootBotton;
                if (button != null)
                {
                    button.Click();
                    // 下面是稳定版本
                    // var point = button.GetClickablePoint();
                    // Mouse.Position = point.Confusion(5, 0);
                    // RandomWait.Wait(100, 300);
                    // SupperMouseKey.MoveTo(point.Confusion(5, 0));
                    // RandomWait.Wait(300, 900);
                    // SupperMouseKey.LeftClick();
                    // RandomWait.Wait(1000, 1500);
                    // groupRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
                }
            }
        }

        internal AutomationElement _GetChatRootPane()
        {
            var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group[@ClassName='mmui::ChatRoomMemberInfoView']";
            var groupRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200)); ;
            if (groupRetry.Success)
            {
                //已经存在.
                return groupRetry.Result;
            }
            else
            {
                //点击按钮
                var button = RootBotton;
                if (button != null)
                {
                    var point = button.GetClickablePoint();
                    Mouse.Position = point.Confusion(5, 3);
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(5, 3));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(1000, 1500);
                    groupRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
                    return groupRetry.Success ? groupRetry.Result : null;
                }
                return null;
            }
        }

        /// <summary>
        /// 点击聊天信息按钮
        /// 注意：
        /// 让保证 聊天信息 按钮是可点击状态
        /// </summary>
        internal void ClickChatInfoButton()
        {
            var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Button[@AutomationId='content_view.top_content_view.title_h_view.right_v_view.right_content_h_view.right_content_v_view.right_ui_.more_button'][@Name='聊天信息']";
            var buttonRetry = Retry.WhileNull(()=>_Client.MainWindow.FindFirstByXPath(path),TimeSpan.FromSeconds(2),TimeSpan.FromMilliseconds(200));
            if (buttonRetry.Success)
            {
                var button = buttonRetry.Result;
                button.Click();
            }
        }

        internal Button RootBotton
        {
            get
            {
                var path = $"/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Button[@Name='聊天信息'][@AutomationId='content_view.top_content_view.title_h_view.right_v_view.right_content_h_view.right_content_v_view.right_ui_.more_button'][@ClassName='mmui::XButton']";
                var index = 0;
                while (index <= 1)
                {
                    var buttonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));
                    if (buttonRetry.Success)
                    {
                        return buttonRetry.Result.AsButton();
                    }
                    else
                    {
                        this._Client.Navigation.SwitchNavigationCore(uiThreadInvoker.Automation, NavigationType.微信);
                        index++;
                    }
                }
                return null;
            }
        }

        private ListBoxItem[] _GetChatMemberList()
        {
            var paneRoot = PaneRoot;
            if (paneRoot == null)
                return null;
            return paneRoot.FindFirstDescendant(cf => cf.ByControlType(ControlType.List).And(cf.ByAutomationId("chat_member_list")).And(cf.ByClassName("QFReuseGridWidget")))?.AsListBox().Items;
        }

        private AutomationElement _GetGoupPaneRoot()
        {
            var rootButton = RootBotton;
            if (rootButton == null)
                return null;
            var index = 0;
            while (index <= 1)
            {
                //可能没有打开
                var paneRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstDescendant(cf => cf.ByControlType(ControlType.Group).And(cf.ByClassName("mmui::ChatRoomMemberInfoView"))), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));
                if (paneRetry.Success)
                {
                    return paneRetry.Result;
                }
                else
                {
                    index++;
                    rootButton.ClickEnhance(this._Client.MainWindow);
                }
            }

            return null;
        }

        private AutomationElement _GetSearEdit()
        {
            var paneRoot = PaneRoot;
            if (paneRoot == null)
                return null;
            return paneRoot.FindFirstDescendant(cf => cf.ByName("搜索").And(cf.ByClassName("mmui::XValidatorTextEdit")));
        }



        internal bool CheckGroup(UIA3Automation automation, string groupName)
        {
            var search = this._Client.Conversations.SearchWhoCore(automation, groupName);
            if (!search)
                return false;
            var headerInfo = this._Client.ChatContent.ChatHeader.GetTitleCore(automation);
            if (headerInfo == null)
                return false;
            if (!headerInfo.CanTalk())
                return false;
            if (headerInfo.HeaderType != ChatType.群聊)
                return false;
            if (headerInfo.Title != groupName)
                return false;
            return true;
        }


        /// <summary>
        /// 是否是自有群
        /// </summary>
        /// <param name="groupName">群聊名称</param>
        /// <returns>是否是自有群</returns>
        public async Task<bool> IsOwnerChatGroup(string groupName)
        {
            var name = await GetGroupOwner(groupName);
            return name == this._Client.NickName ? true : false;
        }

        /// <summary>
        /// 获取群主
        /// </summary>
        /// <param name="groupName">群聊名称</param>
        /// <returns>群主昵称</returns>
        public async Task<string> GetGroupOwner(string groupName)
        {
            return await WeChatInvoker.Call(GetGroupOwnerCore, groupName);
        }

        private string GetGroupOwnerCore(UIA3Automation automation, string groupName)
        {
            if (!CheckGroup(automation, groupName))
                return "";
            var list = _GetChatMemberList();
            if (list.Length > 0)
            {
                this._Client.ChatContent.Sender.FocuseSenderCore(automation);
                return list[0].Name.Trim();
            }
            return "";
        }


        /// <summary>
        /// 退出群聊
        /// </summary>
        /// <param name="groupName">群聊名称,可以为空,如果为空，则退出焦点聊天群</param>
        /// <param name="clearHistory">是否清除历史消</param>
        public async Task QuitChatGroup(string groupName, bool clearHistory = true)
        {
            if (!string.IsNullOrWhiteSpace(groupName))
            {
                var find = await _Client.Conversations.Search(groupName);
                if (!find)
                    return;
            }
            var headInfo = await this._Client.GetTitle();
            if (!headInfo.CanTalk() || headInfo.HeaderType != ChatType.群聊)
                return;

            await WeChatInvoker.Call(QuitChatGroupCore, clearHistory, headInfo.Title);
        }

        private void QuitChatGroupCore(UIA3Automation automation, bool clearHistory, string groupName)
        {
            var root = this._GetChatRootPane();
            RandomWait.Wait(300, 900);
            //先到底部
            var point = root.BoundingRectangle.Center().Confusion(10, 20);
            Mouse.Position = point;
            RandomWait.Wait(100, 300);
            SupperMouseKey.MoveTo(root.BoundingRectangle.Center().Confusion(10, 20));
            RandomWait.Wait(300, 900);
            var index = 0;
            while (index < 3)
            {
                MouseScrollHelper.DownStep(point, 5);
                SupperMouseKey.MoveTo(root.BoundingRectangle.Center().Confusion(10, 20));
                RandomWait.Wait(300, 900);
                index++;
            }
            //点击 退出群聊 按钮
            using var bitmap = root.Capture();
            using var mat = this._Client.OcrEngee.GetMatFromBitmap(bitmap);
            var roi = new Rectangle(0, (int)(mat.Height * 0.7), mat.Width, mat.Height - (int)(mat.Height * 0.7));
            using var mat2 = new Mat(mat, roi);
            using var destBitmap = mat2.ToBitmap();
            var ocrResult = this._Client.OcrEngee.Detect(destBitmap, 0, mat2.Height, 0.5f, 0.3f, 1.6f, false, false, false);
            var region = ocrResult.TextBlocks.Where(u => u.Text.Trim().Equals("退出群聊")).FirstOrDefault();
            if (region != null)
            {
                point = new Point(region.BoxPoints[0].X + (int)((region.BoxPoints[2].X - region.BoxPoints[0].X) / 2),
                                  region.BoxPoints[0].Y + (int)((region.BoxPoints[2].Y - region.BoxPoints[0].Y) / 2));
                point.X = root.BoundingRectangle.X + point.X;
                point.Y = root.BoundingRectangle.Y + (int)(root.BoundingRectangle.Height * 0.7) + point.Y;
                Mouse.Position = point;
                RandomWait.Wait(100, 300);
                SupperMouseKey.MoveTo(point.Confusion(10, 3));
                RandomWait.Wait(300, 900);
                SupperMouseKey.LeftClick();
                RandomWait.Wait(300, 900);

                //点击退出按钮
                var path = "/Window[@Name='Weixin'][@ClassName='mmui::XDialog']/Group/Group/Group/Button[@Name='确定']";
                var confirmRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
                if (confirmRetry.Success)
                {
                    if (clearHistory)
                    {
                        var parent = confirmRetry.Result.GetParent().GetParent().GetParent();
                        var clkCheck = parent.FindFirstChild(cf => cf.ByControlType(ControlType.CheckBox));
                        clkCheck.Click();
                        RandomWait.Wait(300, 900);
                    }
                    var confirmButton = confirmRetry.Result;
                    point = confirmButton.BoundingRectangle.Center();
                    Mouse.Position = point;
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(10, 2));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(1500, 3000);
                    //会话窗口乱点一下.
                    var cList = this._Client.Conversations.GetVisibleConversationElements(automation);
                    var cObjList = this._Client.Conversations.GetVisibleConversationsCore(automation);
                    if (cObjList.FirstOrDefault(x => x.ConversationTitle.Equals(groupName)) != null)
                    {
                        return;
                    }
                    var cRoot = this._Client.Conversations.ConversationRoot;
                    foreach (var c in cList)
                    {
                        if (c.BoundingRectangle.IsClickSafe(cRoot.BoundingRectangle))
                        {
                            var info = this._Client.Conversations.GetConversationItemFromName(c.Name);
                            if (info.NotReadNumbr == 0 || info.IsDoNotDisturb)
                            {
                                c.Click();
                                RandomWait.Wait(300, 900);
                                break;
                            }
                        }
                    }
                }
            }
        }

        /// <summary>
        /// 获取群聊成员列表
        /// </summary>
        /// <param name="groupName">群聊名称,可以为空，如果为空，则获取的是焦点聊天群聊的成员列表</param>
        /// <returns>群聊成员列表</returns>
        public async Task<List<string>> GetChatGroupMemberList(string groupName)
        {
            if (!string.IsNullOrWhiteSpace(groupName))
            {
                var find = await _Client.Conversations.Search(groupName);
                if (!find)
                    return new List<string>(); ;
            }
            var headInfo = await this._Client.GetTitle();
            if (!headInfo.CanTalk() || headInfo.HeaderType != ChatType.群聊)
                return new List<string>();
            return await WeChatInvoker.Call(GetChatGroupMemberListCore);
        }

        internal List<string> GetChatGroupMemberListCore(UIA3Automation automation)
        {
            var resultList = new List<string>();
            var invokeButton = this._Client.ChatContent.MessageBubbleList.HistoryButton;
            if (invokeButton == null)
                return resultList;
            HeaderInfo title = this._Client.ChatContent.ChatHeader.GetTitleCore(automation);
            if (!title.CanTalk())
                return resultList;
            invokeButton.Click();
            RandomWait.Wait(600, 1200);
            var result = __ClickChatHistoryButton(automation, invokeButton, title.Title);  //打开消息历史窗口
            if (!result.Success) return resultList;
            result = __ClickGroupMemberButton(automation, result.Value);
            if (!result.Success) return resultList;
            _FetchMember(automation, result.Value, resultList);

            return resultList;
        }

        private void _FetchMember(UIA3Automation automation, Window subWin, List<string> resultList)
        {
            var desktop = automation.GetDesktop();
            var path = $"/Window[@Name='Weixin'][@ClassName='mmui::XPopover'][@ProcessId={this._Client.MainWindow.Properties.ProcessId}]/Group/Group/List[@AutomationId='chatroom_member_list'][@ClassName='mmui::StickyHeaderRecyclerListView']";
            var listBoxRetry = Retry.WhileNull(() => desktop.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (listBoxRetry.Success)
            {
                var listBox = listBoxRetry.Result.AsListBox();
                var index = 0;
                var oldSnapshot = new List<string>();
                var point = listBox.BoundingRectangle.Center();
                while (index < 4)
                {
                    var listItems = listBox.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem));
                    var newSnapshot = listItems.Select(u => u.Name + "|" + u.Properties.RuntimeId.ToUniqueString()).ToList();
                    var exceptList = newSnapshot.Except(oldSnapshot).ToList();
                    if (exceptList.Count() > 0)
                    {
                        index = 0;
                        oldSnapshot = newSnapshot;
                        var oriList = listItems.Where(u => exceptList.Contains(u.Name + "|" + u.Properties.RuntimeId.ToUniqueString())).ToList();
                        var addList = oriList.Where(u => !u.Name.Equals("")).ToList();
                        resultList.AddRange(addList.Select(u => u.Name));
                    }
                    MouseScrollHelper.DownStep(point.Confusion(10, 10), 3);
                    index++;
                }
            }
            subWin?.Close();
        }

        private Result<Window> __ClickGroupMemberButton(UIA3Automation automation, Window subWin)
        {
            var path = "/Group/Group/Group/Group/Group/Group/Tab/TabItem[@AutomationId='qt_scrollarea_viewport.button_container.record_type_member'][@Name='群成员']";
            var tabItemRetry = Retry.WhileNull(() => subWin.FindFirstByXPath(path), timeout: TimeSpan.FromSeconds(1), interval: TimeSpan.FromMilliseconds(200));
            if (tabItemRetry.Success)
            {
                var tabItem = tabItemRetry.Result;
                RandomWait.Wait(600, 1500);
                tabItem.Click();
                RandomWait.Wait(600, 1500);
                return Result<Window>.Ok(subWin);
            }
            return Result<Window>.Fail("错误：点击 群成员 失败！");
        }

        private Result<Window> __ClickChatHistoryButton(UIA3Automation automation, Button invokeButton, string title)
        {
            var desktop = automation.GetDesktop();
            var winResult = Retry.WhileNull(() => desktop.FindAllChildren(cf => cf.ByClassName("mmui::SearchMsgUniqueChatWindow").And(cf.ByControlType(ControlType.Window).And(cf.ByProcessId(_Client.MainWindow.Properties.ProcessId)))), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
            if (winResult.Success)
            {
                var subWins = winResult.Result;
                var subWin = subWins.FirstOrDefault(u =>
                {
                    var name = u.Name.Replace("“", "").Replace("”", "");
                    if (name.Contains($"{title}"))
                    {
                        return true;
                    }
                    else
                    {
                        return false;
                    }
                }).AsWindow();
                if (subWin == null)
                    return Result<Window>.Fail("错误：未能打开聊天记录窗口");
                subWin.Focus();
                int targetX = _Client.MainWindow.BoundingRectangle.X + (int)((_Client.MainWindow.BoundingRectangle.Width - subWin.BoundingRectangle.Width) / 2);
                int targetY = _Client.MainWindow.BoundingRectangle.Y + (int)((_Client.MainWindow.BoundingRectangle.Height - subWin.BoundingRectangle.Height) / 2);
                subWin.Move(targetX, targetY);  //移动子窗口至主窗口中间
                RandomWait.Wait(100, 600);
                subWin.DrawHighlightExt();
                return Result<Window>.Ok(subWin);
            }
            return Result<Window>.Fail("错误：未能打开聊天记录窗口");
        }

        /// <summary>
        /// 修改自己在群中的昵称
        /// </summary>
        /// <param name="groupName">群名,可以为空，如果为空，则修改焦点群聊的自己在群中的昵称</param>
        /// <param name="nickName">昵称，如果为空，则删除自己在本群中的昵称</param>
        /// <returns>微信响应结果<see cref="Result"/></returns>
        public async Task<Result> ChangeChatGroupNickName(string groupName, string nickName)
        {
            if (!string.IsNullOrWhiteSpace(groupName))
            {
                var find = await _Client.Conversations.Search(groupName);
                if (!find)
                    return Result.Fail($"错误：没有发现groupName={groupName}的群");
            }
            var headInfo = await this._Client.GetTitle();
            if (!headInfo.CanTalk() || headInfo.HeaderType != ChatType.群聊)
                return Result.Fail("错误：此窗口为非聊天窗口");
            return await WeChatInvoker.Call(ChangeChatGroupNickNameCore, nickName);
        }

        private Result ChangeChatGroupNickNameCore(UIA3Automation automation, string nickName)
        {
            var rootPane = this._GetChatRootPane();
            var pane = rootPane.FindFirstByXPath("/Group[2]");
            if (pane == null)
                return Result.Fail("没有找到聊天信息的根Pane");
            using var bitmap = pane.Capture();
            using var mat = this._Client.OcrEngee.GetMatFromBitmap(bitmap);
            //扩大两倍好识别
            using var mat2 = new Mat();
            CvInvoke.Resize(mat, mat2, Size.Empty, 2, 2, Emgu.CV.CvEnum.Inter.Cubic);
            using var srcImg = mat2.ToBitmap();
            var ocrResult = this._Client.OcrEngee.Detect(srcImg, 0, mat2.Width > mat2.Height ? mat2.Width : mat2.Height, 0.5f, 0.3f, 1.5f, false, false, false);
            var item = ocrResult.TextBlocks.Where(x => x.Text.Trim().Equals("我在本群的昵称")).FirstOrDefault();
            if (item == null)
                return Result.Fail("OCR识别 我在本群的昵称 失败");
            var srcPoint = new Point((int)(item.BoxPoints[0].X / 2 + (item.BoxPoints[2].X - item.BoxPoints[0].X) / 4), item.BoxPoints[0].Y / 2 + (int)((item.BoxPoints[2].Y - item.BoxPoints[0].Y) / 4));
            var point = new Point(pane.BoundingRectangle.X + srcPoint.X, pane.BoundingRectangle.Y + srcPoint.Y);
            var baseStep = 25;
            var ratio = DpiHelper.GetScaleForWindow(this._Client.MainWindow.Properties.NativeWindowHandle);
            var destPoint = new Point(point.X + 90, point.Y + (int)(baseStep * ratio));
            Mouse.Position = destPoint;
            RandomWait.Wait(100, 300);
            SupperMouseKey.MoveTo(destPoint.Confusion(10, 0));
            RandomWait.Wait(300, 900);
            SupperMouseKey.LeftClick();
            RandomWait.Wait(300, 1200);
            SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
            RandomWait.Wait(100, 300);
            SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
            ClipboardHelper.SetText(nickName);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.Enter();
            RandomWait.Wait(300, 1200);
            var path = "/Window[@Name='Weixin'][@ClassName='mmui::XDialog']/Group/Text[@Name='修改我在本群的昵称？']";
            var confirmRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (confirmRetry.Success)
            {
                var confirmGroup = confirmRetry.Result.GetParent();
                var button = confirmGroup.FindFirstByXPath("/Group/Group/Button[@Name='修改']");
                if (button != null)
                {
                    button.Click();
                    this.CloseChatInfoPane();
                    RandomWait.Wait(900, 1500);
                    return Result.Ok();
                }
            }

            RandomWait.Wait(800, 1500);
            return Result.Fail("错误：修改群昵称失败!");
        }

        /// <summary>
        /// 改变群备注,群备注仅自己可见.
        /// </summary>
        /// <param name="groupName">群聊名称,可以为空，如果为空，则改变焦点聊天群的备注</param>
        /// <param name="newMemo">新备注</param>
        /// <returns>微信响应结果<see cref="Result"/></returns>
        public async Task<Result> ChangeChatGroupMemo(string groupName, string newMemo)
        {
            if (!string.IsNullOrWhiteSpace(groupName))
            {
                var find = await _Client.Conversations.Search(groupName);
                if (!find)
                    return Result.Fail($"错误：没有发现groupName={groupName}的群");
            }
            var headInfo = await this._Client.GetTitle();
            if (!headInfo.CanTalk() || headInfo.HeaderType != ChatType.群聊)
                return Result.Fail("错误：此窗口为非聊天窗口");
            return await WeChatInvoker.Call(ChangeOwnerChatGroupMemoCore, newMemo);
        }


        private Result ChangeOwnerChatGroupMemoCore(UIA3Automation automation, string newMemo)
        {
            var rootPane = this._GetChatRootPane();
            var pane = rootPane.FindFirstByXPath("/Group[2]");
            if (pane == null)
                return Result.Fail("没有找到聊天信息的根Pane");
            using var bitmap = pane.Capture();
            using var mat = this._Client.OcrEngee.GetMatFromBitmap(bitmap);
            //扩大两倍好识别
            using var mat2 = new Mat();
            CvInvoke.Resize(mat, mat2, Size.Empty, 2, 2, Emgu.CV.CvEnum.Inter.Cubic);
            using var srcImg = mat2.ToBitmap();
            var ocrResult = this._Client.OcrEngee.Detect(srcImg, 0, mat2.Width > mat2.Height ? mat2.Width : mat2.Height, 0.5f, 0.3f, 1.5f, false, false, false);
            var item = ocrResult.TextBlocks.Where(x => x.Text.Trim().Equals("备注")).FirstOrDefault();
            if (item == null)
                return Result.Fail("OCR识别 备注 失败");
            var srcPoint = new Point((int)(item.BoxPoints[0].X / 2 + (item.BoxPoints[2].X - item.BoxPoints[0].X) / 4), item.BoxPoints[0].Y / 2 + (int)((item.BoxPoints[2].Y - item.BoxPoints[0].Y) / 4));
            var point = new Point(pane.BoundingRectangle.X + srcPoint.X, pane.BoundingRectangle.Y + srcPoint.Y);
            var baseStep = 25;
            var ratio = DpiHelper.GetScaleForWindow(this._Client.MainWindow.Properties.NativeWindowHandle);
            var destPoint = new Point(point.X + 90, point.Y + (int)(baseStep * ratio));
            Mouse.Position = destPoint;
            RandomWait.Wait(100, 300);
            SupperMouseKey.MoveTo(destPoint.Confusion(10, 0));
            RandomWait.Wait(300, 900);
            SupperMouseKey.LeftClick();
            RandomWait.Wait(300, 1200);
            SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
            RandomWait.Wait(100, 300);
            SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
            ClipboardHelper.SetText(newMemo);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.Enter();
            RandomWait.Wait(300, 1200);
            this.CloseChatInfoPane();

            RandomWait.Wait(800, 1500);

            return Result.Ok();
        }
    }
}