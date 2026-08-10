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
using Emgu.CV;
using RapidOCRLib.Models;
using System.IO;
using MessagePack;
using System.Reflection.PortableExecutable;
using System.Windows.Controls;
using System.Windows.Documents;

namespace WeChatAuto.Components
{
    /// <summary>
    /// 自有群管理
    /// </summary>
    public class OwnerGroup : Group
    {
        private readonly AutoLogger<OwnerGroup> _Logger;

        internal OwnerGroup(WeChatClient client, UIThreadInvoker uiThreadInvoker, IServiceProvider serviceProvider) :
            base(client, uiThreadInvoker, serviceProvider)
        {
            _Logger = serviceProvider.GetRequiredService<AutoLogger<OwnerGroup>>();
        }

        /// <summary>
        /// 修改群名，适用于自有群群名修改
        /// </summary>
        /// <param name="oldGroupName">旧群名称</param>
        /// <param name="newGroupName">新群名称</param>
        /// <returns>微信响应结果</returns>
        public async Task<Result> ChangeOwnerChatGroupName(string oldGroupName, string newGroupName)
        {
            var find = await _Client.Conversations.Search(oldGroupName);
            if (!find)
                return Result.Fail($"错误：没有发现oldGroupName={oldGroupName}的群");
            return await WeChatInvoker.Call(ChangeOwnerChatGroupNameCore, newGroupName);
        }

        private Result ChangeOwnerChatGroupNameCore(UIA3Automation automation, string newGroupName)
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
            var item = ocrResult.TextBlocks.Where(x => x.Text.Trim().Equals("群聊名称")).FirstOrDefault();
            if (item == null)
                return Result.Fail("OCR识别 群聊名称 失败");
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
            ClipboardHelper.SetText(newGroupName);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.Enter();

            RandomWait.Wait(1000, 3000);
            var path = "/Window[@Name='Weixin'][@ClassName='mmui::XDialog']/Group/Text[@Name='修改群聊名称？']";
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

            return Result.Fail("错误：修改群名失败！");
        }

        /// <summary>
        /// 更新群聊公告,仅适用于自有群
        /// </summary>
        /// <param name="groupName">群聊名称，可以为空字符串，如果为空，则更新焦点聊天群聊窗口的公告</param>
        /// <param name="groupNotice">群聊公告</param>
        /// <returns>微信操作响应结果<see cref="ChatResponse"/></returns>
        public async Task<Result> UpdateGroupNotice(string groupName, string groupNotice)
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

