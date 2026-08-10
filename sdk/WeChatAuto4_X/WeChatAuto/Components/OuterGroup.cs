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
using WeChatAuto.Options;
using System.IO;

namespace WeChatAuto.Components
{

    /// <summary>
    /// 他有群管理
    /// </summary>
    public class OuterGroup : Group
    {
        internal OuterGroup(WeChatClient client, UIThreadInvoker uiThreadInvoker, IServiceProvider serviceProvider) :
            base(client, uiThreadInvoker, serviceProvider)
        {

        }

        /// <summary>
        /// 邀请群聊成员,适用于外部群
        /// </summary>
        /// <param name="groupName">群聊名称,可以为空，如果为空，则在本焦点群聊窗口邀请好友</param>
        /// <param name="members">被邀请的成员名称列表,要求在自己的通讯录中</param>
        /// <param name="inviteReasonIfNeed">邀请原因，只在群管理员开启了 进群需要群主或者管理员确认 功能时有效，可以为空</param>
        /// <returns>微信响应结果<see cref="Result"/></returns>
        public async Task<Result> InviteChatGroupMember(string groupName, List<string> members, string inviteReasonIfNeed = "")
        {
            if (!string.IsNullOrWhiteSpace(groupName))
            {
                var find = await _Client.Conversations.Search(groupName);
                if (!find)
                    return Result.Fail($"错误:未找名为 {groupName} 的群聊!");
            }
            var headInfo = await this._Client.GetTitle();
            if (!headInfo.CanTalk() || headInfo.HeaderType != ChatType.群聊)
                return Result.Fail($"错误：群聊窗口状态错误，或者不是群聊");
            return await WeChatInvoker.Call(InviteChatGroupMemberCore, headInfo.Title, members, inviteReasonIfNeed);
        }

        private Result InviteChatGroupMemberCore(UIA3Automation automation, string groupName, List<string> members, string reason)
        {
            Result result = _PopupInviteWindow(automation, groupName);  //弹出邀请好友窗口
            if (!result.Success) return result;
            result = _SelectInviteMembers(automation, groupName, members);
            if (!result.Success) return result;
            result = _ClickAddButton(automation, groupName);
            if (!result.Success)
            {
                SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
                CloseChatInfoPane();
                return result;
            }
            result = _ClickOwnerConfirm(automation, groupName, reason);
            result = _ClickConfirmButtonIfExist(automation, groupName);
            this.CloseChatInfoPane();
            return result;
        }

