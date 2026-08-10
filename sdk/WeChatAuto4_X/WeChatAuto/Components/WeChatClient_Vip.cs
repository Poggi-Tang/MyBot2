using FlaUI.Core.Definitions;
using FlaUI.Core.AutomationElements;
using System.Collections.Generic;
using WeAutoCommon.Utils;
using System;
using WeAutoCommon.Models;
using OneOf;
using WeChatAuto.Utils;
using System.Threading;
using Microsoft.Extensions.DependencyInjection;
using WeChatAuto.Services;
using FlaUI.Core.Tools;
using WeAutoCommon.Exceptions;
using FlaUI.UIA3;
using WeAutoCommon.Simulator;
using System.Threading.Tasks;
using FlaUI.Core.Capturing;
using WeAutoCommon.Enums;
using WeChatAuto.Extentions;
using WeChatAuto.Models;
using System.Configuration;
using System.Drawing;
using System.Linq;
using System.IO;
using WeChatAuto.Options;
using RapidOCRLib;
using System.Threading.Channels;


namespace WeChatAuto.Components
{
    /// <summary>
    /// 微信客户端,vip使用的库
    /// 适用于单个微信客户端的自动化操作
    /// </summary>
    public partial class WeChatClient : IDisposable
    {
        #region  监听管理
        /// <summary>
        /// <para>添加系统消息监听，以实现如： 检测到群主邀请好友后发送欢迎消息等功能</para>
        /// <para>注意：仅适用于群聊，不适用个人,个人请使用下面的开放式/固定式监听，另外，不支持注册监听后再新增待监听的群聊</para>
        /// 多线程监听变化，但是操作等，还得在微信单线程中执行.
        /// </summary>
        /// <param name="nickNames">群聊昵称，可以多个</param>
        /// <param name="callBack">回调函数,由用户提供,参数：消息上下文<see cref="SystemMessageContext"/></param>
        /// <param name="userToken">取消令牌,请参考<see cref="CancellationToken"/>,可以自行取消消息监听</param>
        public async Task AddGroupSystemMessageListener(OneOf<string, List<string>, string[]> nickNames, Func<SystemMessageContext, Task> callBack, CancellationToken userToken = default) => await this.MessageMonitor.AddGroupSystemMessageListener(nickNames, callBack, userToken);
        /// <summary>
        /// 添加消息监听，用户需要提供一个回调函数，当有消息时，会调用此回调函数
        /// 参考<see cref="MessageContext"/>
        /// 消息监听最主要以事件触发的方式，当消息过来的时候，监听才会运行.
        /// <para>使用规则：</para>
        /// <para>1. 仅能监听“允许消息通知”的好友/群聊,所以需要监听的好友/群聊不要设置为“消息免打扰”;</para>
        /// <para>2. 如果要避免太多消息影响，请将不监听的好友/群设置为“消息免打扰”，以提高监听性能;</para>
        /// <para>3. 此方法可以多次添加，第一次添加时会启动消息监听，第二次（类似的:第三次等）添加效果等同<see cref="AddListeningFriend"/>方法</para>
        /// <para>4. 为了减少会话窗口的滚动，建议不要添加太多消息“置顶”，以提高监听效率.</para>
        /// <para>执行逻辑:</para>
        /// <para>1. 启动消息监听器时，SDK会将会话列表整个循环一遍，会自动点击并回调用户设定的方法，以防止遗漏消息</para>
        /// <para>2. 以后的监听过程会增量监听，以提高效率.</para>
        /// </summary>
        /// <param name="nickNames">好友昵称,可以是一个，也可以是多个好友/群聊 </param>
        /// <param name="callBack">回调函数,由用户提供,参数：消息上下文<see cref="MessageContext"/></param>
        /// <param name="IsOpenMonitor">是否开启开放式监听，默认不开放(值为false）,如果开启开放式监听，前面的nickNames可以为空，所谓的开放式监听的含义是：无须固定好友/群监听，只要此好友/群没有设置“消息免打挠”就可以监听</param>
        /// <param name="userToken">取消令牌,请参考<see cref="CancellationToken"/>,可以自行取消消息监听</param>
        /// <param name="UIInvoker">UI的调度器，适用于把微信嵌入UI的场景使用，如：多微信切换Tab页等,SDK会给调用者注入一个微信名称</param>
        /// <param name="options">监听选项，具体请参见<see cref="MessageMonitorOptions"/></param>
        public async Task AddMessageListener(OneOf<string, List<string>, string[]> nickNames, Action<MessageContext> callBack, bool IsOpenMonitor = false, CancellationToken userToken = default, Action<string> UIInvoker = null, MessageMonitorOptions options = null)
            => await this.MessageMonitor.AddMessageListener(nickNames, callBack, IsOpenMonitor, userToken, UIInvoker, options);
        /// <summary>
        /// 添加一个从什么时候开始，什么时候结束的消息监听，用户需要提供一个回调函数，当有消息时，会调用此回调函数
        /// 参考<see cref="MessageContext"/>
        /// 适用于固定时间自动化的场景
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
          => await this.MessageMonitor.AddMessageListener(nickNames, callBack, startTime, endTime, IsOpenMonitor, userToken, UIInvoker, options);
        /// <summary>
        /// 添加一天中多个时间段的消息监听，用户需要提供一个回调函数，当有消息时，会调用此回调函数
        /// 参考<see cref="MessageContext"/>
        /// 适用于一天内多次固定时间进行自动化操作的场景
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
        /// <param name="range">一天中的多个时间段,如果设定多个时间段，监听器在这些时间段内开始/结束监听,时间段类请参考:<see cref="TimeOnlyRange"/>,另注意：可以跨天，如设置为:23:00 ~ 02:00,则表示当天23:00至明天02:00</param>
        /// <param name="IsOpenMonitor">是否开启开放式监听，默认不开放(值为false）,如果开启开放式监听，前面的nickNames可以为空，所谓的开放式监听的含义是：无须固定好友/群监听，只要此好友/群没有设置“消息免打挠”就可以监听</param>
        /// <param name="userToken">取消令牌,请参考<see cref="CancellationToken"/>,可以自行取消消息监听</param>
        /// <param name="UIInvoker">UI的调度器，适用于把微信嵌入UI的场景使用，如：多微信切换Tab页等,SDK会给调用者注入一个微信名称</param>
        /// <param name="options">监听选项，具体请参见<see cref="MessageMonitorOptions"/></param>
        public async Task AddMessageListener(OneOf<string, List<string>, string[]> nickNames, Action<MessageContext> callBack, List<TimeOnlyRange> range, bool IsOpenMonitor = false, CancellationToken userToken = default, Action<string> UIInvoker = null, MessageMonitorOptions options = null)
            => await this.MessageMonitor.AddMessageListener(nickNames, callBack, range, IsOpenMonitor, userToken, UIInvoker, options);
        /// <summary>
        /// 暂停消息监听
        /// </summary>
        /// <returns></returns>
        public async Task PauseMessageListener() => await this.MessageMonitor.PauseMessageListener();
        /// <summary>
        /// 恢复消息监听
        /// </summary>
        /// <returns></returns>
        public async Task ResumeMessageListener() => await this.MessageMonitor.ResumeMessageListener();
        /// <summary>
        /// 监听过程中添加好友
        /// </summary>
        /// <param name="who">好友名称</param>
        /// <returns></returns>
        public async Task AddListeningFriend(string who) => await this.MessageMonitor.AddListeningFriend(who);
        /// <summary>
        /// 监听过程中移除被监听中的好友/群聊
        /// </summary>
        /// <param name="who">好友/群聊名称</param>
        /// <returns></returns>
        public async Task RemoveListeningFriend(string who) => await this.MessageMonitor.RemoveListeningFriend(who);

