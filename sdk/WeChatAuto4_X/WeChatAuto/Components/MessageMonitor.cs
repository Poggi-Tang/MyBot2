using System;
using System.Collections.Generic;
using System.Linq;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.Core.Input;
using FlaUI.Core.WindowsAPI;
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
using System.Threading;
using System.Diagnostics;
using WeChatAuto.Models;
using OneOf;
using System.Collections.Concurrent;
using WeChatAuto.Services;
using System.Text.RegularExpressions;
using WeChatAuto.Options;
using System.ComponentModel.DataAnnotations;
using System.Configuration;
using System.Drawing.Imaging;
using System.Globalization;
using Emgu.CV;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text;
using System.Runtime.InteropServices;
namespace WeChatAuto.Components
{
    /// <summary>
    /// 消息监听器
    /// </summary>
    public class MessageMonitor : IDisposable
    {
        private int _disposed = 0;
        private readonly WeChatClient _Client;
        private readonly Random random = new Random((int)DateTime.Now.Ticks);
        private readonly IServiceProvider serviceProvider;
        private readonly UIThreadInvoker _MainThreadInvoker;
        private readonly SemaphoreSlim noticeEvent;
        private readonly AutoLogger<MessageMonitor> _Logger;
        #region 消息监听字段
        //消息监听
        private int messageListnerStartedFlag = 0;   //消息监听启用标识
        private bool conversationStarted = true;
        private int totalNewMessage = 0;   //新消息数量
        private readonly ConcurrentDictionary<string, bool> _MonitorList = new ConcurrentDictionary<string, bool>();
        private readonly ConcurrentDictionary<string, bool> _FriendSession = new ConcurrentDictionary<string, bool>();  //首次与非首次session.
        private readonly ConcurrentDictionary<string, string> _ConversationSnapshot = new ConcurrentDictionary<string, string>();  //会话的快照
        private readonly ConcurrentDictionary<string, (string Message, DateTime ExpiresAt)> _OutgoingPreviewEchoes = new();
        private CancellationTokenSource messageGlobalCts = new CancellationTokenSource();
        private Task messageRunningTask;
        private Action<MessageContext> messageCallback;
        private Action<string> UIInvoker;
        private int _IsContinue = 1;
        private int pauseTime = Random.Shared.Next(6 * 60 * 1_000, 10 * 60 * 1_000);  //6与10分钟的某个时间段
        //系统消息监听
        private int systemListnerStartedFlag = 0;   //系统消息监听启用标识
        private readonly List<Thread> _SystemMonitors = new List<Thread>();
        #endregion

        /// <summary>
        /// <para>构造器，不应该自行调用</para>
        /// </summary>
        /// <param name="client"></param>
        /// <param name="serviceProvider"></param>
        /// <param name="resetEvent"></param>
        /// <param name="_uiMainThreadInvoker"></param>
        internal MessageMonitor(WeChatClient client, IServiceProvider serviceProvider, UIThreadInvoker _uiMainThreadInvoker, SemaphoreSlim resetEvent)
        {
            this._Client = client;
            this.serviceProvider = serviceProvider;
            this._MainThreadInvoker = _uiMainThreadInvoker;
            this.noticeEvent = resetEvent;

            _Logger = serviceProvider.GetRequiredService<AutoLogger<MessageMonitor>>();
        }

        #region 消息监听
        /// <summary>
        /// <para>添加系统消息监听，以实现如： 检测到群主邀请好友后发送欢迎消息等功能</para>
        /// <para>注意：仅适用于群聊，不适用个人,个人请使用下面的开放式/固定式监听，另外，不支持注册监听后再新增待监听的群聊</para>
        /// <para>多线程监听变化，但是操作等，还得在微信单线程中执行.</para>
        /// </summary>
        /// <param name="nickNames">群聊昵称，可以多个</param>
        /// <param name="callBack">回调函数,由用户提供,参数：消息上下文<see cref="SystemMessageContext"/></param>
        /// <param name="userToken">取消令牌,请参考<see cref="CancellationToken"/>,可以自行取消消息监听</param>
        public async Task AddGroupSystemMessageListener(OneOf<string, List<string>, string[]> nickNames, Func<SystemMessageContext, Task> callBack, CancellationToken userToken = default)
        {
            await AddGroupSystemMessageListenerCore(nickNames, callBack, userToken);
        }
        private async Task AddGroupSystemMessageListenerCore(OneOf<string, List<string>, string[]> nickNames, Func<SystemMessageContext, Task> callBack, CancellationToken userToken)
        {
            if (Interlocked.CompareExchange(ref this.systemListnerStartedFlag, 1, 0) == 1)
            {
                return;
            }
            var token = CancellationToken.None;
            CancellationTokenSource linkdedCts = default;
            try
            {
                if (userToken != default)
                {
                    linkdedCts = CancellationTokenSource.CreateLinkedTokenSource(messageGlobalCts.Token, userToken);
                    token = linkdedCts.Token;
                }
                else
                {
                    token = messageGlobalCts.Token;
                }

                await this._Client._InitializeSystemMonitorConsumption();  //初始化系统消息消费者.

                var subWinTitles = nickNames.IsT0 ? new List<string>() { nickNames.AsT0 } : nickNames.IsT1 ? nickNames.AsT1 : nickNames.AsT2.ToList();
                foreach (var who in subWinTitles)
                {
                    SystemMonitorOption options = new SystemMonitorOption();
                    options.Who = who;
                    options.Token = token;
                    options.CallBack = callBack;

                    Thread thread = new Thread(new ParameterizedThreadStart((obj) => __GroupSystemMonitorRun(obj).GetAwaiter().GetResult()));
                    thread.Priority = ThreadPriority.Normal;
                    thread.SetApartmentState(ApartmentState.STA);
                    thread.IsBackground = true;
                    thread.Start(options);

                    _SystemMonitors.Add(thread);
                }
            }
            catch (OperationCanceledException)
            {

            }
            catch (Exception ex)
            {
                _Logger.Error($"监听系统消息发生错误：{ex.ToString()}");
            }
            finally
            {
                if (linkdedCts != default)
                    linkdedCts?.Dispose();
            }
        }
        //群聊系统监控运行代码
        private async Task __GroupSystemMonitorRun(object obj)
        {
            SystemMonitorOption options = obj as SystemMonitorOption;
            var thradName = options.Who + "_GroupSystemMontitorRun";
            using PeriodicTimer timer = new PeriodicTimer(TimeSpan.FromSeconds(WeAutomation.Config.MonitorGroupInterval));
            try
            {
                var token = options.Token;
                using UIA3Automation automation = new UIA3Automation();
                List<string> oldSnapshot = new List<string>();
                bool firstFlag = true;
                while (await timer.WaitForNextTickAsync(token).ConfigureAwait(false))
                {
                    try
                    {
                        //首先检查是否打开窗口
                        var subWin = this._Client.Conversations.OpenSubWinCore(automation, options.Who);
                        if (subWin == null)
                            continue;
                        var newMessages = __FetchSystemMessageSession(subWin, ref oldSnapshot, token);
                        if (firstFlag)
                        {
                            //首次不取值.
                            firstFlag = false;
                            continue;
                        }
                        if (newMessages.Count > 0)
                        {
                            await this._Client.SystemMonitorChannel.Writer.WriteAsync((options, newMessages), token);
                        }
                    }
                    catch (OperationCanceledException)
                    {
                        //do nothing.
                    }
                    catch (Exception ex)
                    {
                        _Logger.Error($"{thradName}出现错误:{ex.ToString()}");
                    }
                }
            }
            catch (OperationCanceledException)
            {
                //do nothing.
            }
            catch (Exception ex)
            {
                _Logger.Error($"{thradName}出现错误:{ex.ToString()}");
            }
        }

        private List<string> __FetchSystemMessageSession(Window subWin, ref List<string> oldSnapshot, CancellationToken token)
        {
            token.ThrowIfCancellationRequested();
            var thisMessageSnapshot = new List<string>();
            var result = new List<string>();
            var path = "/Group/Group/Group/Custom/Group/Group/List[@Name='消息'][@AutomationId='chat_message_list'][@ClassName='mmui::RecyclerListView'] | /Group/Group/Group/Custom/Group/List[@Name='消息'][@AutomationId='chat_message_list'][@ClassName='mmui::RecyclerListView']";
            var rootRetry = Retry.WhileNull(() => subWin.FindFirstByXPath(path), TimeSpan.FromSeconds(3), TimeSpan.FromMilliseconds(200));
            if (rootRetry.Success)
            {
                var root = rootRetry.Result.AsListBox();
                //如果有最新消息
                var existNewMessageButton = root.GetSibling(1);
                if (existNewMessageButton != null && existNewMessageButton.ControlType == ControlType.Button && existNewMessageButton.Name.Contains("新消息"))
                {
                    //检查是不是最下面
                    var centerPointY = root.BoundingRectangle.Center().Y;
                    if (existNewMessageButton.BoundingRectangle.Y > centerPointY)
                    {
                        existNewMessageButton.AsButton().Click();
                        RandomWait.Wait(300,900);
                    }
                }
                var items = root.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem).And(cf.ByClassName("mmui::ChatItemView")));
                //过滤掉时间
                foreach (var item in items)
                {
                    token.ThrowIfCancellationRequested();
                    var pattern = @"\s*\d{2}:\d{2}$";
                    Match match = Regex.Match(item.Name, pattern);
                    if (!match.Success)
                    {
                        thisMessageSnapshot.Add($"{item.Name}|{item.Properties.RuntimeId.ToUniqueString()}");
                    }
                }
                var exceptList = thisMessageSnapshot.Except(oldSnapshot).ToList();
                oldSnapshot = thisMessageSnapshot;
                if (exceptList.Count > 0)
                {
                    result = exceptList.Select(r => r.Split('|', StringSplitOptions.RemoveEmptyEntries)[0]).ToList();
                }
            }

