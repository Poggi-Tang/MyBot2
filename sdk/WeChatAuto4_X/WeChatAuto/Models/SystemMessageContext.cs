using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using OneOf;
using WeChatAuto.Components;
using WeAutoCommon.Enums;
using Newtonsoft.Json;

namespace WeChatAuto.Models
{
    /// <summary>
    /// 系统消息上下文
    /// 解释newMessages列表的内容，即可以获取系统消息.
    /// </summary>
    public sealed class SystemMessageContext
    {
        public SystemMessageContext(List<string> newMessages, WeChatClient ownerClient, IServiceProvider serviceProvider, string from)
        {
            NewMessages = newMessages;
            Client = ownerClient;
            ServiceProvider = serviceProvider;
            FromWho = from;
        }
        /// <summary>
        /// 本次消息的来源，为好友或者群聊名称.
        /// </summary>
        public string FromWho { get; set; }
        /// <summary>
        /// 新消息气泡列表
        /// </summary>
        public List<string> NewMessages { get; set; }

        /// <summary>
        /// 当前微信客户端,通过Client可以执行发消息等操作
        /// 参考<see cref="WeChatClient"/>
        /// </summary>
        public WeChatClient Client { get; set; }
        /// <summary>
        /// 服务提供者，使用者可以注入自己的服务，在此处获取
        /// 参考<see cref="IServiceProvider"/>
        /// </summary>
        public IServiceProvider ServiceProvider { get; set; }
    }
}