        private Result _SelectInviteMembers(UIA3Automation automation, string groupName, List<string> members)
        {
            var path = "/Window[@Name='微信添加群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/Group/Edit[@Name='搜索'][@ClassName='mmui::XValidatorTextEdit']";
            var editRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (editRetry.Success)
            {
                foreach (var m in members)
                {
                    var edit = editRetry.Result.AsTextBox();
                    var parent = edit.GetParent();
                    var clearButton = parent.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("清空")));
                    if (clearButton != null)
                    {
                        clearButton.Click();
                        RandomWait.Wait(300, 900);
                    }
                    edit.Focus();
                    edit.Text = m;
                    RandomWait.Wait(1000, 3000);
                    path = "/Window[@Name='微信添加群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/List[@AutomationId='sp_search_result_list'][@Name='请勾选需要添加的联系人']";
                    var items = this._Client.MainWindow.FindFirstByXPath(path).AsListBox();
                    var item = items.FindAllChildren(cf => cf.ByControlType(ControlType.CheckBox)).FirstOrDefault(x => x.Name.Trim().Equals(m.Trim()));
                    if (item != null)
                    {
                        if (item.Patterns.Toggle.IsSupported)
                        {
                            //可以点击，否则不能点击
                            var point = item.BoundingRectangle.Center();
                            Mouse.Position = point.Confusion(10, 4);
                            RandomWait.Wait(100, 300);
                            SupperMouseKey.MoveTo(point.Confusion(10, 4));
                            RandomWait.Wait(300, 900);
                            SupperMouseKey.LeftClick();
                        }
                    }

                    RandomWait.Wait(1000, 4000);
                }
                return Result.Ok();
            }
            return Result.Fail("错误：选择被邀请成员时出错！");
        }

        private Result _ClickAddButton(UIA3Automation automation, string groupName)
        {
            var path = "/Window[@Name='微信添加群成员'][@ClassName='mmui::SessionPickerWindow']/Group/Group/Button[@Name='添加'][@AutomationId='confirm_btn']";
            var buttonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (buttonRetry.Success)
            {
                var button = buttonRetry.Result;
                if (button.IsEnabled)
                {
                    var point = button.BoundingRectangle.Center();
                    Mouse.Position = point.Confusion(10, 2);
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(10, 2));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(1000, 4000);
                    return Result.Ok();
                }
            }
            return Result.Fail("错误：点击 增加 按钮出错，可能增加按钮不可点击！");
        }
        private Result _ClickOwnerConfirm(UIA3Automation automation, string groupName, string reason)
        {
            var path = "/Window[@Name='Weixin']/Group/Group/Group/Button[@Name='邀请']";
            var inviteButtonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (inviteButtonRetry.Success)
            {
                var inviteButton = inviteButtonRetry.Result.AsButton();
                if (!string.IsNullOrWhiteSpace(reason))
                {
                    path = "/Window[@Name='Weixin']/Group/Group/Group/Edit/Group[@AutomationId='qt_scrollarea_viewport']";
                    var group = this._Client.MainWindow.FindFirstByXPath(path);
                    if (group != null)
                    {
                        var edit = group.GetParent().AsTextBox();
                        edit.Focus();
                        RandomWait.Wait(300, 900);
                        edit.Text = reason;
                        RandomWait.Wait(1000, 2000);
                    }
                }
                inviteButton.Click();
                RandomWait.Wait(1000, 4000);
            }
            return Result.Ok();
        }
        private Result _ClickConfirmButtonIfExist(UIA3Automation automation, string groupName)
        {
            var path = "/Window[@Name='Weixin']/Group/Group/Group/Button[@Name='邀请']";
            var inviteButtonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (inviteButtonRetry.Success)
            {
                var inviteButton = inviteButtonRetry.Result.AsButton();
                inviteButton.Click();
                RandomWait.Wait(1000, 4000);
            }
            return Result.Ok();
        }

        private Result _PopupInviteWindow(UIA3Automation automation, string groupName)
        {
            var paneRoot = PaneRoot;
            var point = this._Client.OcrEngee.OCRVerticalDetect(paneRoot, 0.5f, "添加");
            if (point.IsEmpty)
                return Result.Fail("错误: OCR 添加 按钮失败!");
            this._Client.MainWindow.Focus();
            Mouse.Position = paneRoot.BoundingRectangle.Center();
            RandomWait.Wait(600, 1200);
            var point2 = new Point(point.X, point.Y - 30).Confusion(10, 5);
            SupperMouseKey.MoveTo(point2);
            RandomWait.Wait(300, 1200);
            SupperMouseKey.LeftClick();
            RandomWait.Wait(800, 1500);
            return Result.Ok();
        }


        /// <summary>
        /// 添加群聊里面的好友为自己的好友,适用于从外部群中添加好友为自己的好友
        /// 此操作为微信严风控操作，因为微信对于一天加好友应该有数量限定，建议分批次加，一次不要超过20-30个，时间延长为4小时或者一天后
        /// </summary>
        /// <param name="groupName">群聊名称,可以为空，如果为空，则在本焦点群聊窗口邀请好友</param>
        /// <param name="memberName">成员名称列表,考虑风控,建议先运行<see cref="Group.GetChatGroupMemberList(string)"/>获取群聊的成员列表，然后分批增加</param>
        /// <param name="options">好友选项，可以增加好友时设置备注后缀、打招呼内容及标签等，方便分类管理</param>
        /// <returns></returns>
        public async Task<IDictionary<string, FriendAddResult>> AddChatGroupMemberToFriends(string groupName, List<string> memberName, AddFriendsOptions options = null)
        {
            if (!string.IsNullOrWhiteSpace(groupName))
            {
                var find = await _Client.Conversations.Search(groupName);
                if (!find)
                    return new Dictionary<string, FriendAddResult>();
            }
            var headInfo = await this._Client.GetTitle();
            if (!headInfo.CanTalk() || headInfo.HeaderType != ChatType.群聊)
                return new Dictionary<string, FriendAddResult>();
            return await WeChatInvoker.Call(AddChatGroupMemberToFriendsCore, headInfo.Title, memberName, options);
        }

        private IDictionary<string, FriendAddResult> AddChatGroupMemberToFriendsCore(UIA3Automation automation, string groupName, List<string> memberName, AddFriendsOptions options)
        {
            if (options == null)
            {
                options = new AddFriendsOptions();
            }
            var returnList = new Dictionary<string, FriendAddResult>();
            memberName = memberName.Where(u => !u.Equals(this._Client.NickName)).ToList();
            var paneRoot = PaneRoot;  //打开窗口
            Result result = _SearchAndAddFriend(automation, memberName, paneRoot, returnList, options);
            this.CloseChatInfoPane();
            return returnList;
        }

        private Result _SearchAndAddFriend(UIA3Automation automation, List<string> memberName, AutomationElement paneRoot, Dictionary<string, FriendAddResult> returnList, AddFriendsOptions options)
        {
            var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group/Group/Edit[@Name='搜索']";
            var searchRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (searchRetry.Success)
            {
                var search = searchRetry.Result.AsTextBox();
                foreach (var item in memberName)
                {
                    var point = search.BoundingRectangle.Center();
                    #region 首先清历史
                    if (Probability.Hit(0.7))
                    {
                        //优先考虑用 清空 按钮清空
                        var parent = search.GetParent();
                        var clearBtn = parent.FindFirstChild(cf => cf.ByName("清空").And(cf.ByControlType(ControlType.Button)));
                        if (clearBtn != null)
                        {
                            var btnPoint = clearBtn.BoundingRectangle.Center();
                            Mouse.Position = btnPoint.Confusion(2, 2);
                            RandomWait.Wait(100, 300);
                            SupperMouseKey.MoveTo(btnPoint.Confusion(2, 2));
                            RandomWait.Wait(300, 900);
                            SupperMouseKey.LeftClick();
                            RandomWait.Wait(300, 900);
                        }
                    }
                    else
                    {
                        Mouse.Position = point.Confusion(20, 4);
                        RandomWait.Wait(100, 300);
                        SupperMouseKey.MoveTo(point.Confusion(20, 4));
                        RandomWait.Wait(300, 900);
                        SupperMouseKey.LeftClick();
                        RandomWait.Wait(300, 900);
                        SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
                        RandomWait.Wait(300, 900);
                        SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
                        RandomWait.Wait(300, 900);
                    }
                    #endregion
                    #region 查询
                    ClipboardHelper.SetText(item);
                    Mouse.Position = point.Confusion(20, 4);
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(20, 4));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
                    RandomWait.Wait(1000, 3000);
                    #endregion
                    #region 加好友
                    var resultGroup = search.GetParent().GetSibling(1);
                    if (resultGroup == null)
                        continue;
                    var listBox = resultGroup.FindFirstChild(cf => cf.ByControlType(ControlType.List));
                    if (listBox == null)
                        continue;
                    var items = listBox.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem));
                    var listItem = items.FirstOrDefault(cf => cf.Name.Equals(item));
                    if (listItem == null)
                        continue;
                    point = listItem.BoundingRectangle.Center();
                    SupperMouseKey.MoveTo(point.Confusion(10, 4));
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(10, 4));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(600, 1500);
                    var exit = __ParseResult(automation, item, returnList, options);
                    if (exit)
                        break;
                    #endregion

                    RandomWait.Wait(System.Math.Max(options.IntervalTime - 1, 0) * 1000, Math.Max(options.IntervalTime + 1, 1) * 1000);
                }

                return Result.Ok();
            }

            return Result.Fail("错误：在他有群增加好友时出错！");
        }

        private bool __ParseResult(UIA3Automation automation, string who, Dictionary<string, FriendAddResult> returnList, AddFriendsOptions options)
        {
            //第一种情况： 已是好友判断
            var desktop = automation.GetDesktop();
            var path = $"/Window[@Name='Weixin'][@ProcessId={this._Client.MainWindow.Properties.ProcessId}]/Group/Group/Group/Group/Group/Group/Group/Text[@AutomationId='right_v_view.user_info_center_view.basic_line_view.basic_line.key_text'][@Name='微信号：']";
            var wxRetry = Retry.WhileNull(() => desktop.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (wxRetry.Success)
            {
                returnList.Add(who, FriendAddResult.Friend);
                SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
                return false;
            }
            //第二种：不能添加、第三种: 添加中，需要对方验证，第四种情况：不需要验证，一加就通过了
            path = $"/Window[@Name='Weixin'][@ProcessId={this._Client.MainWindow.Properties.ProcessId}]/Group/Group/Group/Group/Button[@Name='添加到通讯录'][@AutomationId='content_v_view.ProfileActionUi.add_friend_button']";
            var addButtonRetry = Retry.WhileNull(() => desktop.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (!addButtonRetry.Success)
                return false;
            var point = addButtonRetry.Result.BoundingRectangle.Center();
            SupperMouseKey.MoveTo(point.Confusion(10, 4));
            RandomWait.Wait(100, 300);
            SupperMouseKey.MoveTo(point.Confusion(10, 4));
            RandomWait.Wait(300, 900);
            SupperMouseKey.LeftClick();
            RandomWait.Wait(600, 1500);

            //添加信息
            __ConfigAddInfomation(automation, returnList, who, options);
            //判断与返回状态
            var result = __RetrunStatus(automation, returnList, who);
            return result;
        }

        private void __ConfigAddInfomation(UIA3Automation automation, Dictionary<string, FriendAddResult> result, string friend, AddFriendsOptions options)
        {
            var desktop = automation.GetDesktop();
            var addWinRetry = Retry.WhileNull(() => desktop.FindFirstChild(cf => cf.ByName("申请添加朋友").And(cf.ByClassName("mmui::VerifyFriendWindow").And(cf.ByControlType(ControlType.Window)).And(cf.ByProcessId(this._Client.MainWindow.Properties.ProcessId)))), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (addWinRetry.Success)
            {
                var addWin = addWinRetry.Result.AsWindow();
                this._Client.MoveWinToMainCenter(addWin);
                if (options != null && !string.IsNullOrWhiteSpace(options.SayHi))
                {
                    var path = "/Group/Group/Group/Group/Group/Group/Group/Edit[@Name='发送添加朋友申请'][@ClassName='mmui::XValidatorTextEdit']";
                    var edit = addWin.FindFirstByXPath(path);
                    var point = edit.BoundingRectangle.SafeRandomPoint();
                    SupperMouseKey.MoveTo(point);
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(10, 5));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(300, 900);
                    ClipboardHelper.SetText(options.SayHi);
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
                    RandomWait.Wait(600, 2000);
                }
                if (options != null && !string.IsNullOrWhiteSpace(options.Suffix))
                {
                    var path = "/Group/Group/Group/Group/Group/Group/Text/Edit[@Name='修改备注'][@ClassName='mmui::XLineEdit']";
                    var edit = addWin.FindFirstByXPath(path);
                    var memoName = edit.GetParent().Name;  //得到名字，但是名字可能是空格等异常情况.
                    if (string.IsNullOrWhiteSpace(memoName))
                    {
                        memoName = Path.GetFileNameWithoutExtension(Path.GetRandomFileName());  //如果为空，则得到一个随机名称
                    }
                    if (!memoName.EndsWith($"_{options.Suffix}"))
                    {
                        memoName = $"{memoName}_{options.Suffix}";
                    }
                    var point = edit.BoundingRectangle.SafeRandomPoint();
                    SupperMouseKey.MoveTo(point);
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(point.Confusion(10, 5));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(300, 900);
                    ClipboardHelper.SetText(memoName);
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.BACK);
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
                    RandomWait.Wait(600, 2000);

                }
                if (options != null && !string.IsNullOrWhiteSpace(options.Label))
                {
                    var lableItem = addWin.FindFirstByXPath("/Group/Group/Group/Group/Group/Group/Button[@Name='修改标签'][@AutomationId='button']");
                    var point = lableItem.BoundingRectangle.SafeRandomPoint();
                    Mouse.MoveTo(point);
                    RandomWait.Wait(100, 600);
                    Mouse.LeftClick();
                    RandomWait.Wait(1000, 2500);
                    //标签名可能已经存在，或者不存在，需要新建.
                    var list = addWin.FindFirstDescendant(cf => cf.ByControlType(ControlType.List).And(cf.ByClassName("mmui::XTableView")).And(cf.ByName("标签"))).AsListBox();
                    var items = list.FindAllChildren(cf => cf.ByControlType(ControlType.CheckBox));
                    if (items.Select(x => x.Name).Where(x => x.Equals(options.Label)).Count() > 0)
                    {
                        //已经有标签
                        var selectItem = items.FirstOrDefault(x => x.Name.Equals(options.Label));
                        if (selectItem != null)
                        {
                            var point2 = selectItem.BoundingRectangle.SafeRandomPoint();
                            Mouse.MoveTo(point2);
                            Mouse.LeftClick();
                            RandomWait.Wait(300, 900);
                        }
                    }
                    else
                    {
                        //无标签，需要新建
                        var searchEdit = addWin.FindFirstDescendant(cf => cf.ByControlType(ControlType.Edit).And(cf.ByName("搜索")).And(cf.ByClassName("mmui::XValidatorTextEdit")));
                        if (searchEdit != null)
                        {
                            searchEdit.Focus();
                            var point2 = searchEdit.BoundingRectangle.SafeRandomPoint();
                            Mouse.Click(point2);
                            ClipboardHelper.SetText(options.Label);
                            Keyboard.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
                            RandomWait.Wait(300, 900);
                            list = addWin.FindFirstDescendant(cf => cf.ByControlType(ControlType.List).And(cf.ByClassName("mmui::XTableView")).And(cf.ByName("标签"))).AsListBox();
                            var createItemRetry = Retry.WhileNull(() => list.Items.Where(u => u.Name.Contains("创建新标签") && u.ControlType == ControlType.ListItem).FirstOrDefault(),
                            timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
                            if (createItemRetry != null)
                            {
                                var createItem = createItemRetry.Result;
                                point2 = createItem.BoundingRectangle.SafeRandomPoint();
                                Mouse.Click(point2);
                                RandomWait.Wait(300, 900);
                            }
                        }
                    }
                    var randomRetry = Random.Shared.Next(1, 10);
                    if (randomRetry <= 5)
                    {
                        //点击备注栏
                        var clkItem = addWin.FindFirstDescendant(cf => cf.ByControlType(ControlType.Edit).And(cf.ByName("修改备注").And(cf.ByClassName("mmui::XLineEdit"))));
                        clkItem.Click();
                    }
                    else
                    {
                        //点击“确定上面一点”
                        var button = addWin.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("确定")).And(cf.ByClassName("mmui::XOutlineButton")));
                        if (button != null)
                        {
                            var buttonRect = button.BoundingRectangle;
                            var point2 = new Rectangle(buttonRect.X - 100, buttonRect.Y, 90, buttonRect.Height).SafeRandomPoint();
                            Mouse.MoveTo(point2);
                            Mouse.Click();
                        }
                    }
                }
                //点击确定
                RandomWait.Wait(1000, 3000);
                var confirmButton = addWin.FindFirstDescendant(cf => cf.ByControlType(ControlType.Button).And(cf.ByName("确定")).And(cf.ByClassName("mmui::XOutlineButton")));
                if (confirmButton != null)
                {
                    SupperMouseKey.MoveTo(confirmButton.BoundingRectangle.Center().Confusion(10, 5));
                    RandomWait.Wait(100, 300);
                    SupperMouseKey.MoveTo(confirmButton.BoundingRectangle.Center().Confusion(10, 5));
                    RandomWait.Wait(300, 900);
                    SupperMouseKey.LeftClick();
                    RandomWait.Wait(1000, 1500);
                }
            }
        }

        private bool __RetrunStatus(UIA3Automation automation, Dictionary<string, FriendAddResult> returnList, string who)
        {
            //操作过于频繁，请稍后再试
            var path = "/Window[@Name='Weixin'][@ClassName='mmui::XDialog']/Group/Text[@Name='操作过于频繁，请稍后再试。']";
            var exitRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
            if (exitRetry.Success)
            {
                var exit = exitRetry.Result;
                var parent = exit.GetParent();
                path = "/Group/Group/Button[@Name='确定']";
                var button = parent.FindFirstByXPath(path);
                if (button != null)
                {
                    button.Click();
                    RandomWait.Wait(600, 1500);
                }
                return true;
            }
            //第二种情况： 不能添加
            path = "/Window[@Name='Weixin'][@ClassName='mmui::XDialog']/Group/Text[@Name='由于对方的隐私设置，你无法通过群聊将其添加至通讯录。']";
            var rejectRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (rejectRetry.Success)
            {
                var reject = rejectRetry.Result;
                var parent = reject.GetParent();
                path = "/Group/Group/Button[@Name='确定']";
                var button = parent.FindFirstByXPath(path);
                if (button != null)
                {
                    button.Click();
                    RandomWait.Wait(600, 1500);
                }
                returnList.Add(who, FriendAddResult.PrivacyRestricted);
                System.Diagnostics.Debug.WriteLine($"风控测试，实际增加至: {returnList.Count}个");
                return false;
            }
            path = "/Window[@Name='Weixin'][@ClassName='mmui::XDialog']/Group//Group/Group/Button[@Name='确定']";
            var errorRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (errorRetry.Success)
            {
                var errButton = errorRetry.Result;
                errButton.Click();
                return false;
            }
            //第三种情况：添加中，或者第四种情况：通过
            RandomWait.Wait(2000, 4000);
            var visibleList = this._Client.Conversations.GetVisibleConversationsCore(automation);
            var item = visibleList.FirstOrDefault(u => u.ConversationTitle.Equals(who));
            if (item == null)
            {
                returnList.Add(who, FriendAddResult.Adding);
                System.Diagnostics.Debug.WriteLine($"实际增加至: {returnList.Count}个");
            }
            else
            {
                System.Diagnostics.Debug.WriteLine($"风控测试，实际增加至: {returnList.Count}个");
                returnList.Add(who, FriendAddResult.Added);
                System.Diagnostics.Debug.WriteLine($"实际增加至: {returnList.Count}个");
            }
            return false;
        }
    }
}