            return await WeChatInvoker.Call(UpdateGroupNoticeCore, groupNotice);
        }

        private Result UpdateGroupNoticeCore(UIA3Automation automation, string groupNotice)
        {
            if (string.IsNullOrWhiteSpace(groupNotice))
                return Result.Fail("groupNotice参数不能为空！");
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
            var item = ocrResult.TextBlocks.Where(x => x.Text.Trim().Equals("群公告")).FirstOrDefault();
            if (item == null)
                return Result.Fail("OCR识别 群公告 失败");
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
            //弹出修改群公告窗口
            var chatInfo = this._Client.ChatContent.ChatHeader.GetTitleCore(automation);
            var title = $"“{chatInfo.Title}”的群公告";
            var desktop = automation.GetDesktop();
            var winRetry = Retry.WhileNull(() => desktop.FindFirstChild(cf => cf.ByName(title).And(cf.ByControlType(ControlType.Pane))), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (winRetry.Success)
            {
                var win = winRetry.Result;
                var document = win.FindFirstByXPath("/Document[@ClassName='Chrome_RenderWidgetHostHWND']");
                var baseWidth = 71;
                var baseY = 30;
                point = new Point(document.BoundingRectangle.X + document.BoundingRectangle.Width - (int)(baseWidth * ratio), document.BoundingRectangle.Y + (int)(baseY * ratio));
                Mouse.Position = point;
                RandomWait.Wait(100, 300);
                SupperMouseKey.MoveTo(point.Confusion(10, 2));
                RandomWait.Wait(300, 900);
                SupperMouseKey.LeftClick();
                RandomWait.Wait(300, 1200);
                point = document.BoundingRectangle.Center();
                Mouse.Position = point.Confusion(10, 5);
                RandomWait.Wait(100, 300);
                SupperMouseKey.MoveTo(point.Confusion(10, 5));
                RandomWait.Wait(300, 900);
                SupperMouseKey.LeftClick();
                RandomWait.Wait(300, 1200);
                SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
                RandomWait.Wait(300, 900);
                SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
                RandomWait.Wait(300, 900);
                ClipboardHelper.SetText(groupNotice);
                RandomWait.Wait(300, 900);
                SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
                //点击完成
                RandomWait.Wait(600, 1500);
                baseWidth = 44;
                baseY = 26;
                point = new Point(document.BoundingRectangle.X + document.BoundingRectangle.Width - (int)(baseWidth * ratio), document.BoundingRectangle.Y + (int)(baseY * ratio));
                Mouse.Position = point;
                RandomWait.Wait(100, 300);
                SupperMouseKey.MoveTo(point.Confusion(5, 0));
                RandomWait.Wait(300, 900);
                SupperMouseKey.LeftClick();
                RandomWait.Wait(300, 1200);
                //confirm
                var path = "/Document/Custom/Button[@Name='发布']";
                var confirmRetry = Retry.WhileNull(() => win.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
                if (confirmRetry.Success)
                {
                    var confirm = confirmRetry.Result;
                    confirm.Click();
                    RandomWait.Wait(300, 1200);
                    this.CloseChatInfoPane();
                    return Result.Ok();
                }
            }

            this.CloseChatInfoPane();
            return Result.Fail("错误：修改群公告失败");
        }

        /// <summary>
        /// 创建群聊
        /// 如果存在，则打开群聊，否则创建一个新群聊
        /// </summary>
        /// <param name="groupName">群聊名称,不能与历史的群聊名称重复</param>
        /// <param name="firstWho">首个成员名称，必须是好友，不能是群聊名称，用来创建群聊定位,可以为空，如果为空，则以当前聊天的好友为基准创建群聊</param>
        /// <param name="memberName">成员名称,成员数量要大于0</param>
        /// <returns>是否创建成功,如果创建失败，则显示原因,具体请参考<see cref="Result"/></returns>
        public async Task<Result> CreateOwnerChatGroup(string groupName, string firstWho, string[] memberName)
        {
            return await WeChatInvoker.Call(CreateOwnerChatGroupCore, groupName, firstWho, memberName);
        }

        private Result CreateOwnerChatGroupCore(UIA3Automation automation, string groupName, string firstWho, string[] memberName)
        {
            if (memberName == null || memberName.Count() < 1)
                return Result.Fail("memberName参数不能为空并且count()要大于0");
            (bool flowControl, Result value) = _ValidTitle(automation, firstWho);
            if (!flowControl) return value;
            RandomWait.Wait(300, 1000);
            Result result = __ClickAddGroupButton(automation, firstWho);
            if (!result.Success) return result;
            result = _FindMemberAndClick(memberName);
            if (!result.Success) return result;
            result = _ClickFinishButton(automation);
            if (!result.Success) return result;
            //修改名称
            this.CloseChatInfoPane();
            result = ChangeOwnerChatGroupNameCore(automation, groupName);

            return result;
        }

        private Result _ClickFinishButton(UIA3Automation automation)
        {
            var path = "/Window[@Name='微信发起群聊']/Group/Group/Button[@AutomationId='confirm_btn'][@Name='完成']";
            var finishButtonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (finishButtonRetry.Success)
            {
                var finishButton = finishButtonRetry.Result.AsButton();
                if (finishButton.IsEnabled)
                {
                    var point = finishButton.BoundingRectangle.SafeRandomPoint();
                    Mouse.Position = point;
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(10, 5));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(1500, 5000);
                    return Result.Ok();
                }
                else
                {
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
                    RandomWait.Wait(900, 1500);
                    return Result.Fail("错误：按钮名 完成 不能点击！");
                }
            }

            return Result.Fail("点击 完成 按钮出错！");
        }

        private (bool flowControl, Result value) _ValidTitle(UIA3Automation automation, string firstWho)
        {
            if (!string.IsNullOrWhiteSpace(firstWho))
            {
                _Client.Conversations.SearchWhoCore(automation, firstWho);
            }
            var chatInfo = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
            if (!chatInfo.CanTalk())
            {
                return (flowControl: false, value: Result.Fail($"你想用 {firstWho} 为基准建立群聊，但是当前好友不属于能创建群聊的状态"));
            }
            if (chatInfo.HeaderType != ChatType.好友 && chatInfo.HeaderType != ChatType.企业微信)
            {
                return (flowControl: false, value: Result.Fail($"你想用 {firstWho} 建立群聊，但是当前好友不属于能创建群聊的状态，只有普通好友、企业微信才能建群聊，不能使用群聊创建群聊")); ;
            }

            return (flowControl: true, value: null);
        }

        private Result _FindMemberAndClick(string[] memberName)
        {
            var editRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath("/Window[@Name='微信发起群聊']/Group/Group/Group/Edit[@Name='搜索'][@ClassName='mmui::XValidatorTextEdit']"), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (editRetry.Success)
            {
                var edit = editRetry.Result.AsTextBox();
                foreach (var who in memberName)
                {
                    //点击清空按钮
                    var parent = edit.GetParent();
                    var clearButotn = parent.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("清空")));
                    if (clearButotn != null)
                    {
                        clearButotn.Click();
                        RandomWait.Wait(800, 2000);
                    }
                    edit.Text = who.Trim();
                    RandomWait.Wait(1000, 3000);
                    //加好友
                    var path = "/Window[@Name='微信发起群聊']/Group/Group/List[@Name='请勾选需要添加的联系人'][@AutomationId='sp_search_result_list']";
                    var resultPaneRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
                    if (resultPaneRetry.Success)
                    {
                        var list = resultPaneRetry.Result.AsListBox();
                        var items = list.FindAllChildren(cf => cf.ByControlType(ControlType.CheckBox));
                        var item = items.FirstOrDefault(u => u.Name.Trim().Equals(who.Trim()));
                        if (item != null)
                        {
                            var pattern = item.Patterns.Toggle;
                            if (pattern.Pattern.ToggleState == ToggleState.Off)
                            {
                                var point = item.BoundingRectangle.SafeRandomPoint();
                                Mouse.Position = point;
                                RandomWait.Wait(100, 300);
                                SupperMouseKey.MoveTo(point.Confusion(10, 5));
                                RandomWait.Wait(300, 900);
                                SupperMouseKey.LeftClick();
                            }
                        }
                    }

                    RandomWait.Wait(1000, 2500);
                }
                return Result.Ok();

            }
            return Result.Fail("加好友入群时发生错误！");
        }

        private Result __ClickAddGroupButton(UIA3Automation automation, string firstWho)
        {
            var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Button[@Name='聊天信息'][@AutomationId='content_view.top_content_view.title_h_view.right_v_view.right_content_h_view.right_content_v_view.right_ui_.more_button']";
            var padButtonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (padButtonRetry.Success)
            {
                var padButton = padButtonRetry.Result;
                padButton.Click();  //打开侧边栏
                RandomWait.Wait(600, 1500);
                var ratio = DpiHelper.GetScaleForWindow(this._Client.MainWindow.Properties.NativeWindowHandle);
                var baseX = (int)(40 * ratio);
                var baseY = (int)(32 * ratio);
                var step = (int)(53 * ratio);
                path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group[@AutomationId='single_chat_info_view']";
                var groupRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
                if (groupRetry.Success)
                {
                    var groupPanel = groupRetry.Result;
                    var point = new Point(groupPanel.BoundingRectangle.X + baseX, groupPanel.BoundingRectangle.Y + baseY);
                    Mouse.Position = point.Confusion(5, 5);
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(5, 5));
                    RandomWait.Wait(300, 900);
                    var destPoint = new Point(point.X + step, point.Y);
                    SupperMouseKey.MoveTo(destPoint.Confusion(5, 5));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(800, 1500);
                    return Result.Ok();
                }
                else
                {
                    return Result.Fail("错误：没有发现 右边侧 Panel");
                }
            }
            return Result.Fail("错误：没有发现 聊天信息 按钮，请检查原因！");
        }

        private Result __PoupupQuckMenuAndClick(UIA3Automation automation, AutomationElement button)
        {
            var point = button.BoundingRectangle.Center();
            Mouse.Position = point.Confusion(5, 5);
            RandomWait.Wait(100, 300);
            SupperMouseKey.MoveTo(point.Confusion(5, 5));
            RandomWait.Wait(300, 900);
            SupperMouseKey.LeftClick();
            RandomWait.Wait(600, 1500);
            var buttonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath("/Window/Group/List[@Name='快捷操作']/ListItem[@Name='发起群聊'][@ClassName='mmui::ChatMoreCellView']"), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (buttonRetry.Success)
            {
                var addButton = buttonRetry.Result;
                point = addButton.GetClickablePoint().Confusion(10, 5);
                Mouse.Position = point;
                RandomWait.Wait(100, 300);
                SupperMouseKey.MoveTo(point.Confusion(10, 5));
                RandomWait.Wait(300, 900);
                SupperMouseKey.LeftClick();
                RandomWait.Wait(600, 1500);
                return Result.Ok();
            }
            return Result.Fail("点击发起群聊按钮失败！");
        }


        /// <summary>
        /// 添加群聊成员，适用于自有群
        /// </summary>
        /// <param name="groupName">群聊名称,可以为空，则在焦点聊天群聊中添加群聊成员</param>
        /// <param name="memberName">成员名称</param>
        /// <returns>微信响应结果<see cref="ChatResponse"/></returns>
        public async Task AddOwnerChatGroupMember(string groupName, OneOf<string, string[]> memberName)
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
            await WeChatInvoker.Call(AddOwnerChatGroupMemberCore, headInfo.Title, memberName);
        }


        private void AddOwnerChatGroupMemberCore(UIA3Automation automation, string groupName, OneOf<string, string[]> memberName)
        {
            if (!CheckGroup(automation, groupName))
                return;
            var paneRoot = PaneRoot;
            var point = this._Client.OcrEngee.OCRVerticalDetect(paneRoot, 0.5f, "添加");
            if (point.IsEmpty)
                return;
            this._Client.MainWindow.Focus();
            Mouse.Position = paneRoot.BoundingRectangle.Center();
            RandomWait.Wait(600, 1200);
            var point2 = (new Point(point.X, point.Y - 30)).Confusion(10, 5);
            SupperMouseKey.MoveTo(point2);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.LeftClick();
            //处理拉人事宜
            ProcessInviteMembers(memberName, automation);
        }

        internal void ProcessInviteMembers(OneOf<string, string[]> memberName, UIA3Automation automation)
        {
            var memberList = memberName.IsT0 ? new List<string> { memberName.AsT0.Trim() } : memberName.AsT1.ToList().Select(x => x.Trim()).ToList();
            if (memberList.Count() == 0)
                return;
            var editPath = "/Window[@Name='微信添加群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/Group/Edit[@Name='搜索'][@ClassName='mmui::XValidatorTextEdit']";
            var searchEditRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(editPath), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            var path = "";
            if (searchEditRetry.Success)
            {
                var editParent = searchEditRetry.Result.GetParent();
                foreach (var m in memberList)
                {
                    //清空
                    var clearButton = editParent.FindFirstChild(cf => cf.ByName("清空")).AsButton();
                    if (clearButton != null)
                    {
                        clearButton.Click();
                        RandomWait.Wait(600, 1500);
                    }
                    var searchEdit = this._Client.MainWindow.FindFirstByXPath(editPath).AsTextBox();
                    searchEdit.Text = m;
                    RandomWait.Wait(800, 2500);
                    path = "/Window[@Name='微信添加群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/List[@Name='请勾选需要添加的联系人'][@AutomationId='sp_search_result_list']";
                    var itemRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
                    if (itemRetry.Success)
                    {
                        var items = itemRetry.Result.FindAllChildren(cf => cf.ByControlType(ControlType.CheckBox)).Select(u => u.AsCheckBox()).ToList();
                        foreach (var item in items)
                        {
                            if (item.Name.Equals(m))
                            {
                                //勾选
                                var point = item.BoundingRectangle.Center();
                                Mouse.Position = point.Confusion(10, 4);
                                RandomWait.Wait(100, 300);
                                SupperMouseKey.MoveTo(point.Confusion(10, 4));
                                RandomWait.Wait(300, 900);
                                SupperMouseKey.LeftClick();
                                break;
                            }
                        }

                    }
                    //停顿，准备下一个勾选
                    RandomWait.Wait(1200, 3000);
                }
                //确认是点击确定还是取消
                path = "/Window[@Name='微信添加群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/Button[@Name='添加'][@AutomationId='confirm_btn']";
                var addRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
                if (addRetry.Success)
                {
                    var addButton = addRetry.Result.AsButton();
                    if (addButton.IsEnabled)
                    {
                        var point = addButton.BoundingRectangle.Center();
                        Mouse.Position = point.Confusion(10, 4);
                        RandomWait.Wait(100, 300);
                        SupperMouseKey.MoveTo(point.Confusion(10, 4));
                        RandomWait.Wait(300, 900);
                        SupperMouseKey.LeftClick();
                        RandomWait.Wait(600, 2000);
                        //如果群人数比较多，会存在confirm的情况
                        path = "/Window/Group/Group/Group/Button[@Name='邀请'][@ClassName='mmui::XOutlineButton']";
                        var buttonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(3), TimeSpan.FromMilliseconds(200));
                        if (buttonRetry.Success)
                        {
                            var qryButton = buttonRetry.Result;
                            point = qryButton.BoundingRectangle.SafeRandomPoint();
                            SupperMouseKey.LeftClick(point);
                        }
                    }
                    else
                    {
                        SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
                    }
                }
                else
                {
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
                }
                RandomWait.Wait(1000, 3000);
                this.CloseChatInfoPane();
            }
        }

        /// <summary>
        /// 删除群聊，适用于自有群,与退出群聊不同，退出群聊是退出群聊，删除群聊会删除自有群的所有好友，然后退出群聊
        /// willdo: 这里有一个问题，如果删除群的好友很多，则需要滚屏才能全部选中。
        /// </summary>
        /// <param name="groupName">群聊名称</param>
        /// <returns>微信响应结果<see cref="ChatResponse"/></returns>
        public async Task<ChatResponse> DeleteOwnerChatGroup(string groupName) => throw new Exception("待完成");
        //=> await WxMainWindow.DeleteOwnerChatGroup(groupName);
        /// <summary>
        /// 移除群聊成员,适用于自有群
        /// </summary>
        /// <param name="groupName">群聊名称,可以为空，如果为空，则从焦点聊天群聊中移除好友</param>
        /// <param name="memberName">成员名称</param>
        /// <returns>微信响应结果<see cref="Result"/></returns>
        public async Task<Result> RemoveOwnerChatGroupMember(string groupName, OneOf<string, string[]> memberName)
        {
            if (!string.IsNullOrWhiteSpace(groupName))
            {
                var find = await _Client.Conversations.Search(groupName);
                if (!find)
                    return Result.Fail($"错误：未找到群： {groupName} ,移除好友动作失败！"); ;
            }
            var headInfo = await this._Client.GetTitle();
            if (!headInfo.CanTalk() || headInfo.HeaderType != ChatType.群聊)
                return Result.Fail("错误：此窗口为非聊天窗口");
            return await WeChatInvoker.Call(RemoveOwnerChatGroupMemberCore, memberName, headInfo.Title);
        }

        private Result RemoveOwnerChatGroupMemberCore(UIA3Automation automation, OneOf<string, string[]> memberName, string groupName)
        {
            var paneRoot = PaneRoot;
            var point = this._Client.OcrEngee.OCRVerticalDetect(paneRoot, 0.5f, "移出");
            if (point.IsEmpty)
                return Result.Fail("");
            this._Client.MainWindow.Focus();
            Mouse.Position = paneRoot.BoundingRectangle.Center();
            RandomWait.Wait(600, 1200);
            var point2 = (new Point(point.X, point.Y - 30)).Confusion(10, 5);
            SupperMouseKey.MoveTo(point2);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.LeftClick();
            //处理删人事宜
            return ProcessRemoveMembers(memberName, automation);
        }

        internal Result ProcessRemoveMembers(OneOf<string, string[]> memberName, UIA3Automation automation)
        {
            var memberList = memberName.IsT0 ? new List<string> { memberName.AsT0.Trim() } : memberName.AsT1.ToList().Select(x => x.Trim()).ToList();
            if (memberList.Count() == 0)
                return Result.Fail("错误：memberList列表为空！");
            var editPath = "/Window[@Name='微信移出群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/Group/Edit[@Name='搜索'][@ClassName='mmui::XValidatorTextEdit']";
            var searchEditRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(editPath), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            var path = "";
            if (searchEditRetry.Success)
            {
                var editParent = searchEditRetry.Result.GetParent();
                foreach (var m in memberList)
                {
                    //清空
                    var clearButton = editParent.FindFirstChild(cf => cf.ByName("清空")).AsButton();
                    if (clearButton != null)
                    {
                        clearButton.Click();
                        RandomWait.Wait(600, 1500);
                    }
                    var searchEdit = this._Client.MainWindow.FindFirstByXPath(editPath).AsTextBox();
                    searchEdit.Text = m;
                    RandomWait.Wait(800, 2500);
                    path = "/Window[@Name='微信移出群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/List[@AutomationId='sp_search_list']";
                    var itemRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
                    if (itemRetry.Success)
                    {
                        var items = itemRetry.Result.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem)).ToList();
                        if (items.Count > 0)
                        {
                            var item = items[0];
                            var point = item.BoundingRectangle.Center();
                            Mouse.Position = point.Confusion(10, 4);
                            RandomWait.Wait(100, 300);
                            SupperMouseKey.MoveTo(point.Confusion(10, 4));
                            RandomWait.Wait(300, 900);
                            SupperMouseKey.LeftClick();
                        }
                    }
                    //停顿，准备下一个勾选
                    RandomWait.Wait(1200, 3000);
                }
                //确认是点击确定还是取消
                path = "/Window[@Name='微信移出群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/Button[@Name='移出'][@AutomationId='confirm_btn']";
                var addRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
                if (addRetry.Success)
                {
                    var addButton = addRetry.Result.AsButton();
                    if (addButton.IsEnabled)
                    {
                        var point = addButton.BoundingRectangle.Center();
                        Mouse.Position = point.Confusion(10, 4);
                        RandomWait.Wait(100, 300);
                        SupperMouseKey.MoveTo(point.Confusion(10, 4));
                        RandomWait.Wait(300, 900);
                        SupperMouseKey.LeftClick();
                        RandomWait.Wait(600, 2000);
                    }
                    else
                    {
                        SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
                        return Result.Fail("删除群内好友失败！");
                    }
                }
                else
                {
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
                    return Result.Fail("删除群内好友失败！");
                }
                RandomWait.Wait(1000, 3000);
                this.CloseChatInfoPane();
                return Result.Ok();
            }
            return Result.Fail("删除群里好友失败！");
        }
    }
}