        /// <summary>
        /// <para>新好友添加监听</para>
        /// <para>实现的功能</para>
        /// <para>1. 自动通过好友申请</para>
        /// <para>2. 根据设定的关键词过滤好友申请的打招呼文本，只有包含关键词的打招呼内容才会被通过</para>
        /// <para>3. 通过好友申请时，可以设置后缀,以区分不同类型的好友,方便后续的自动化实现</para>
        /// <para>4. 通过好友申请时，可以设置特定的微信标签，以方便后续的自动化与好友管理</para>
        /// <para>5. 也可以通过好友申请后，删除申请记录</para>
        /// </summary>
        /// <param name="options">配置选项，请参考<see cref="FriendRequestAutoAcceptOptions"/>类</param>
        /// <param name="token">取消令版</param>
        /// <param name="UIInvoker">UI线程调度器,适用于把微信嵌入UI的场景使用，如：多微信切换Tab页等,SDK会给调用者注入一个微信名称</param>
        /// <returns></returns>
        public async Task AddFriendRequestAutoAcceptListener(FriendRequestAutoAcceptOptions options, CancellationToken token = default, Action<string> UIInvoker = null)
          => await this.NewFriendMonitor.AddFriendRequestAutoAcceptListener(options, token, UIInvoker);
        /// <summary>
        /// 暂停好友申请监听
        /// </summary>
        /// <returns></returns>
        public async Task PauseNewFriendListener() => await this.NewFriendMonitor.PauseNewFriendListener();
        /// <summary>
        /// 恢复好友申请监听
        /// </summary>
        /// <returns></returns>
        public async Task ResumeNewFriendListener() => await this.NewFriendMonitor.ResumeNewFriendListener();
        #endregion