            return result;
        }



        /// <summary>
        /// <para>添加消息监听，用户需要提供一个回调函数，当有消息时，会调用此回调函数</para>
        /// <para>参考<see cref="MessageContext"/></para>
        /// 
        /// <para>使用规则：</para> 
        /// <para>1. 仅能监听“允许消息通知”的好友/群聊,所以需要监听的好友/群聊不要设置为“消息免打扰”;</para>
        /// <para>2. 如果要避免太多消息影响，请将不监听的好友/群设置为“消息免打扰”，以提高监听性能;</para>
        /// <para>3. 此方法可以多次添加，第一次添加时会启动消息监听，第二次（类似的第三次等）添加效果等同<see cref="AddListeningFriend"/>方法</para>
        /// <para>4. 为了减少会话窗口的滚动，建议不要添加太多消息“置顶”，以提高监听效率.</para>
        /// <para>执行逻辑:</para>
        /// <para>1. 启动消息监听器时做做一次全量扫描，即：SDK会将会话列表整个循环一编，会自动点击并回调用户设定的方法，以防止遗漏消息</para>
        /// <para>2. 以后的监听过程会增量监听，以提高效率.</para>
        /// </summary>
        /// <param name="nickNames">好友昵称,可以是一个，也可以是多个好友/群聊 </param>
        /// <param name="callBack">回调函数,由用户提供,参数：消息上下文<see cref="MessageContext"/></param>
        /// <param name="IsOpenMonitor">是否开启开放式监听，默认不开放(值为false）,如果开启开放式监听，前面的nickNames可以为空，所谓的开放式监听的含义是：无须固定好友/群监听，只要此好友/群没有设置“消息免打挠”就可以监听,而固定式监听为只监听设定的好友/群</param>
        /// <param name="userToken">取消令牌,请参考<see cref="CancellationToken"/>,可以自行取消消息监听</param>
        /// <param name="UIInvoker">UI的调度器，适用于把微信嵌入UI的场景使用，如：多微信切换Tab页等,SDK会给调用者注入一个微信名称</param>
        /// <param name="options">监听选项，具体请参见<see cref="MessageMonitorOptions"/></param>
        public async Task AddMessageListener(OneOf<string, List<string>, string[]> nickNames, Action<MessageContext> callBack, bool IsOpenMonitor = false, CancellationToken userToken = default, Action<string> UIInvoker = null, MessageMonitorOptions options = null)
        => await AddMessageListenerCore(nickNames, callBack, IsOpenMonitor, userToken, UIInvoker, new DateTimeRange(), options);

        /// <summary>
        /// 添加一个从什么时候开始，什么时候结束的消息监听，用户需要提供一个回调函数，当有消息时，会调用此回调函数
        /// 参考<see cref="MessageContext"/>
        /// 添加此监听，在设定的开始时间开始监听，并且在设定的结束时间暂停监听
        /// 
        /// <para>使用规则：</para>
        /// <para>1. 仅能监听“允许消息通知”的好友/群聊,所以需要监听的好友/群聊不要设置为“消息免打扰”;</para>
        /// <para>2. 如果要避免太多消息影响，请将不监听的好友/群设置为“消息免打扰”，以提高监听性能;</para>
        /// <para>3. 此方法可以多次添加，第一次添加时会启动消息监听，第二次（类似的第三次等）添加效果等同<see cref="AddListeningFriend"/>方法</para>
        /// <para>4. 为了减少会话窗口的滚动，建议不要添加太多消息“置顶”，以提高监听效率.</para>
        /// <para>执行逻辑:</para>
        /// <para>1. 启动消息监听器时做做一次全量扫描，即：SDK会将会话列表整个循环一编，会自动点击并回调用户设定的方法，以防止遗漏消息</para>
        /// <para>2. 以后的监听过程会增量监听，以提高效率.</para>
        /// </summary>
        /// <param name="nickNames">好友昵称,可以是一个，也可以是多个好友/群聊 </param>
        /// <param name="callBack">回调函数,由用户提供,参数：消息上下文<see cref="MessageContext"/></param>
        /// <param name="startTime">开始时间</param>
        /// <param name="endTime">结束时间</param> 
        /// <param name="IsOpenMonitor">是否开启开放式监听，默认不开放(值为false）,如果开启开放式监听，前面的nickNames可以为空，所谓的开放式监听的含义是：无须固定好友/群监听，只要此好友/群没有设置“消息免打挠”就可以监听</param>
        /// <param name="userToken">取消令牌,请参考<see cref="CancellationToken"/>,可以自行取消消息监听</param>
        /// <param name="UIInvoker">UI的调度器，适用于把微信嵌入UI的场景使用，如：多微信切换Tab页等,SDK会给调用者注入一个微信名称</param>
        /// <param name="options">监听选项，具体请参见<see cref="MessageMonitorOptions"/></param>
        public async Task AddMessageListener(OneOf<string, List<string>, string[]> nickNames, Action<MessageContext> callBack, TimeOnly startTime, TimeOnly endTime, bool IsOpenMonitor = false, CancellationToken userToken = default, Action<string> UIInvoker = null, MessageMonitorOptions options = null)
        => await AddMessageListenerCore(nickNames, callBack, IsOpenMonitor, userToken, UIInvoker, new DateTimeRange()
        {
            IsCheckDate = true,
            TimeList = new List<TimeOnlyRange>(){
                new TimeOnlyRange()
                {
                    StarTime = startTime,
                    EndTime = endTime,
                }
            }
        }, options);
        /// <summary>
        /// 添加一天中多个时间段的消息监听，用户需要提供一个回调函数，当有消息时，会调用此回调函数
        /// 参考<see cref="MessageContext"/>
        /// 
        /// <para>使用规则：</para>
        /// <para>1. 仅能监听“允许消息通知”的好友/群聊,所以需要监听的好友/群聊不要设置为“消息免打扰”;</para>
        /// <para>2. 如果要避免太多消息影响，请将不监听的好友/群设置为“消息免打扰”，以提高监听性能;</para>
        /// <para>3. 此方法可以多次添加，第一次添加时会启动消息监听，第二次（类似的第三次等）添加效果等同<see cref="AddListeningFriend"/>方法</para>
        /// <para>4. 为了减少会话窗口的滚动，建议不要添加太多消息“置顶”，以提高监听效率.</para>
        /// <para>执行逻辑:</para>
        /// <para>1. 启动消息监听器时做做一次全量扫描，即：SDK会将会话列表整个循环一编，会自动点击并回调用户设定的方法，以防止遗漏消息</para>
        /// <para>2. 以后的监听过程会增量监听，以提高效率.</para>
        /// </summary>
        /// <param name="nickNames">好友昵称,可以是一个，也可以是多个好友/群聊 </param>
        /// <param name="callBack">回调函数,由用户提供,参数：消息上下文<see cref="MessageContext"/></param>
        /// <param name="range">一天中的多个时间段,如果设定多个时间段，监听器在这些时间段内开始/结束监听,时间段类请参考:<see cref="TimeOnlyRange"/>,另注意：可以跨天，如设置为:23:00 ~ 02:00</param>
        /// <param name="IsOpenMonitor">是否开启开放式监听，默认不开放(值为false）,如果开启开放式监听，前面的nickNames可以为空，所谓的开放式监听的含义是：无须固定好友/群监听，只要此好友/群没有设置“消息免打挠”就可以监听</param>
        /// <param name="userToken">取消令牌,请参考<see cref="CancellationToken"/>,可以自行取消消息监听</param>
        /// <param name="UIInvoker">UI的调度器，适用于把微信嵌入UI的场景使用，如：多微信切换Tab页等,SDK会给调用者注入一个微信名称</param>
        /// <param name="options">监听选项，具体请参见<see cref="MessageMonitorOptions"/></param>
        public async Task AddMessageListener(OneOf<string, List<string>, string[]> nickNames, Action<MessageContext> callBack, List<TimeOnlyRange> range, bool IsOpenMonitor = false, CancellationToken userToken = default, Action<string> UIInvoker = null, MessageMonitorOptions options = null)
        => await AddMessageListenerCore(nickNames, callBack, IsOpenMonitor, userToken, UIInvoker, new DateTimeRange()
        {
            IsCheckDate = true,
            TimeList = range,
        }, options);

        /// <summary>
        /// 暂停消息监听
        /// </summary>
        /// <returns></returns>
        public async Task PauseMessageListener()
        {
            Volatile.Write(ref _IsContinue, 0);
            await Task.CompletedTask;
        }
        /// <summary>
        /// 恢复消息监听
        /// </summary>
        /// <returns></returns>
        public async Task ResumeMessageListener()
        {
            Volatile.Write(ref _IsContinue, 1);
            await Task.CompletedTask;
        }

        /// <summary>
        /// 监听过程中动态添加待监听的好友/群聊
        /// </summary>
        /// <param name="who">好友/群聊名称</param>
        /// <returns></returns>
        public async Task AddListeningFriend(string who)
        {
            if (messageListnerStartedFlag != 1)
                throw new Exception("错误：请先启动消息监听器");
            if (!_MonitorList.Keys.Contains(who))
            {
                _MonitorList.TryAdd(who, false);
            }
            await Task.CompletedTask;
        }
        /// <summary>
        /// 监听过程中动态移除被监听的好友/群聊
        /// </summary>
        /// <param name="who">好友/群聊</param>
        /// <returns></returns>
        public async Task RemoveListeningFriend(string who)
        {
            if (messageListnerStartedFlag != 1)
                throw new Exception("错误：请先启动消息监听器");
            _MonitorList.TryRemove(who, out _);
            await Task.CompletedTask;
        }

        public async Task<SimpleMessageBubble> FetchLatestOriginalImage(string who)
        {
            var operationId = Guid.NewGuid().ToString("N");
            var stopwatch = Stopwatch.StartNew();
            ImageCaptureOperationLog.Write(operationId, "on_demand_started", stopwatch, details: new Dictionary<string, object>
            {
                ["requested_conversation"] = who ?? string.Empty,
                ["method"] = "clipboard_original_copy"
            });
            var listenerWasRunning = messageListnerStartedFlag == 1
                && Volatile.Read(ref _IsContinue) == 1;
            if (listenerWasRunning)
                Volatile.Write(ref _IsContinue, 0);
            try
            {
                ImageCaptureOperationLog.Write(operationId, "ui_action_queued", stopwatch, details: new Dictionary<string, object>
                {
                    ["requested_conversation"] = who ?? string.Empty
                });
                var result = await WeChatInvoker.Call(
                    __FetchLatestOriginalImageForConversationCore,
                    who,
                    operationId,
                    stopwatch
                ).WaitAsync(TimeSpan.FromSeconds(30));
                ImageCaptureOperationLog.Write(operationId, "on_demand_finished", stopwatch, result != null, new Dictionary<string, object>
                {
                    ["image_file"] = result?.ImageFile ?? string.Empty
                });
                return result;
            }
            catch (TimeoutException)
            {
                ImageCaptureOperationLog.Write(operationId, "on_demand_finished", stopwatch, false, new Dictionary<string, object>
                {
                    ["reason"] = "ui_action_timeout"
                });
                throw;
            }
            finally
            {
                if (listenerWasRunning)
                    Volatile.Write(ref _IsContinue, 1);
            }
        }

        private SimpleMessageBubble __FetchLatestOriginalImageForConversationCore(
            UIA3Automation automation,
            string who,
            string operationId,
            Stopwatch stopwatch)
        {
            ImageCaptureOperationLog.Write(operationId, "ui_action_started", stopwatch, details: new Dictionary<string, object>
            {
                ["requested_conversation"] = who ?? string.Empty
            });
            _Client.EnsureMainWindowVisible("fetch_latest_original_image");
            var currentTitle = _Client.ChatContent.ChatHeader.GetTitleCore(automation)?.Title?.Trim();
            var opened = string.IsNullOrWhiteSpace(who)
                || string.Equals(currentTitle, who.Trim(), StringComparison.Ordinal)
                || __OpenConversationCore(automation, who);
            ImageCaptureOperationLog.Write(operationId, "conversation_opened", stopwatch, opened, new Dictionary<string, object>
            {
                ["requested_conversation"] = who ?? string.Empty,
                ["previous_conversation"] = currentTitle ?? string.Empty
            });
            return opened
                ? __FetchLatestOriginalImageCore(automation, operationId, stopwatch)
                : null;
        }

        private SimpleMessageBubble __FetchLatestOriginalImageCore(UIA3Automation automation, string operationId, Stopwatch stopwatch)
        {
            _Client.EnsureMainWindowVisible("fetch_latest_original_image_core");
            var header = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
            var root = __FindMessageListRoot(automation);
            ImageCaptureOperationLog.Write(operationId, "message_list_resolved", stopwatch, root != null && header != null, new Dictionary<string, object>
            {
                ["actual_conversation"] = header?.Title ?? string.Empty,
                ["root_bounds"] = __DescribeBounds(root)
            });
            if (header == null || root == null)
                return null;

            Mouse.Position = root.BoundingRectangle.SafeRandomPoint();
            SupperMouseKey.Scroll(-30);
            RandomWait.Wait(250, 450);
            root = __FindMessageListRoot(automation);
            if (root == null)
                return null;

            for (var page = 0; page < 5; page++)
            {
                var imageItem = __FindLatestVisibleImageBubble(root);
                ImageCaptureOperationLog.Write(operationId, "image_page_scanned", stopwatch, imageItem != null, new Dictionary<string, object>
                {
                    ["page"] = page,
                    ["item_name"] = imageItem?.Name ?? string.Empty,
                    ["item_class"] = imageItem?.ClassName ?? string.Empty,
                    ["item_bounds"] = __DescribeBounds(imageItem)
                });
                if (imageItem != null)
                {
                    var message = new SimpleMessageBubble
                    {
                        Who = "对方",
                        Message = "[图片]",
                        SendDate = DateTime.Now,
                        MessageType = imageItem.Name.StartsWith("动画表情") ? MessageType.动画表情 : MessageType.图片
                    };
                    var ratio = DpiHelper.GetScaleForWindow(_Client.MainWindow.Properties.NativeWindowHandle);
                    __FetchImage(message, imageItem, new MessageMonitorOptions { FetchImage = true }, ratio, _Client.MainWindow, root, header, true);
                    if (!string.IsNullOrWhiteSpace(message.ImageFile) && File.Exists(message.ImageFile))
                        return message;
                }

                if (page < 4)
                {
                    MouseScrollHelper.UpStep(root.BoundingRectangle.SafeRandomPoint(), 3);
                    RandomWait.Wait(150, 350);
                    root = __FindMessageListRoot(automation);
                    if (root == null)
                        break;
                }
            }
            return null;
        }

        private bool __OpenConversationCore(UIA3Automation automation, string who)
        {
            if (string.IsNullOrWhiteSpace(who))
                return true;
            AutomationElement FindVisible() => _Client.Conversations.GetVisibleConversationElements(automation)
                .FirstOrDefault(candidate => string.Equals(
                    (candidate.Name ?? string.Empty).Split('\n')[0].Trim(),
                    who.Trim(),
                    StringComparison.Ordinal));
            var item = FindVisible();
            if (item == null)
            {
                if (!_Client.Conversations.LocateConversationCore(automation, who))
                    return false;
                item = FindVisible();
            }
            if (item == null || item.BoundingRectangle.IsEmpty || item.IsOffscreen)
                return false;
            for (var attempt = 0; attempt < 2; attempt++)
            {
                _Client.MainWindow.Focus();
                var point = item.BoundingRectangle.SafeRandomPoint();
                Mouse.Position = point;
                RandomWait.Wait(100, 250);
                Mouse.LeftClick();
                for (var check = 0; check < 30; check++)
                {
                    Thread.Sleep(200);
                    var header = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
                    var messageRoot = __FindMessageListRoot(automation);
                    if (messageRoot != null && string.Equals(
                        header?.Title?.Trim(),
                        who.Trim(),
                        StringComparison.Ordinal))
                        return true;
                }
                item = FindVisible();
                if (item == null || item.BoundingRectangle.IsEmpty || item.IsOffscreen)
                    break;
            }
            return false;
        }

        private async Task AddMessageListenerCore(OneOf<string, List<string>, string[]> nickNames, Action<MessageContext> callBack, bool IsOpenMonitor, CancellationToken userToken, Action<string> UIInvoker, DateTimeRange range, MessageMonitorOptions options)
        {
            Volatile.Write(ref messageCallback, callBack);
            Volatile.Write(ref _IsContinue, 1);
            if (Interlocked.CompareExchange(ref messageListnerStartedFlag, 1, 0) == 1)
            {
                List<string> list = nickNames.IsT0 ? new List<string>() { nickNames.AsT0 } : nickNames.IsT1 ? nickNames.AsT1 : nickNames.AsT2.ToList();
                foreach (var item in list)
                {
                    await AddListeningFriend(item);
                }
                return;
            }
            this.UIInvoker = UIInvoker;
            CancellationToken token;
            CancellationTokenSource linkedCts = default;
            if (userToken != default)
            {
                linkedCts = CancellationTokenSource.CreateLinkedTokenSource(messageGlobalCts.Token, userToken);
                token = linkedCts.Token;
            }
            else
            {
                token = messageGlobalCts.Token;
            }
            (nickNames.IsT0 ? new List<string>() { nickNames.AsT0 } : nickNames.IsT1 ? nickNames.AsT1.ToHashSet().ToList() : nickNames.AsT2.ToHashSet().ToList()).ForEach(u => _MonitorList.TryAdd(u, false));  //赋初始值.
            try
            {
                var startTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                if (options == null)
                    options = new MessageMonitorOptions();
                messageRunningTask = Task.Run(async () =>
                {
                    startTcs.TrySetResult(true);
                    using PeriodicTimer timer = new PeriodicTimer(TimeSpan.FromSeconds(WeAutomation.Config.MonitorMessageInterval));
                    Stopwatch riskWatch = new Stopwatch();
                    riskWatch.Start();
                    while (await timer.WaitForNextTickAsync(token).ConfigureAwait(false))
                    {
                        try
                        {
                            if (_IsContinue != 1)  //如果暂停了
                                continue;
                            if (range.IsCheckDate) //时间段检查
                            {
                                var flag = _CheckRuntime(range.TimeList);
                                if (!flag)
                                    continue;
                            }
                            if (options.IsRiskPrevention)
                            {
                                //如果启用了风控选项
                                await __RunPreventionRisk(options, riskWatch);
                            }
                            await noticeEvent.WaitAsync(token);
                            try
                            {
                                var currentCallback = Volatile.Read(ref messageCallback);
                                await WeChatInvoker.Call(AddMessageListenerAction, currentCallback, token, IsOpenMonitor, options);
                            }
                            finally
                            {
                                noticeEvent.Release();
                            }
                        }
                        catch (OperationCanceledException)
                        {
                            if (!startTcs.Task.IsCompleted)
                                startTcs.TrySetCanceled();
                        }
                        catch (Exception ex)
                        {
                            if (!startTcs.Task.IsCompleted)
                                startTcs.SetException(ex);
                            _Logger.Error($"监听消息发生错误：{ex.ToString()}");
                        }
                    }
                }, token);
                await startTcs.Task;
            }
            catch (OperationCanceledException)
            {
                //do nothing.
            }
            catch (Exception ex)
            {
                _Logger.Error($"监听消息发生错误：{ex.ToString()}");
            }
            finally
            {
                if (linkedCts != default)
                {
                    linkedCts?.Dispose();
                }
            }
        }
        /// <summary>
        /// 运行预防风控行为
        /// </summary>
        /// <param name="options">监听选项</param>
        /// <param name="riskWatch">7</param>
        /// <exception cref="NotImplementedException"></exception>
        private async Task __RunPreventionRisk(MessageMonitorOptions options, Stopwatch riskWatch)
        {
            try
            {
                var timespan = riskWatch.Elapsed;
                if (timespan.TotalMilliseconds >= pauseTime)  //条件满足
                {
                    System.Diagnostics.Debug.WriteLine($"===== 开始运行风控行为代码 ======");
                    try
                    {
                        await options?.RiskPreventionAction?.Invoke(this._Client);  //运行预防风控行为
                        riskWatch.Restart();  //重新计时
                    }
                    finally
                    {
                        await this._Client.SwitchNavigation(NavigationType.微信);
                    }
                    this.pauseTime = Random.Shared.Next(6 * 60 * 1_000, 10 * 60 * 1_000);   //重新计算下一次停顿时间.
                    //await WeChatInvoker.Call(__FixedSideEffect);  //暂时取消副作用，因为有些打开的子窗口监听是不需要关闭的.
                    System.Diagnostics.Debug.WriteLine($"===== 运行风控行为代码结束 ======");
                }
            }
            catch (Exception ex)
            {
                _Logger.Error("消息监听中运行预防风控行为出错:" + ex.ToString());
            }
        }

        /// <summary>
        /// 如果有副作用，如：打开的临时窗口等,则关闭他们
        /// </summary>
        /// <param name="automation"></param>
        private void __FixedSideEffect(UIA3Automation automation)
        {
            var desktop = automation.GetDesktop();
            var sideEffectWin = desktop.FindAllChildren(cf => (cf.ByControlType(ControlType.Window).Or(cf.ByControlType(ControlType.Pane))).And(cf.ByProcessId(this._Client.MainWindow.Properties.ProcessId)));
            var closeWin = sideEffectWin.Where(u => !u.Properties.RuntimeId.Value.SequenceEqual(this._Client.MainWindow.Properties.RuntimeId.Value)).ToList();
            foreach (var win in closeWin)
            {
                if (win is Window)
                {
                    win.AsWindow().Close();
                }
            }

        }

        private void AddMessageListenerAction(UIA3Automation automation, Action<MessageContext> callBack, CancellationToken token, bool IsOpenMonitor, MessageMonitorOptions options)
        {
            if (Volatile.Read(ref _IsContinue) != 1)
                return;
            var root = this._Client.Conversations.ConversationRoot;
            token.ThrowIfCancellationRequested();
            if (conversationStarted)
            {
                conversationStarted = false;
                _SwtichUI(token);
                // Fixed monitoring starts from the next unread change. The frontend can
                // watch the active conversation preview without taking over the mouse.
                if (!IsOpenMonitor)
                {
                    __InitializeConversationSnapshots(automation);
                    return;
                }
                // Preserve the SDK's original full initial scan for other modes.
                _TravelConversationList(automation, callBack, IsOpenMonitor, token, root, options);
                return;
            }
            this.totalNewMessage = _GetTotalMessage(token);
            if (this.totalNewMessage == 0 && !(options?.MonitorReadConversations == true && !IsOpenMonitor))
            {
                return;
            }
            //增量执行监听
            _SwtichUI(token);
            token.ThrowIfCancellationRequested();
            _MessageClickScheduling(automation, callBack, token, IsOpenMonitor, root, options);
        }
        /// <summary>
        /// 允许调用者做一些UI操作.
        /// </summary>
        /// <param name="token"></param>
        private void _SwtichUI(CancellationToken token)
        {
            if (this.UIInvoker != null)
            {
                token.ThrowIfCancellationRequested();
                WeAutomation.currentContext.Send((state) => this.UIInvoker.Invoke(state.ToString()), this._Client.NickName);
            }
        }

        private int _GetTotalMessage(CancellationToken token)
        {
            try
            {
                var root = this._Client.Navigation.rootElement;
                if (root == null)
                    return 0;
                var item = root.FindFirstChild(cf => cf.ByName("微信").And(cf.ByControlType(ControlType.Button)));
                if (item == null)
                    return 0;
                item.WaitUntilClickable();
                var title = item.Properties.FullDescription;
                if (string.IsNullOrEmpty(title) || title == "微信")
                    return 0;
                var pattern = @"^([\d]+)条新消息$";
                var match = Regex.Match(title, pattern);
                if (match.Success)
                {
                    return int.TryParse(match.Groups[1].Value, out var result) ? result : 0;
                }
                else
                {
                    return 0;
                }
            }
            catch (Exception ex)
            {
                _Logger.Error($"{nameof(MessageMonitor)} - {nameof(_GetTotalMessage)}发生错误:{ex.ToString()}");
                return 0;
            }
        }

        private void _TravelConversationList(UIA3Automation automation, Action<MessageContext> callBack, bool IsOpenMonitor, CancellationToken token, ListBox root, MessageMonitorOptions options)
        {
            if (Volatile.Read(ref _IsContinue) != 1)
                return;
            //当前的消息列表处理
            _ProcessVisibleConversation(automation, callBack, IsOpenMonitor, root.BoundingRectangle, token, options);
            //先往上翻到顶.
            this._Client.Conversations.UpCore(automation, (els, rootRect) =>
            {
                if (Volatile.Read(ref _IsContinue) != 1)
                    return false;
                _ProcessVisibleConversation(automation, callBack, IsOpenMonitor, rootRect, token, options);
                return true;
            });
            //再往下翻到底
            this._Client.Conversations.DownCore(automation, (el, rootRect) =>
            {
                if (Volatile.Read(ref _IsContinue) != 1)
                    return false;
                _ProcessVisibleConversation(automation, callBack, IsOpenMonitor, rootRect, token, options);
                return true;
            });
            //再往上翻到顶
            this._Client.Conversations.UpCore(automation, (els, rootRect) => Volatile.Read(ref _IsContinue) == 1);
        }

        private void _MessageClickScheduling(UIA3Automation automation, Action<MessageContext> callBack, CancellationToken token, bool IsOpenMonitor, ListBox root, MessageMonitorOptions options)
        {
            if (Volatile.Read(ref _IsContinue) != 1)
                return;
            if (!IsOpenMonitor)
            {
                var visibleConversations = _Client.Conversations.GetVisibleConversationsCore(automation);
                var elements = _Client.Conversations.GetVisibleConversationElements(automation);
                var hasVisibleTarget = visibleConversations.Any(item =>
                {
                    if (item.IsDoNotDisturb || !_MonitorList.ContainsKey(item.ConversationTitle))
                        return false;
                    if (item.NotReadNumbr > 0)
                        return true;
                    if (options?.MonitorReadConversations != true)
                        return false;
                    var element = elements.FirstOrDefault(candidate => candidate.GetName().Trim() == item.ConversationTitle);
                    return __ConversationChanged(item.ConversationTitle, element);
                });
                if (!hasVisibleTarget)
                    return;
            }
            this._Client.MainWindow.Focus();
            Mouse.Position = _Client.MainWindow.BoundingRectangle.Center();

            var index = 0;
            token.ThrowIfCancellationRequested();

            //当前的消息列表处理
            _ProcessVisibleConversation(automation, callBack, IsOpenMonitor, root.BoundingRectangle, token, options);
            if (_GetTotalMessage(token) == 0)
                return;

            //先往下滚动
            this._Client.Conversations.DownCore(automation, (el, rootRect) =>
            {
                if (Volatile.Read(ref _IsContinue) != 1)
                    return false;
                index++;
                _ProcessVisibleConversation(automation, callBack, IsOpenMonitor, rootRect, token, options);
                if (index <= WeAutomation.Config.MonitorMessageMaxDownInterval)
                {
                    return true;
                }
                return false;
            });
            //再往上翻到顶.
            this._Client.Conversations.UpCore(automation, (els, rootRect) =>
            {
                if (Volatile.Read(ref _IsContinue) != 1)
                    return false;
                _ProcessVisibleConversation(automation, callBack, IsOpenMonitor, rootRect, token, options);
                return true;
            });

            token.ThrowIfCancellationRequested();
        }

        //未设置“免打扰”,有未读消息数字
        private void _ProcessVisibleConversation(UIA3Automation automation, Action<MessageContext> callBack, bool IsOpenMonitor, Rectangle rootRect, CancellationToken token, MessageMonitorOptions options)
        {
            if (Volatile.Read(ref _IsContinue) != 1)
                return;
            List<SimpleConversation> visibleConvesationList = _Client.Conversations.GetVisibleConversationsCore(automation);
            RandomWait.Wait(100, 350);
            token.ThrowIfCancellationRequested();
            var elementList = _Client.Conversations.GetVisibleConversationElements(automation);  //取所有可见的会话元素
            var filterObjList = visibleConvesationList
                .Where(item =>
                {
                    if (item.IsDoNotDisturb)
                        return false;
                    if (item.NotReadNumbr > 0)
                        return true;
                    if (IsOpenMonitor || options?.MonitorReadConversations != true || !_MonitorList.ContainsKey(item.ConversationTitle))
                        return false;
                    var element = elementList.FirstOrDefault(candidate => candidate.GetName().Trim() == item.ConversationTitle);
                    return __ConversationChanged(item.ConversationTitle, element);
                })
                .ToList();
            List<AutomationElement> clickList = new List<AutomationElement>();  //待点击的列表
            var tmpList = filterObjList.Select(x => x.ConversationTitle);  //可点击的元素标题 列表
            foreach (var item in elementList)
            {
                string[] aryItems = item.Name.Split('\n');
                var name = aryItems[0].Trim();
                if (tmpList.Contains(name))
                {
                    clickList.Add(item);
                }
            }
            var willParseList = new List<string>();  //待获取元素并要求返回消息回调s
            if (IsOpenMonitor)
            {
                willParseList.AddRange(clickList.Select(u => u.GetName()));
            }
            else
            {
                var l1 = clickList.Select(u => u.GetName().Trim()).ToList(); //本次获取的对象。
                var l2 = this._MonitorList.Keys;  //所有监听对象
                willParseList.AddRange(l2.Intersect(l1));
            }


            // Fixed monitoring must not steal focus by clicking every unread
            // conversation. Only open configured targets; open monitoring
            // keeps the original all-unread behavior.
            var clickTargets = IsOpenMonitor
                ? clickList
                : clickList.Where(item => willParseList.Contains(item.GetName())).ToList();
            if (Volatile.Read(ref _IsContinue) != 1)
                return;
            foreach (var item in clickTargets)   //丢失了点击没有关系，下一轮又会点击，关键不能失去点击的能力.
            {
                token.ThrowIfCancellationRequested();
                if (item.BoundingRectangle.IsClickSafe(rootRect))
                {
                    var point = item.BoundingRectangle.SafeRandomPoint();
                    Mouse.Position = point;
                    RandomWait.Wait(50, 200);
                    SupperMouseKey.LeftClick();   //点击
                    RandomWait.Wait(200, 600);
                    var clickBackResult = _ProcessClickBack();  //点击了服务号需要进行返回
                    if (clickBackResult)
                        continue;
                    if (willParseList.Contains(item.GetName()))
                    {
                        var excludeResult = ExcludeUnParserItems(item);
                        if (excludeResult)
                            continue;
                        if (options?.FetchFile == true)
                            __TryCaptureVisibleFileWithoutMessageList(automation, callBack, options);
                        if (options?.FetchImage == true && __TryCaptureImageConversationPreview(automation, item, callBack, options))
                            continue;
                        var messageListRoot = __FindMessageListRoot(automation);
                        if (messageListRoot == null)
                        {
                            _Logger.Error($"抓取的名字为[{item.Name}]-未找到消息列表根元素，无法获取消息");
                            continue;
                        }
                        _ParserMessaageCore(automation, callBack, token, item, options, messageListRoot);
                    }
                }
            }
        }

        private bool ExcludeUnParserItems(AutomationElement item)
        {
            string[] names = new string[]
            {
              "文件传输助手",
              "公众号",
              "服务通知",
              "腾讯新闻",
              "元宝",
              "微信支付",
              "QQ邮箱提醒"
            };
            foreach (var name in names)
            {
                if (item.Name.Trim().StartsWith(name))
                    return true;
            }
            return false;
        }

        //item 为会话列表AutomationElement
        private int _GetCurrentNotReadNumbr(AutomationElement item, CancellationToken token)
        {
            var result = 0;
            var aryContent = item.Name.Split('\n', StringSplitOptions.RemoveEmptyEntries);
            foreach (var i in aryContent)
            {
                var pattern = @"\[(\d+)条\]";
                var match = Regex.Match(i, pattern);
                if (match.Success)
                {
                    result = int.TryParse(match.Groups[1].Value, out var r) ? r : 0;
                    break;
                }
            }
            return result;
        }

        private void _ParserMessaageCore(UIA3Automation automation, Action<MessageContext> callBack, CancellationToken token, AutomationElement clickConversionItem, MessageMonitorOptions options, AutomationElement messageListRoot)
        {
            token.ThrowIfCancellationRequested();
            var title = this._Client.ChatContent.ChatHeader.GetTitleCore(automation);
            if (title == null)
                return;
            if (!_FriendSession.Keys.Contains(title.Title))
            {
                _FriendSession.TryAdd(title.Title, false);
            }
            if (!_ConversationSnapshot.Keys.Contains(title.Title))
            {
                _ConversationSnapshot.TryAdd(title.Title, "");
            }
            if (options != null && options.FetchFriendInfo)
            {
                //先获取用户信息后再获取消息
                if (title.HeaderType == ChatType.好友)  //只有普通好友才有wxid.
                {
                    //session的首次取一下，不影响未来的100%准确性.
                    if (!_FriendSession[title.Title])
                    {
                        _FetchFriendInfo(automation, token, title);
                    }
                }
            }
            //获取数据核心方法
            var totalSessionNewMessages = new List<SimpleMessageBubble>();
            while (true)
            {
                List<SimpleMessageBubble> newMessages = _FetchMessageCore(automation, token, clickConversionItem, messageListRoot, title, options); //本次最新的消息列表
                if (newMessages.Count > 0)
                {
                    MessageCacheHelper.AddTodayMessageCaches(title.Title, newMessages);  //增加进缓存.
                    totalSessionNewMessages.AddRange(newMessages);

                    //日志
                    System.Diagnostics.Debug.WriteLine($"===== 来自 {title.Title} 的消息 ======");
                    foreach (var item in newMessages)
                    {
                        System.Diagnostics.Debug.WriteLine(item.ToString());
                    }
                    System.Diagnostics.Debug.WriteLine($"===== 结束输出 {title.Title} 的消息 ======");
                }
                //检查实时会话快照
                var oldSnapshot = _ConversationSnapshot[title.Title];
                var newSnapshot = clickConversionItem.Name;
                if (oldSnapshot.Equals(newSnapshot))
                {
                    break;
                }
                System.Diagnostics.Debug.WriteLineIf(!oldSnapshot.Equals(newSnapshot), $"newSnapshot与oldSnapshot不同，准备下一轮...");
                var pattern = @"\s*\[[\d]+条\]\s*";
                if (Regex.IsMatch(newSnapshot, pattern))
                {
                    clickConversionItem.Click();
                }
            }

            //回调用户提供的方法
            if (totalSessionNewMessages.Count() > 0)
            {
                _DoCallBackAction(title.Title, totalSessionNewMessages, callBack);
            }
        }

        private void _DoCallBackAction(string title, List<SimpleMessageBubble> newMessages, Action<MessageContext> callBack)
        {
            if (callBack == null)
                return;
            if (newMessages == null || newMessages.Count == 0)
                return;
            var historyList = MessageCacheHelper.GetTodayLastMessages(title, WeAutomation.Config.MaxHistoryMessageFetchNumber);
            MessageContext context = new MessageContext(newMessages, historyList, this._Client.ChatContent.Sender, this._Client, this._Client.Factory, this.serviceProvider, this._Client.NickName);
            callBack.Invoke(context);
        }



        private List<SimpleMessageBubble> _FetchMessageCore(UIA3Automation automation, CancellationToken token, AutomationElement clickConversionItem, AutomationElement messageListRoot, HeaderInfo title, MessageMonitorOptions options)
        {
            token.ThrowIfCancellationRequested();
            List<SimpleMessageBubble> result = new List<SimpleMessageBubble>();  //本次最新的消息列表
            var historyButton = this._Client.ChatContent.MessageBubbleList.HistoryButton;
            if (historyButton == null)
                return result;
            _StabilityClick(automation, token, clickConversionItem, messageListRoot, historyButton, title.Title);   //等候聊天稳定
            var desktop = automation.GetDesktop();
            var winResult = Retry.WhileNull(() => desktop.FindAllChildren(cf => cf.ByClassName("mmui::SearchMsgUniqueChatWindow").And(cf.ByControlType(ControlType.Window).And(cf.ByProcessId(_Client.MainWindow.Properties.ProcessId)))), timeout: TimeSpan.FromSeconds(2), interval: TimeSpan.FromMilliseconds(200));
            if (winResult.Success)
            {
                var subWins = winResult.Result;
                var subWin = subWins.FirstOrDefault(u =>
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
                    return result;
                this._Client.MoveWinToMainCenter(subWin);
                RandomWait.Wait(300, 1200);
                result = __FetchMessageFromHistory(subWin, token, title, options, automation);   //从历史窗口中获取数据
                this._Client.ChatContent.CloseSearchWindowCore(automation, title.Title); //关闭窗口
            }

            return result;
        }
        //消息稳定器 - 消息稳定后点击
        private void _StabilityClick(UIA3Automation automation, CancellationToken token, AutomationElement clickConversionItem, AutomationElement messageListRoot, Button historyButton, string who)
        {
            var index = 0;
            PreMove(historyButton);  //预先移动好
            var conversationRoot = this._Client.Conversations.ConversationRoot;
            AutomationElement item = null;
            while (index < WeAutomation.Config.MessageStabilityRetryNumber)
            {
                token.ThrowIfCancellationRequested();
                var items = conversationRoot.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem));
                item = items.Select(u => u.AsListBoxItem()).Where(u => u.IsSelected).FirstOrDefault();
                if (item == null || item.BoundingRectangle.Y + item.BoundingRectangle.Height > conversationRoot.BoundingRectangle.Y + conversationRoot.BoundingRectangle.Height)   //会话列表中被挤下去.
                {
                    var count = 0;
                    while (count < 3)
                    {
                        MouseScrollHelper.DownStep(conversationRoot.BoundingRectangle.Center().Confusion(10, 20), 2);
                        items = conversationRoot.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem));
                        item = items.Select(u => u.AsListBoxItem()).Where(u => u.IsSelected).FirstOrDefault();
                        if (item != null && item.BoundingRectangle.Y + item.BoundingRectangle.Height <= conversationRoot.BoundingRectangle.Y + conversationRoot.BoundingRectangle.Height)
                            break;
                        count++;
                    }
                    index = 0;
                    continue;
                }
                string[] aryCotent = item.Name.Trim().Split('\n');
                var match = Regex.Match(aryCotent[1], @"\[([\d]*)条\]");
                if (match.Success)
                {
                    item.Click();
                    index = 0;
                    if (item != null)
                    {
                        _ConversationSnapshot[who] = item.Name;
                    }
                    continue;
                }

                RandomWait.Wait(100, 600);
                PreMove(historyButton);  //预先移动好
                index++;
            }
            //保存会话最后的快照，如果执行结束后，检查与快照不一致，又重新一轮.
            var checkItemsRetry = Retry.WhileNull(() => conversationRoot.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem)), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (checkItemsRetry.Success)
            {
                var checkItems = checkItemsRetry.Result;
                item = checkItems.Select(u => u.AsListBoxItem()).Where(u => u.IsSelected).FirstOrDefault();
                if (item != null)
                {
                    _ConversationSnapshot[who] = item.Name;
                }
                SupperMouseKey.LeftClick();
                RandomWait.Wait(300, 900);
                SupperMouseKey.MoveTo(historyButton.BoundingRectangle.Center().Confusion(5, 5));
            }
        }

        private static void PreMove(Button historyButton)
        {
            Mouse.Position = historyButton.BoundingRectangle.Center().Confusion(5, 5);
            RandomWait.Wait(50, 300);
            SupperMouseKey.MoveTo(historyButton.BoundingRectangle.Center().Confusion(5, 5));
            RandomWait.Wait(100, 600);
        }

        private List<SimpleMessageBubble> __FetchMessageFromHistory(Window subWin, CancellationToken token, HeaderInfo title, MessageMonitorOptions options, UIA3Automation automation)
        {
            token.ThrowIfCancellationRequested();
            var ratio = DpiHelper.GetScaleForWindow(this._Client.MainWindow.Properties.NativeWindowHandle);   //ocr的比率.

            List<SimpleMessageBubble> result = new List<SimpleMessageBubble>();  //本次最新的消息列表
            List<SimpleMessageBubble> compareList = new List<SimpleMessageBubble>();
            compareList.AddRange(__GetTodayLastMessages(title.Title, 3));   //取历史记录的最后三条,要求比较时特征值与位置都要正确.

            var rootRetry = Retry.WhileNull(() => subWin.FindFirstByXPath("/Group/Group/Group/Group/List[@AutomationId='chat_log_message_list'][@ClassName='mmui::RecyclerListView'][@Name='聊天记录']"), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200)); //弹出窗口的消息根
            if (!rootRetry.Success)
                return result;
            var root = rootRetry.Result.AsListBox();   //历史消息的根ListBox

            var fetchCount = -1;
            if (!_FriendSession[title.Title])
            {
                //启动监听后第一次运行，不受特性匹配规则约速，并且取设定条目数消息.
                fetchCount = WeAutomation.Config.MessageFirstFetchNumber;
                _FriendSession[title.Title] = true;
            }

            var index = 0;
            var lastItems = new List<string>();        //内容+runtimeid
            var scrollPoint = root.BoundingRectangle.SafeRandomPoint();
            var maxFetchNumber = 0;
            while (index < 6)   //退出机理： 或者消息数不够，重试6次，或者特性匹配达到阈值.
            {
                token.ThrowIfCancellationRequested();
                var items = root.FindAllChildren(cf => cf.ByControlType(ControlType.ListItem));
                var thisPageList = new List<string>();
                foreach (var item in items)
                {
                    var height = 31 * ratio;  //31是100% dpi的高度.
                    if (item.BoundingRectangle.Y >= root.BoundingRectangle.Y && item.BoundingRectangle.Y + height <= root.BoundingRectangle.Y + root.BoundingRectangle.Height)
                    {
                        thisPageList.Add($"{item.Name}_{item.Properties.RuntimeId.ToUniqueString()}");
                    }
                }
                var exceptList = thisPageList.Except(lastItems).ToList();
                if (exceptList.Count == 0)
                {
                    index++;
                }
                else
                {
                    index = 0;
                    lastItems = thisPageList;
                    if (fetchCount == -1)
                    {
                        var exitFlag = __ProcessMessageWithOCR(exceptList, items, options, ratio, result, automation, root, subWin, compareList, token,title);
                        if (exitFlag)
                        {
                            result = result.Take(result.Count - compareList.Count).ToList();
                            break;
                        }
                    }
                    else
                    {
                        var exitFlag = __FirstFetchWithOCR(exceptList, items, options, ratio, result, automation, root, subWin, compareList, ref fetchCount, token,title);
                        if (exitFlag)
                            break;
                    }
                }
                MouseScrollHelper.DownStep(scrollPoint.Confusion(5, 10), 2);
                RandomWait.Wait(100, 400);
                maxFetchNumber++;
                if (maxFetchNumber > WeAutomation.Config.MaxHistoryFallbackThresholdNumber)
                {
                    break;
                }
            }
            result.Reverse();  //反转，因为从下往上读的聊天记录.
            return result;
        }

        private List<SimpleMessageBubble> __GetTodayLastMessages(string title, int lastCount)
        {
            var messages = MessageCacheHelper.GetTodayMessageCaches(title);
            if (messages.Count <= lastCount)
                return messages;
            return messages.GetRange(messages.Count - lastCount, lastCount);
        }


        //仅负责处理数据，并做退出判断
        private bool __ProcessMessageWithOCR(List<string> exceptList, AutomationElement[] root, MessageMonitorOptions options, decimal ratio, List<SimpleMessageBubble> result, UIA3Automation automation, AutomationElement messageListRoot, Window subWin, List<SimpleMessageBubble> compareList, CancellationToken token,HeaderInfo headerInfo)
        {
            var processItems = root.Where(r => exceptList.Contains($"{r.Name}_{r.Properties.RuntimeId.ToUniqueString()}"));

            foreach (var item in processItems)
            {
                token.ThrowIfCancellationRequested();
                SimpleMessageBubble message = new SimpleMessageBubble();
                if (item.ClassName.Equals("mmui::ChatItemView"))
                {
                    //系统消息
                    __ProcessSystemMessageWithOCR(item, message);
                }
                else
                {
                    //非系统消息.
                    __ProcessMessageWithOCRCore(item, options, ratio, message, automation, messageListRoot, subWin,headerInfo);
                }
                //自定义处理消息
                if (options != null && options.CustomProcessMessageAction != null)
                {
                    options.CustomProcessMessageAction.Invoke(item, message);
                }
                result.Add(message);
                if (__FeatureCompare(compareList, result))
                {
                    return true;
                }
            }
            return false;
        }

        private bool __FeatureCompare(List<SimpleMessageBubble> compareList, List<SimpleMessageBubble> result)
        {
            if (compareList == null || compareList.Count() == 0)
                return true;
            if (result.Count < compareList.Count)
                return false;
            //含不含有撤回消息
            var regretList = result.Where(r => r.MessageType.Equals(MessageType.其他) && r.Who == "系统" && r.Message.Contains("撤回了一条消")).ToList();
            if (regretList.Count == 0)
            {
                List<SimpleMessageBubble> tempList = result.Select(u => u.Clone()).ToList();
                tempList.Reverse();
                tempList = tempList.Take(compareList.Count()).ToList();
                if (tempList.SequenceEqual(compareList))
                    return true;
            }
            else
            {
                var cpList = compareList.Where(r => result.Contains(r)).ToList();
                if (cpList.Count > 0)
                    return true;
            }
            return false;
        }

        private bool __FirstFetchWithOCR(List<string> exceptList, AutomationElement[] root, MessageMonitorOptions options, decimal ratio, List<SimpleMessageBubble> result, UIA3Automation automation, AutomationElement messageListRoot, Window subWin, List<SimpleMessageBubble> compareList, ref int fetchCount, CancellationToken token,HeaderInfo headerInfo)
        {
            var processItems = root.Where(r => exceptList.Contains($"{r.Name}_{r.Properties.RuntimeId.ToUniqueString()}"));

            foreach (var item in processItems)
            {
                token.ThrowIfCancellationRequested();
                SimpleMessageBubble message = new SimpleMessageBubble();
                if (item.ClassName.Equals("mmui::ChatItemView"))
                {
                    //系统消息
                    __ProcessSystemMessageWithOCR(item, message);
                }
                else
                {
                    //非系统消息.
                    __ProcessMessageWithOCRCore(item, options, ratio, message, automation, messageListRoot, subWin,headerInfo);
                    fetchCount--;
                }
                result.Add(message);
                if (fetchCount == 0)
                    return true;
            }
            return false;
        }
        // 处理非系统消息
        private void __ProcessMessageWithOCRCore(AutomationElement item, MessageMonitorOptions options, decimal ratio, SimpleMessageBubble message, UIA3Automation automation, AutomationElement messageListRoot, Window subWin,HeaderInfo headerInfo)
        {
            var title = __OcrMessageTitle(item, ratio);
            message.Who = title;
            // 个人名片
            if (item.ClassName.Equals("mmui::ChatPersonalCardItemView"))
            {
                message.MessageType = MessageType.个人名片;
                (string content, DateTime date) resultSplit = __ParseHistoryItem(item.Name.Trim());
                message.Message = resultSplit.content;
                message.SendDate = resultSplit.date;
                return;
            }
            // 笔记
            if (item.ClassName.Equals("mmui::ChatNoteCardItemView"))
            {
                message.MessageType = MessageType.笔记;
                (string content, DateTime date) resultSplit = __ParseHistoryItem(item.Name.Trim().Substring(2));
                message.Message = resultSplit.content;
                message.SendDate = resultSplit.date;
                return;
            }
            //语音
            if (item.ClassName.Equals("mmui::ChatVoiceItemView"))
            {
                message.MessageType = MessageType.语音;
                var voiceResult = __ParseVoiceContent(item.Name.Trim());
                message.Message = __GetVoiceContent(voiceResult.voiceDelay, item, ratio, automation, subWin, options);
                message.SendDate = voiceResult.date;
                return;
            }

            if (item.ClassName.Equals("mmui::ChatBubbleItemView"))
            {
                //微信红包
                if (item.Name.EndsWith("微信红包"))
                {
                    message.Message = item.Name;
                    message.SendDate = default;
                    message.MessageType = MessageType.红包;
                    __ProcessRedEnvelope(item, messageListRoot, automation);
                    return;
                }
                //微信转账
                if (item.Name.EndsWith("微信转账"))
                {
                    message.Message = item.Name;
                    message.SendDate = default;
                    message.MessageType = MessageType.微信转账;
                    __ProcessTransfer(item, messageListRoot, automation);
                    return;
                }
                //文件
                if (item.Name.StartsWith("文件"))
                {
                    message.MessageType = MessageType.文件;
                }
                //聊天记录
                if (item.Name.StartsWith("聊天记录"))
                {
                    message.MessageType = MessageType.聊天记录;
                }
                //位置
                if (item.Name.StartsWith("位置"))
                {
                    message.MessageType = MessageType.位置;
                }
                //视频号
                if (item.Name.StartsWith("视频号") && !item.Name.Contains("直播中") && !item.Name.Contains("直播已结束"))
                {
                    message.MessageType = MessageType.视频号;
                }
                if (item.Name.StartsWith("视频号") && (item.Name.Contains("直播中") || item.Name.Contains("直播已结束")))
                {
                    message.MessageType = MessageType.视频号直播;
                }
                if (item.Name.StartsWith("小程序"))
                {
                    message.MessageType = MessageType.小程序;
                }
                if (item.Name.StartsWith("[链接]"))
                {
                    message.MessageType = MessageType.链接;
                }

                if (message.MessageType == MessageType.None)
                {
                    _Logger.Warn($"警告：类：{"mmui::ChatBubbleItemView"} - {item.Name} 没有被处理，当做 文本 来处理.");
                    message.MessageType = MessageType.文字;
                }

                (string content, DateTime date) resultSplit = __ParseHistoryItem(item.Name.Trim());
                message.SendDate = resultSplit.date;
                message.Message = resultSplit.content;
                if (message.MessageType == MessageType.文件)
                {
                    __FetchFile(message, options, item, automation, subWin, headerInfo?.Title ?? string.Empty);
                }
                return;
            }
            if (item.ClassName.Equals("mmui::ChatBubbleReferItemView"))
            {
                __PopulateReferenceMetadata(item, message);
                //图片
                if (item.Name.StartsWith("图片"))
                {
                    message.MessageType = MessageType.图片;
                    (string content, DateTime date) resultSplit = __ParseHistoryItem(item.Name.Trim());
                    message.SendDate = resultSplit.date;
                    message.Message = resultSplit.content;
                    __FetchImage(message, item, options, ratio, subWin, messageListRoot,headerInfo);
                    return;
                }
                //视频
                if (item.Name.StartsWith("视频"))
                {
                    message.MessageType = MessageType.视频;
                    (string content, DateTime date) resultSplit = __ParseHistoryItem(item.Name.Trim());
                    message.SendDate = resultSplit.date;
                    message.Message = resultSplit.content;
                    return;
                }
                //动画表情
                if (item.Name.StartsWith("动画表情"))
                {
                    message.MessageType = MessageType.动画表情;
                    (string content, DateTime date) resultSplit = __ParseHistoryItem(item.Name.Trim());
                    message.SendDate = resultSplit.date;
                    message.Message = resultSplit.content;
                    __FetchImage(message, item, options, ratio, subWin, messageListRoot, headerInfo);
                    return;
                }
                _Logger.Warn($"警告：{item.Name} 没有被处理，当做 文本 来处理.");
                //如果没有截取到
                if (message.MessageType == MessageType.None)
                    message.MessageType = MessageType.文字;

                (string content, DateTime date) antother = __ParseHistoryItem(item.Name.Trim());
                message.SendDate = antother.date;
                message.Message = antother.content;
                return;
            }

            message.MessageType = MessageType.文字;
            (string content, DateTime date) split = __ParseHistoryItem(item.Name.Trim());
            message.SendDate = split.date;
            message.Message = split.content;
        }

        private static void __PopulateReferenceMetadata(AutomationElement item, SimpleMessageBubble message)
        {
            message.IsReference = true;
            var candidates = new List<string>();
            if (!string.IsNullOrWhiteSpace(item?.Name))
                candidates.Add(item.Name);
            try
            {
                candidates.AddRange(item
                    .FindAllDescendants()
                    .Select(element => element?.Name)
                    .Where(value => !string.IsNullOrWhiteSpace(value)));
            }
            catch
            {
                // Quote children can disappear while WeChat refreshes the message list.
            }

            foreach (var candidate in candidates.AsEnumerable().Reverse())
            {
                var lines = Regex.Split(candidate ?? string.Empty, "[\\r\\n]+")
                    .Select(value => value.Trim())
                    .Where(value => !string.IsNullOrWhiteSpace(value))
                    .Reverse();
                foreach (var line in lines)
                {
                    var match = Regex.Match(
                        line,
                        @"^(?:引用\s*)?(?<who>[^:：\r\n]{1,64})\s*[:：]\s*(?<message>.+)$");
                    if (!match.Success)
                        continue;
                    var who = match.Groups["who"].Value.Trim();
                    var referencedMessage = match.Groups["message"].Value.Trim();
                    if (string.IsNullOrWhiteSpace(who)
                        || string.IsNullOrWhiteSpace(referencedMessage)
                        || Regex.IsMatch(who, @"^(?:今天|昨天|前天|上午|下午|晚上|\d{1,2})$"))
                        continue;
                    message.ReferencedWho = who;
                    message.ReferencedMessage = referencedMessage;
                    return;
                }
            }
        }

        private void __FetchImage(SimpleMessageBubble message, AutomationElement item, MessageMonitorOptions options, decimal ratio, Window subWin, AutomationElement root,HeaderInfo headerInfo, bool ignoreHistory = false)
        {
            var operationId = Guid.NewGuid().ToString("N");
            var stopwatch = Stopwatch.StartNew();
            ImageCaptureOperationLog.Write(operationId, "started", stopwatch, details: new Dictionary<string, object>
            {
                ["conversation"] = headerInfo?.Title ?? string.Empty,
                ["message_type"] = message?.MessageType.ToString() ?? string.Empty,
                ["item_class"] = item?.ClassName ?? string.Empty,
                ["item_name"] = item?.Name ?? string.Empty,
                ["item_bounds"] = __DescribeBounds(item)
            });
            if (options == null)
            {
                ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object> { ["reason"] = "options_null" });
                return;
            }
            if (!options.FetchImage)
            {
                ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object> { ["reason"] = "fetch_image_disabled" });
                return;
            }
            if (!ignoreHistory && excludeHistory(message,headerInfo))
            {
                ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object> { ["reason"] = "history_message" });
                return;
            }
            if (item == null || root == null)
            {
                ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object> { ["reason"] = "missing_element" });
                return;
            }
            var needHeight = (int)(49 * ratio);
            if (item.BoundingRectangle.Y + needHeight > root.BoundingRectangle.Y + root.BoundingRectangle.Height)
            {
                //如果不在点击区域，则滚动一下.
                MouseScrollHelper.DownStep(root.BoundingRectangle.SafeRandomPoint(), 2);
                var items = root.FindAllChildren();
                item = items.Where(u => u.Properties.RuntimeId.Value.SequenceEqual(item.Properties.RuntimeId.Value)).FirstOrDefault();
                ImageCaptureOperationLog.Write(operationId, "scrolled", stopwatch, details: new Dictionary<string, object>
                {
                    ["item_found"] = item != null,
                    ["item_bounds"] = __DescribeBounds(item)
                });
                if (item == null)
                {
                    ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object> { ["reason"] = "element_lost_after_scroll" });
                    return;
                }
            }

            var clickPoints = __ImageCopyClickPoints(message, item, __FindImageContentElement(item));
            for (var attempt = 0; attempt < clickPoints.Count; attempt++)
            {
                var point = clickPoints[attempt];
                var targetHandle = (IntPtr)subWin.Properties.NativeWindowHandle.Value;
                WinApi.ActivateWindow(targetHandle);
                subWin.Focus();
                RandomWait.Wait(40, 80);
                var foregroundHandle = WinApi.GetForegroundWindowHandle();
                ImageCaptureOperationLog.Write(operationId, "clipboard_original_copy_started", stopwatch, details: new Dictionary<string, object>
                {
                    ["attempt"] = attempt + 1,
                    ["click_x"] = point.X,
                    ["click_y"] = point.Y,
                    ["preferred_side"] = __IsIncomingMessage(message) ? "left" : "right",
                    ["target_hwnd"] = targetHandle.ToInt64(),
                    ["foreground_hwnd"] = foregroundHandle.ToInt64(),
                    ["foreground_pid"] = WinApi.GetWindowProcessId(foregroundHandle),
                    ["foreground_matches_target"] = foregroundHandle == targetHandle
                });
                if (foregroundHandle != targetHandle)
                    continue;
                if (!__TryClearClipboard(TimeSpan.FromSeconds(1)))
                    continue;
                SupperMouseKey.MoveTo(point);
                RandomWait.Wait(30, 60);
                SupperMouseKey.RightClick();
                var menuItem = __FindDesktopMenuItem("复制", subWin, TimeSpan.FromSeconds(2));
                ImageCaptureOperationLog.Write(operationId, "copy_menu_resolved", stopwatch, menuItem != null, new Dictionary<string, object>
                {
                    ["attempt"] = attempt + 1,
                    ["menu_name"] = menuItem?.Name ?? string.Empty,
                    ["menu_class"] = menuItem?.ClassName ?? string.Empty,
                    ["menu_process_id"] = menuItem?.Properties.ProcessId.ValueOrDefault ?? 0,
                    ["menu_bounds"] = __DescribeBounds(menuItem),
                    ["menu_items"] = __DescribeMenuItems(subWin)
                });
                if (menuItem == null)
                {
                    SupperMouseKey.TypeSimultaneously(VirtualKeyShort.ESC);
                    continue;
                }
                menuItem.AsMenuItem().Click();
                RandomWait.Wait(40, 80);
                using var bitmap = __TryReadClipboardImage(TimeSpan.FromSeconds(2.5));
                ImageCaptureOperationLog.Write(operationId, "clipboard_image_read", stopwatch, bitmap != null, new Dictionary<string, object>
                {
                    ["attempt"] = attempt + 1,
                    ["formats"] = __DescribeClipboardFormats(),
                    ["width"] = bitmap?.Width ?? 0,
                    ["height"] = bitmap?.Height ?? 0
                });
                if (bitmap == null)
                    continue;
                __SaveFetchedImage(message, bitmap);
                ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, true, new Dictionary<string, object>
                {
                    ["method"] = "clipboard_original_copy",
                    ["attempt"] = attempt + 1,
                    ["width"] = bitmap.Width,
                    ["height"] = bitmap.Height,
                    ["image_file"] = message.ImageFile
                });
                return;
            }
            ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object> { ["reason"] = "copy_menu_or_clipboard_unavailable" });
        }

        private static List<Point> __ImageCopyClickPoints(SimpleMessageBubble message, AutomationElement item, AutomationElement imageContent)
        {
            var points = new List<Point>();
            if (imageContent != null && !imageContent.BoundingRectangle.IsEmpty)
                points.Add(imageContent.BoundingRectangle.Center());
            var bounds = item.BoundingRectangle;
            var sideOffset = Math.Clamp((int)Math.Round(bounds.Width * 0.27), 64, 110);
            var y = (int)Math.Round((double)bounds.Y + (double)bounds.Height / 2.0);
            var left = new Point((int)Math.Round((double)bounds.X) + sideOffset, y);
            var right = new Point((int)Math.Round((double)bounds.Right) - sideOffset, y);
            if (__IsIncomingMessage(message))
            {
                points.Add(left);
                points.Add(right);
            }
            else
            {
                points.Add(right);
                points.Add(left);
            }
            return points.Distinct().ToList();
        }

        private static bool __IsIncomingMessage(SimpleMessageBubble message)
            => !string.Equals(message?.Who?.Trim(), "我", StringComparison.Ordinal);

        private static AutomationElement __FindDesktopMenuItem(string name, Window owner, TimeSpan timeout)
        {
            var stopwatch = Stopwatch.StartNew();
            while (stopwatch.Elapsed < timeout)
            {
                try
                {
                    var result = owner.FindFirstDescendant(cf =>
                        cf.ByControlType(ControlType.MenuItem).And(cf.ByName(name)));
                    result ??= owner.Automation.GetDesktop().FindFirstDescendant(cf =>
                        cf.ByControlType(ControlType.MenuItem).And(cf.ByName(name)));
                    if (result != null && !result.BoundingRectangle.IsEmpty)
                        return result;
                }
                catch (COMException)
                {
                    // The transient XMenu window can disappear while UIA is walking it.
                }
                Thread.Sleep(80);
            }
            return null;
        }

        private static string __DescribeClipboardFormats()
            => ClipboardHelper.DescribeFormats();

        private static string __DescribeMenuItems(Window owner)
        {
            try
            {
                var menu = owner.FindFirstDescendant(cf =>
                    cf.ByControlType(ControlType.Window)
                        .And(cf.ByClassName("mmui::XMenu")));
                if (menu == null)
                    return string.Empty;
                return string.Join(",", menu.FindAllDescendants(cf => cf.ByControlType(ControlType.MenuItem))
                    .Select(item => item.Name)
                    .Where(name => !string.IsNullOrWhiteSpace(name)));
            }
            catch (COMException)
            {
                return "menu_tree_unavailable";
            }
        }

        private static bool __TryClearClipboard(TimeSpan timeout)
            => ClipboardHelper.TryClear(timeout);

        private static Bitmap __TryReadClipboardImage(TimeSpan timeout)
            => ClipboardHelper.TryGetImage(timeout);

        private bool __TryCaptureImageConversationPreview(
            UIA3Automation automation,
            AutomationElement conversationItem,
            Action<MessageContext> callBack,
            MessageMonitorOptions options)
        {
            var conversation = _Client.Conversations.GetConversationItemFromName(conversationItem.Name);
            var preview = conversation.ConversationContent?.Trim() ?? string.Empty;
            if (!Regex.IsMatch(preview, @"(?:^|[:：]\s*)\[?图片\]?$", RegexOptions.IgnoreCase))
                return false;

            var header = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
            if (header == null || string.IsNullOrWhiteSpace(header.Title))
                return false;

            var operationId = Guid.NewGuid().ToString("N");
            var stopwatch = Stopwatch.StartNew();
            ImageCaptureOperationLog.Write(operationId, "started", stopwatch, details: new Dictionary<string, object>
            {
                ["conversation"] = header.Title,
                ["method"] = "original_image_only",
                ["preview"] = preview
            });
            try
            {
                _Client.MainWindow.Focus();
                RandomWait.Wait(100, 250);
                var messageRoot = __FindMessageListRoot(automation);
                var imageItem = __FindLatestVisibleImageBubble(messageRoot);
                if (imageItem != null)
                {
                    var sender = "对方";
                    var senderMatch = Regex.Match(preview, @"^(?<sender>[^:：\r\n]{1,40})[:：]\s*\[?图片\]?$", RegexOptions.IgnoreCase);
                    if (senderMatch.Success)
                        sender = senderMatch.Groups["sender"].Value.Trim();
                    var message = new SimpleMessageBubble
                    {
                        Who = sender,
                        Message = "[图片]",
                        SendDate = DateTime.Now,
                        MessageType = imageItem.Name.StartsWith("动画表情") ? MessageType.动画表情 : MessageType.图片
                    };
                    var ratio = DpiHelper.GetScaleForWindow(this._Client.MainWindow.Properties.NativeWindowHandle);
                    __FetchImage(message, imageItem, options, ratio, _Client.MainWindow, messageRoot, header);
                    if (!string.IsNullOrWhiteSpace(message.ImageFile) && File.Exists(message.ImageFile))
                    {
                        var messages = new List<SimpleMessageBubble> { message };
                        MessageCacheHelper.AddTodayMessageCaches(header.Title, messages);
                        _ConversationSnapshot[header.Title] = conversationItem.Name;
                        _DoCallBackAction(header.Title, messages, callBack);
                        ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, true, new Dictionary<string, object>
                        {
                            ["method"] = "latest_image_bubble",
                            ["item_class"] = imageItem.ClassName ?? string.Empty,
                            ["item_bounds"] = __DescribeBounds(imageItem),
                            ["image_file"] = message.ImageFile
                        });
                        return true;
                    }
                }
                ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object>
                {
                    ["method"] = "original_image_only",
                    ["reason"] = "image_bubble_or_clipboard_unavailable"
                });
                return false;
            }
            catch (Exception exception)
            {
                _Logger.Warn("复制当前聊天原图失败。", exception);
                ImageCaptureOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object>
                {
                    ["method"] = "original_image_only",
                    ["error_type"] = exception.GetType().FullName,
                    ["error_message"] = exception.Message
                });
                return false;
            }
        }

        private AutomationElement __FindMessageListRoot(UIA3Automation automation)
        {
            AutomationElement root = this._Client.ChatContent.MessageBubbleList.MessageRoot;
            if (root != null)
                return root;

            var desktop = automation.GetDesktop();
            root = desktop.FindFirstDescendant(cf => cf.ByAutomationId("chat_message_list"));
            root ??= desktop.FindFirstDescendant(cf =>
                cf.ByClassName("mmui::RecyclerListView")
                    .And(cf.ByName("消息")));
            root ??= desktop.FindFirstDescendant(cf =>
                cf.ByControlType(ControlType.List).And(cf.ByName("消息")));
            if (root != null)
            {
                _Logger.Info(
                    $"消息列表已通过桌面树定位：Class={root.ClassName}, ControlType={root.ControlType}, " +
                    $"AutomationId={root.AutomationId}, ProcessId={root.Properties.ProcessId.ValueOrDefault}, " +
                    $"Bounds={root.BoundingRectangle}");
            }
            return root;
        }

        private static AutomationElement __FindLatestVisibleImageBubble(AutomationElement root)
        {
            if (root == null)
                return null;
            return root.FindAllDescendants(cf => cf.ByControlType(ControlType.ListItem))
                .Where(candidate =>
                    candidate.ClassName == "mmui::ChatBubbleReferItemView"
                    && (candidate.Name?.StartsWith("图片") == true
                        || candidate.Name?.StartsWith("动画表情") == true)
                    && candidate.BoundingRectangle.Y >= root.BoundingRectangle.Y
                    && candidate.BoundingRectangle.Y < root.BoundingRectangle.Bottom)
                .OrderByDescending(candidate => candidate.BoundingRectangle.Y)
                .FirstOrDefault();
        }

        private static AutomationElement __FindImageContentElement(AutomationElement item)
        {
            if (item == null || item.BoundingRectangle.IsEmpty)
                return null;
            var itemBounds = item.BoundingRectangle;
            return item.FindAllDescendants()
                .Where(candidate =>
                {
                    var bounds = candidate.BoundingRectangle;
                    var className = candidate.ClassName ?? string.Empty;
                    return !bounds.IsEmpty
                        && bounds.Width >= 48
                        && bounds.Height >= 48
                        && bounds.Width < itemBounds.Width * 0.8
                        && bounds.Height <= itemBounds.Height
                        && !className.Contains("ContactHeadView", StringComparison.OrdinalIgnoreCase)
                        && !className.Contains("Avatar", StringComparison.OrdinalIgnoreCase);
                })
                .OrderByDescending(candidate => candidate.BoundingRectangle.Width * candidate.BoundingRectangle.Height)
                .FirstOrDefault();
        }

        private void __InitializeConversationSnapshots(UIA3Automation automation)
        {
            foreach (var item in _Client.Conversations.GetVisibleConversationElements(automation))
            {
                var title = item.GetName().Trim();
                if (_MonitorList.ContainsKey(title))
                    _ConversationSnapshot[title] = item.Name;
            }
        }

        internal void RecordOutgoingMessageCore(UIA3Automation automation, string title, string message)
        {
            if (string.IsNullOrWhiteSpace(title))
                return;
            _OutgoingPreviewEchoes[title] = (message?.Trim() ?? string.Empty, DateTime.UtcNow.AddSeconds(8));
            // WeChat updates the conversation preview just after Enter. Refresh the
            // monitor snapshot while the UI automation lock is still held so the
            // outgoing preview cannot be mistaken for a new inbound message.
            Thread.Sleep(80);
            var item = _Client.Conversations
                .GetVisibleConversationElements(automation)
                .FirstOrDefault(candidate => candidate.GetName().Trim() == title);
            if (item != null)
                _ConversationSnapshot[title] = item.Name;
        }

        private bool __ConversationChanged(string title, AutomationElement item)
        {
            if (item == null)
                return false;
            if (!_ConversationSnapshot.TryGetValue(title, out var previous))
            {
                _ConversationSnapshot[title] = item.Name;
                return false;
            }
            if (string.Equals(previous, item.Name, StringComparison.Ordinal))
                return false;
            if (_OutgoingPreviewEchoes.TryGetValue(title, out var outgoing))
            {
                if (outgoing.ExpiresAt < DateTime.UtcNow)
                {
                    _OutgoingPreviewEchoes.TryRemove(title, out _);
                }
                else
                {
                    var preview = _Client.Conversations
                        .GetConversationItemFromName(item.Name)
                        .ConversationContent?.Trim() ?? string.Empty;
                    if (__OutgoingPreviewMatches(preview, outgoing.Message))
                    {
                        _ConversationSnapshot[title] = item.Name;
                        _OutgoingPreviewEchoes.TryRemove(title, out _);
                        return false;
                    }
                }
            }
            return true;
        }

        private static bool __OutgoingPreviewMatches(string preview, string message)
        {
            if (string.IsNullOrWhiteSpace(preview) || string.IsNullOrWhiteSpace(message))
                return false;
            if (string.Equals(preview, message, StringComparison.Ordinal))
                return true;
            if (preview.EndsWith($": {message}", StringComparison.Ordinal)
                || preview.EndsWith($"：{message}", StringComparison.Ordinal))
                return true;
            if (!preview.EndsWith("…", StringComparison.Ordinal))
                return false;
            var prefix = preview[..^1].TrimEnd();
            var separator = Math.Max(prefix.LastIndexOf(": ", StringComparison.Ordinal), prefix.LastIndexOf('：'));
            if (separator >= 0)
                prefix = prefix[(separator + (prefix[separator] == '：' ? 1 : 2))..];
            return prefix.Length >= 12 && message.StartsWith(prefix, StringComparison.Ordinal);
        }

        private static void __SaveFetchedImage(SimpleMessageBubble message, Bitmap bitmap)
        {
            var directory = Path.Combine(AppContext.BaseDirectory, "ImageCaches");
            Directory.CreateDirectory(directory);
            var path = Path.Combine(directory, $"original-{Guid.NewGuid():N}.png");
            bitmap.Save(path, ImageFormat.Png);
            message.Image = new Bitmap(bitmap);
            message.ImageFile = path;
        }

        private static string __DescribeBounds(AutomationElement element)
        {
            if (element == null)
                return string.Empty;
            var bounds = element.BoundingRectangle;
            return $"{bounds.X},{bounds.Y},{bounds.Width},{bounds.Height}";
        }

        private bool excludeHistory(SimpleMessageBubble message,HeaderInfo headerInfo)
        {
            //从历史消息取15条，如果匹对得上，则返回真，不做图象获取.
            var compareHistoryList = MessageCacheHelper.GetTodayLastMessages(headerInfo.Title, 15);
            if (compareHistoryList.Contains(message))
                return true;
            return false;
        }

        // WeChat performs voice transcription when its own automatic transcription
        // setting is enabled. MyBot only reads the resulting UIA Name and never
        // clicks the voice bubble or opens its context menu.
        private string __GetVoiceContent(int voiceDelay, AutomationElement item, decimal ratio, UIA3Automation automation, AutomationElement subWin, MessageMonitorOptions options)
        {
            if (options == null || !options.FetchVoiceChat)
                return "语音";
            return ReadVisibleVoiceContent(item, "语音");
        }

        internal string ReadVisibleVoiceContent(AutomationElement item, string fallback = "语音")
        {
            var text = __ExtractVoiceTranscription(item?.Name?.Trim() ?? string.Empty);
            return string.IsNullOrWhiteSpace(text) ? fallback : text;
        }

        private void __FetchFile(
            SimpleMessageBubble message,
            MessageMonitorOptions options,
            AutomationElement item = null,
            UIA3Automation automation = null,
            Window subWin = null,
            string conversation = "")
        {
            if (options == null || !options.FetchFile)
                return;
            var lines = Regex.Split(message.Message ?? string.Empty, "[\\r\\n]+")
                .Select(value => value.Trim())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .ToList();
            var fileName = lines
                .Select(value => Regex.Replace(
                    Regex.Replace(value, "^(?:\\[?文件\\]?|文件[:：])\\s*", string.Empty).Trim(),
                    "\\s+[\\d.]+\\s*(?:B|KB|MB|GB|字节)\\s*$",
                    string.Empty,
                    RegexOptions.IgnoreCase).Trim())
                .FirstOrDefault(value => !string.IsNullOrWhiteSpace(value)
                    && value != "文件"
                    && !Regex.IsMatch(value, "^[\\d.]+\\s*(?:B|KB|MB|GB|字节)$", RegexOptions.IgnoreCase));
            if (string.IsNullOrWhiteSpace(fileName))
                return;
            fileName = Path.GetFileName(fileName.Replace('/', Path.DirectorySeparatorChar));
            message.FileName = fileName;

            if (!string.IsNullOrWhiteSpace(options.FileSaveDirectory))
            {
                var privatePath = __PrivateAttachmentPath(options.FileSaveDirectory, conversation, fileName);
                if (File.Exists(privatePath) && new FileInfo(privatePath).Length > 0)
                {
                    message.FilePath = privatePath;
                    return;
                }
                if (item != null && automation != null && subWin != null
                    && __TrySaveFileAs(item, automation, subWin, privatePath, conversation, fileName))
                {
                    message.FilePath = privatePath;
                    return;
                }
            }

            var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            var root = Path.Combine(home, "xwechat_files");
            if (!Directory.Exists(root))
                return;
            var months = new[] { DateTime.Now, DateTime.Now.AddMonths(-1) }
                .Select(value => value.ToString("yyyy-MM"))
                .Distinct();
            var matches = new List<FileInfo>();
            foreach (var accountRoot in Directory.EnumerateDirectories(root))
            {
                foreach (var month in months)
                {
                    var directory = Path.Combine(accountRoot, "msg", "file", month);
                    if (!Directory.Exists(directory))
                        continue;
                    try
                    {
                        matches.AddRange(Directory.EnumerateFiles(directory, fileName, SearchOption.AllDirectories)
                            .Select(path => new FileInfo(path)));
                    }
                    catch (IOException) { }
                    catch (UnauthorizedAccessException) { }
                }
            }
            var selected = matches
                .Where(value => value.Exists && value.Length > 0)
                .OrderByDescending(value => value.LastWriteTimeUtc)
                .FirstOrDefault();
            if (selected != null)
                message.FilePath = selected.FullName;
        }

        private bool __TryCaptureVisibleFileWithoutMessageList(
            UIA3Automation automation,
            Action<MessageContext> callBack,
            MessageMonitorOptions options)
        {
            var header = _Client.ChatContent.ChatHeader.GetTitleCore(automation);
            if (header == null || string.IsNullOrWhiteSpace(header.Title))
                return false;
            AutomationElement item;
            try
            {
                item = _Client.MainWindow
                    .FindAllDescendants(cf => cf.ByClassName("mmui::ChatBubbleItemView"))
                    .Where(value => value != null && Regex.IsMatch(value.Name ?? string.Empty, "^文件(?:[：:\\s]|$)"))
                    .Where(value => !value.BoundingRectangle.IsEmpty)
                    .OrderByDescending(value => value.BoundingRectangle.Bottom)
                    .FirstOrDefault();
            }
            catch (Exception exception)
            {
                _Logger.Warn("扫描当前会话文件气泡失败。", exception);
                return false;
            }
            if (item == null)
                return false;
            var message = new SimpleMessageBubble
            {
                Who = "对方",
                Message = item.Name.Trim(),
                SendDate = default,
                MessageType = MessageType.文件
            };
            if (MessageCacheHelper.GetTodayLastMessages(header.Title, 30).Contains(message))
                return false;

            __FetchFile(message, options, item, automation, _Client.MainWindow, header.Title);
            if (string.IsNullOrWhiteSpace(message.FileName))
                return false;
            var messages = new List<SimpleMessageBubble> { message };
            MessageCacheHelper.AddTodayMessageCaches(header.Title, messages);
            _DoCallBackAction(header.Title, messages, callBack);
            return true;
        }

        private bool __TrySaveFileAs(
            AutomationElement item,
            UIA3Automation automation,
            Window subWin,
            string destination,
            string conversation,
            string fileName)
        {
            var operationId = Guid.NewGuid().ToString("N");
            var stopwatch = Stopwatch.StartNew();
            AttachmentOperationLog.Write(operationId, "started", stopwatch, details: new Dictionary<string, object>
            {
                ["conversation"] = conversation,
                ["file_name"] = fileName,
                ["destination"] = destination,
                ["method"] = "wechat_save_as"
            });
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                SupperMouseKey.MoveTo(item.BoundingRectangle.Center().Confusion(8, 4));
                RandomWait.Wait(100, 250);
                SupperMouseKey.RightClick();
                var popup = Retry.WhileNull(
                    () => automation.GetDesktop().FindFirstDescendant(cf =>
                        cf.ByControlType(ControlType.Window)
                            .And(cf.ByClassName("mmui::XMenu"))
                            .And(cf.ByName("Weixin"))),
                    TimeSpan.FromSeconds(2),
                    TimeSpan.FromMilliseconds(120));
                if (!popup.Success)
                    throw new InvalidOperationException("未找到文件右键菜单");
                var saveAs = popup.Result.FindAllDescendants(cf => cf.ByControlType(ControlType.MenuItem))
                    .FirstOrDefault(value => (value.Name ?? string.Empty).StartsWith("另存为", StringComparison.Ordinal));
                if (saveAs == null)
                    throw new InvalidOperationException("右键菜单中没有另存为");
                saveAs.Click();

                var dialog = Retry.WhileNull(
                    () => automation.GetDesktop().FindFirstDescendant(cf =>
                        cf.ByControlType(ControlType.Window)
                            .And(cf.ByClassName("#32770"))
                            .And(cf.ByName("另存为..."))),
                    TimeSpan.FromSeconds(4),
                    TimeSpan.FromMilliseconds(150));
                if (!dialog.Success)
                    throw new InvalidOperationException("未找到另存为对话框");
                var fileNameEdit = dialog.Result.FindFirstDescendant(cf =>
                    cf.ByControlType(ControlType.Edit).And(cf.ByAutomationId("1001")));
                if (fileNameEdit == null)
                    throw new InvalidOperationException("未找到另存为文件名输入框");
                fileNameEdit.Focus();
                Keyboard.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_A);
                ClipboardHelper.SetText(destination);
                Keyboard.TypeSimultaneously(VirtualKeyShort.CONTROL, VirtualKeyShort.KEY_V);
                var save = dialog.Result.FindFirstDescendant(cf =>
                    cf.ByControlType(ControlType.Button).And(cf.ByAutomationId("1")));
                if (save == null)
                    throw new InvalidOperationException("未找到保存按钮");
                save.Click();
                var completed = Retry.WhileFalse(
                    () => File.Exists(destination) && new FileInfo(destination).Length > 0,
                    TimeSpan.FromSeconds(15),
                    TimeSpan.FromMilliseconds(200));
                if (!completed.Success)
                    throw new IOException("微信另存为后未生成文件");
                AttachmentOperationLog.Write(operationId, "finished", stopwatch, true, new Dictionary<string, object>
                {
                    ["file_name"] = fileName,
                    ["destination"] = destination,
                    ["bytes"] = new FileInfo(destination).Length
                });
                return true;
            }
            catch (Exception exception)
            {
                _Logger.Warn($"另存为微信文件失败：{fileName}", exception);
                AttachmentOperationLog.Write(operationId, "finished", stopwatch, false, new Dictionary<string, object>
                {
                    ["file_name"] = fileName,
                    ["destination"] = destination,
                    ["error_type"] = exception.GetType().FullName,
                    ["error_message"] = exception.Message
                });
                var saveDialog = automation.GetDesktop().FindFirstDescendant(cf =>
                    cf.ByControlType(ControlType.Window)
                        .And(cf.ByClassName("#32770"))
                        .And(cf.ByName("另存为...")));
                saveDialog?.AsWindow().Close();
                _Client.EnsureMainWindowVisible("file_save_failed");
                return false;
            }
        }

        private static string __PrivateAttachmentPath(string root, string conversation, string fileName)
        {
            var fullRoot = Path.GetFullPath(root);
            var digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(conversation ?? string.Empty)))
                .ToLowerInvariant()[..16];
            var directory = Path.GetFullPath(Path.Combine(fullRoot, digest, "inbox"));
            if (!directory.StartsWith(fullRoot.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("附件保存目录越界");
            return Path.Combine(directory, Path.GetFileName(fileName));
        }

        private static string __ExtractVoiceTranscription(string itemName)
        {
            if (string.IsNullOrWhiteSpace(itemName))
                return string.Empty;
            var match = Regex.Match(itemName.Trim(), @"^语音\d+[\""”″]?秒(?<text>[\s\S]*)$");
            if (!match.Success)
                return string.Empty;
            var text = Regex.Replace(
                match.Groups["text"].Value,
                @"\s+\d{4}年\d{1,2}月\d{1,2}日\s+\d{2}:\d{2}$",
                string.Empty);
            var ignored = new HashSet<string>(StringComparer.Ordinal)
            {
                "未播放", "已播放", "转文字", "语音转文字", "正在转文字", "转换中"
            };
            var lines = Regex.Split(text, "[\\r\\n]+")
                .Select(value => value.Trim())
                .Where(value => !string.IsNullOrWhiteSpace(value) && !ignored.Contains(value))
                .ToArray();
            return string.Join("\n", lines).Trim();
        }

        private (int voiceDelay, DateTime date) __ParseVoiceContent(string text)
        {
            var match = Regex.Match(
                        text,
                        @"^语音(?<seconds>\d+)""秒\s+(?<time>\d{4}年\d{1,2}月\d{1,2}日\s+\d{2}:\d{2})$");

            if (match.Success)
            {
                int seconds = int.Parse(match.Groups["seconds"].Value);
                string time = match.Groups["time"].Value;
                return (seconds, DateTime.TryParseExact(time, "yyyy年M月d日 HH:mm", CultureInfo.InvariantCulture, DateTimeStyles.None, out var date) ? date : default);
            }
            return (0, default);
        }

        private (string content, DateTime date) __ParseHistoryItem(string text)
        {
            var match = Regex.Match(
                text,
                @"^(?<content>[\s\S]*?)\s*(?<time>\d{4}年\d{1,2}月\d{1,2}日\s+\d{2}:\d{2})$");

            if (match.Success)
            {
                string content = match.Groups["content"].Value.Trim();
                string time = match.Groups["time"].Value;
                return (content, DateTime.TryParseExact(time, "yyyy年M月d日 HH:mm", CultureInfo.InvariantCulture, DateTimeStyles.None, out var date) ? date : default);
            }
            return ("", default);
        }

        private string __OcrMessageTitle(AutomationElement item, decimal ratio)
        {
            //先得到rio
            using var oriMat = this._Client.OcrEngee.GetMatFromElement(item);
            int top = (int)(11 * ratio);   //计算-算上dpi的顶端
            var left = (int)(65 * ratio);  //计算-算上dpi的左边
            var height = (int)((33 - 11) * ratio);  //计算上dpi的高度
            var width = (int)(oriMat.Width - left - 150 * ratio);   //150为计算dpi，并且考虑日期的长度
            using var mat = new Mat(oriMat, new Rectangle(left, top, width, height));
            //放大2倍，增加识别准确性.
            var bigMat = new Mat();
            CvInvoke.Resize(mat, bigMat, Size.Empty, 2, 2, Emgu.CV.CvEnum.Inter.Cubic);
            //识别
            var result = this._Client.OcrEngee.Detect(bigMat.ToBitmap(), 0, bigMat.Width > bigMat.Height ? bigMat.Width : bigMat.Height, 0.3f, 0.3f, 1.8f, false, false, isTest: false);

            return result.StrRes.Trim();
        }

        // 处理系统消息
        private void __ProcessSystemMessageWithOCR(AutomationElement item, SimpleMessageBubble message)
        {
            //其他消息，如：系统消息,时间,收取红包,拒绝红包,拍一拍,加入群聊,移出群聊,撤回了一条消息,其他消息,
            message.Who = "系统";
            message.Message = item.Name.Trim();
            message.SendDate = default;
            message.MessageType = MessageType.其他;
        }


        private void __ProcessRedEnvelope(AutomationElement item, AutomationElement messageListRoot, UIA3Automation automation)
        {
            int[] runtimeId = item.Properties.RuntimeId.Value;
        }

        private void __ProcessTransfer(AutomationElement item, AutomationElement messageListRoot, UIA3Automation automation)
        {

        }

        //仅用于测试.
        public async Task FetchFriendInfo(string who)
        {
            await this._Client.SearchFriend(who);
            RandomWait.Wait(500, 1200);
            var chatInfo = await this._Client.ChatContent.ChatHeader.GetTitle();
            await WeChatInvoker.Call(_FetchFriendInfo, CancellationToken.None, chatInfo);
        }
        /// <summary>
        /// 点击聊天窗口右上角的“聊天信息”按钮，进入好友信息界面获取好友信息，获取完后会自动关闭好友信息界面
        /// </summary>
        /// <param name="automation"></param>
        /// <param name="token"></param>
        /// <param name="headerInfo"></param>
        internal void _FetchFriendInfo(UIA3Automation automation, CancellationToken token, HeaderInfo headerInfo)
        {
            //首先判断在缓存中有没有此用户
            var result = this._Client.GetFriendFromCache(headerInfo.Title);
            token.ThrowIfCancellationRequested();
            if (result != null)
            {
                return;
            }
            //如果没有此用户，则取用户wxid
            var path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Button[@Name='聊天信息'][@AutomationId='content_view.top_content_view.title_h_view.right_v_view.right_content_h_view.right_content_v_view.right_ui_.more_button']";
            var buttonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (!buttonRetry.Success)
                return;
            var button = buttonRetry.Result; //点击侧边栏按钮.
            var point = button.BoundingRectangle.Center();
            var point1 = point.Confusion(5, 3);
            Mouse.Position = point1;
            RandomWait.Wait(100, 300);
            point1 = point.Confusion(5, 3);
            SupperMouseKey.MoveTo(point1);
            RandomWait.Wait(200, 800);
            SupperMouseKey.LeftClick();
            //点击后找到右边侧图标
            path = "/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group[2]/Group[2]/Group/Group/Group/Group[1]/Button[1]";
            buttonRetry = Retry.WhileNull(() => this._Client.MainWindow.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (!buttonRetry.Success)
                return;
            token.ThrowIfCancellationRequested();
            button = buttonRetry.Result;
            button = button.FindFirstChild(cf => cf.ByControlType(ControlType.Button).And(cf.ByClassName("mmui::ContactHeadView")));
            point = button.BoundingRectangle.Center();
            point1 = point.Confusion(5, 5);
            Mouse.Position = point1;
            RandomWait.Wait(100, 300);
            point1 = point.Confusion(5, 3);
            SupperMouseKey.MoveTo(point1);
            RandomWait.Wait(200, 800);
            SupperMouseKey.LeftClick();
            token.ThrowIfCancellationRequested();

            //获取信息
            FriendInfo friendInfo = GetFriendInfoCore(automation);
            if (friendInfo != null)
            {
                this._Client.AddOrUpdateFriendFromCache(friendInfo);
            }
            token.ThrowIfCancellationRequested();
            this._Client.ChatContent.Sender.FocuseSenderCore(automation);  //获取完信息后把焦点切回消息输入框
            RandomWait.Wait(100, 300);

            //再次检查一下是否关闭侧边栏，如果没有关闭，则关闭一下，避免影响下一次获取信息
            var addButtonRetry = Retry.WhileNotNull(() => this._Client.MainWindow.FindFirstByXPath("/Group/Custom/Group/Group/Group/Custom/Custom/Custom/Group/Custom/Custom/Group/Group/Group/Group/Group/Group/Group/Button[@Name='添加'][@AutomationId='single_chat_member_add'][@ClassName='mmui::ChatMemberActionView']"), TimeSpan.FromSeconds(1), TimeSpan.FromMilliseconds(200));
            if (!addButtonRetry.Result)
            {
                this._Client.ChatContent.Sender.FocuseSenderCore(automation);  //获取完信息后把焦点切回消息输入框
                RandomWait.Wait(100, 300);
            }
        }

        /// <summary>
        /// 单纯获取好友信息
        /// </summary>
        /// <param name="automation"></param>
        /// <returns></returns>
        internal FriendInfo GetFriendInfoCore(UIA3Automation automation)
        {
            FriendInfo friendInfo = new FriendInfo();
            var winRetry = Retry.WhileNull(() => automation.GetDesktop().FindFirstChild(cf => cf.ByName("Weixin").And(cf.ByClassName("mmui::ProfileUniquePop").And(cf.ByProcessId(this._Client.MainWindow.Properties.ProcessId)))), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (!winRetry.Success)
                return null;
            var win = winRetry.Result.AsWindow();
            var path = "/Group/Group/Group/Group/Group/Group/Group/Text[@Name='微信号：'][@AutomationId='right_v_view.user_info_center_view.basic_line_view.basic_line.key_text']";
            var textRetry = Retry.WhileNull(() => win.FindFirstByXPath(path), TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(200));
            if (!textRetry.Success)
                return null;
            //微信号
            var text = textRetry.Result.GetSibling(1);
            friendInfo.WxId = text.Name;
            //名称、昵称、备注
            path = "/Group/Group/Group/Group/Group/Group/Text[@AutomationId='right_v_view.nickname_button_view.display_name_text']";
            text = win.FindFirstByXPath(path);
            friendInfo.NickName = text.Name;
            friendInfo.MemoName = text.Name;
            //昵称
            path = "/Group/Group/Group/Group/Group/Group/Group/Text[@Name='昵称：'][@AutomationId='right_v_view.user_info_center_view.basic_line_view.basic_line.key_text']";
            text = win.FindFirstByXPath(path)?.GetSibling(1);
            if (text != null)
            {
                friendInfo.NickName = text.Name;
            }
            //地区
            path = "/Group/Group/Group/Group/Group/Group/Group/Text[@Name='地区：'][@AutomationId='right_v_view.user_info_center_view.basic_line_view.basic_line.key_text']";
            text = win.FindFirstByXPath(path)?.GetSibling(1);
            if (text != null)
            {
                friendInfo.Area = text.Name;
            }
            //共同群聊
            path = "/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Button/Group/Group/Text[@AutomationId='content_v_view.ProfileResizeVBoxView.detail_scroll_view.gradient_mask_stacked_view.default_scroll_area.qt_scrollarea_viewport.detail_content_host.detail_center_v_view.detail_derived_content_view.section_shell.more_line_v_view.chatroom_intersection.value_normal_view.content_view.value_reader_view.value_reader_'][@ClassName='mmui::ProfileTextView']";
            text = win.FindFirstByXPath(path);
            if (text != null)
            {
                friendInfo.SameGroupNumber = text.Name;
            }
            //签名
            path = "/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Button/Group/Group/Text[@AutomationId='content_v_view.ProfileResizeVBoxView.detail_scroll_view.gradient_mask_stacked_view.default_scroll_area.qt_scrollarea_viewport.detail_content_host.detail_center_v_view.detail_derived_content_view.section_shell.more_line_v_view.sign.value_normal_view.content_view.value_reader_view.value_reader_'][@ClassName='mmui::ProfileTextView']";
            text = win.FindFirstByXPath(path);
            if (text != null)
            {
                friendInfo.Signature = text.Name;
            }
            //来源与添加时间略掉，因为没啥意义.
            //标签
            path = "/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Group/Button/Group/Group/Text[@AutomationId='content_v_view.ProfileResizeVBoxView.detail_scroll_view.gradient_mask_stacked_view.default_scroll_area.qt_scrollarea_viewport.detail_content_host.detail_center_v_view.detail_derived_content_view.section_shell.main_line_v_view.tag_line.value_normal_view.content_view.value_reader_view.value_reader_'][@ClassName='mmui::ProfileTextView']";
            text = win.FindFirstByXPath(path);
            if (text != null)
            {
                string[] tags = text.Name.Split(',', StringSplitOptions.RemoveEmptyEntries);
                friendInfo.Lable = tags.ToList();
            }
            path = "/Group/Group/Group/Group/Group/Button[@AutomationId='head_image_v_view.head_view_'][@ClassName='mmui::ContactHeadView']";
            var button = win.FindFirstByXPath(path);
            if (button != null)
            {
                path = Path.Combine(AppContext.BaseDirectory, "Avator", $"{friendInfo.WxId}.png");
                button.CaptureToFile(path);
                friendInfo.AvatarPath = path;
            }
            win?.Close();
            return friendInfo;
        }
        private bool _ProcessClickBack()
        {
            var backButtonRetry = Retry.WhileNull(() => _Client.MainWindow.FindFirstDescendant(cf => cf.ByName("返回").And(cf.ByAutomationId("button")).And(cf.ByClassName("mmui::ChatBackwardView")).And(cf.ByControlType(ControlType.Button).And(cf.ByProcessId(this._Client.MainWindow.Properties.ProcessId)))), timeout: TimeSpan.FromSeconds(0.5), interval: TimeSpan.FromMilliseconds(100));
            if (backButtonRetry.Success)
            {
                var button = backButtonRetry.Result;
                button.WaitUntilClickable();
                button.Click();
                RandomWait.Wait(300, 600);
                return true;
            }
            return false;
        }

        #endregion

        private string __GetConversionShortTitle(string fullTitle)
        {
            string[] aryTitles = fullTitle.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            string title = string.Empty;
            foreach (var item in aryTitles)
            {
                string pattern = @"^(?:[01]\d|2[0-3]):[0-5]\d$";
                if (Regex.IsMatch(item, pattern))
                {
                    continue;
                }
                title += item;
            }
            return title;
        }
        private bool _CheckRuntime(List<TimeOnlyRange> timeList)
        {
            var now = TimeOnly.FromDateTime(DateTime.Now);

            foreach (var time in timeList)
            {
                if (_IsInRange(now, time.StarTime, time.EndTime))
                    return true;
            }

            return false;
        }

        private bool _IsInRange(TimeOnly now, TimeOnly start, TimeOnly end)
        {
            // 普通区间
            if (start <= end)
            {
                return now >= start && now <= end;
            }

            // 跨天区间
            return now >= start || now <= end;
        }

        #region 释放器
        ~MessageMonitor()
        {
            Dispose(false);
        }
        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        protected virtual void Dispose(bool disposing)
        {
            if (Interlocked.CompareExchange(ref _disposed, 1, 0) == 1)
                return;
            if (disposing)
            {
                messageGlobalCts?.Cancel();
                if (messageRunningTask != null)
                {
                    if (!messageRunningTask.IsCompleted)
                    {
                        try
                        {
                            messageRunningTask.Wait(TimeSpan.FromSeconds(3));
                        }
                        catch (AggregateException) { }
                        catch (Exception) { }
                    }
                }
                foreach (var subThread in _SystemMonitors)
                {
                    try
                    {
                        subThread.Join(TimeSpan.FromSeconds(3));
                    }
                    catch (AggregateException) { }
                    catch (Exception) { }
                }

                messageGlobalCts?.Dispose();
                messageRunningTask?.Dispose();
            }
        }
        #endregion
    }
}