        #region 朋友圈管理
        /// <summary>
        /// 打开朋友圈,如果未打开，则打开朋友圈，如果已经打开了，则窗口提前到顶端
        /// </summary>
        /// <returns>返回朋友圈窗口对象|</returns>
        public async Task<Window> OpenMoments() => await this.Moments.OpenMoments();
        /// <summary>
        /// 关闭朋友圈
        /// </summary>
        /// <returns></returns>
        public async Task CloseMoments() => await this.Moments.CloseMoments();
        /// <summary>
        /// 发送朋友圈
        /// </summary>
        /// <param name="imageFiles">图片列表，可以一个，也可以多个,如果是多个文件，要求在同一个目录中</param>
        /// <param name="content">朋友圈内容</param>
        /// <param name="options">发送选项，请参考<see cref="MomentsOptions"/></param>
        /// <returns>成功还是失败</returns>
        public async Task<bool> AddMoments(List<string> imageFiles, string content, MomentsOptions options = null)
          => await this.Moments.AddMoments(imageFiles, content, options);
        /// <summary>
        /// 移除自己发送的朋友圈
        /// </summary>
        /// <param name="content">朋友圈文字内容</param>
        /// <returns>是否成功删除</returns>
        public async Task<bool> RemoveMoments(string content)
          => await this.Moments.RemoveMoments(content);
        #endregion
        /// <summary>
        /// 转发多条消息,默认转发最后5条消息，可以自行指定转发多少条消息
        /// </summary>
        /// <param name="who">被转发消息的好友/群聊,可以为空，则转发本窗口的消息</param>
        /// <param name="to">要转发给谁</param>
        /// <param name="fType">消息转发类型，详情请参见<see cref="ForwardMessageTypeEnums"/></param>
        /// <param name="rowCount">要转发多少条消息，默认是最后的5条消息,如果当前没有5条，则转发所有消息</param>
        public async Task<bool> ForwardMultipleMessage(string who, OneOf<string, string[]> to, ForwardMessageTypeEnums fType = ForwardMessageTypeEnums.ForwardMerge, int rowCount = 5) => await this.ChatContent.MessageBubbleList.ForwardMultipleMessage(who, to, fType, rowCount);


        /// <summary>
        /// 转发单条消息
        /// 流程：
        /// 1. 找到这一条消息,倒序找，这里注意一点，如果找不到消息，自动往前滚动，如果找不到，则不会转发此消息,日志显示错误，但不会报错.
        /// 2. 右键点击这一条消息
        /// 3. 找到菜单
        /// 4. 找到发送人
        /// </summary>
        /// <param name="to">要转发给谁,可以多人/群</param>
        /// <param name="chatSimpleMessage">要转发的消息<see cref="ChatSimpleMessage"/></param>
        /// <param name="prevScrollNumber">如果当前页找不到，往前翻页的次数</param>
        public async Task<bool> ForwardSingleMessage(ChatSimpleMessage chatSimpleMessage, OneOf<string, string[]> to, int prevScrollNumber = 30) => await this.ChatContent.MessageBubbleList.ForwardSingleMessage(chatSimpleMessage, to, prevScrollNumber);

        /// <summary>
        /// 转发单条消息
        /// </summary>
        /// <param name="who">要转发的好友昵称</param>
        /// <param name="message">要转发的消息内容</param>
        /// <param name="to">要转发给谁</param>
        /// <param name="prevScrollNumber">如果当前页找不到，往前滚动的次数</param>
        public async Task<bool> ForwardSingleMessage(string who, string message, OneOf<string, string[]> to, int prevScrollNumber = 30) => await this.ChatContent.MessageBubbleList.ForwardSingleMessage(who, message, to, prevScrollNumber);

    }
}