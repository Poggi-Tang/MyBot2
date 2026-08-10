using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using OneOf;
using WeChatAuto.Components;
using WeAutoCommon.Enums;

namespace WeChatAuto.Models
{
    public sealed class MessageContext
    {
        public MessageContext(List<SimpleMessageBubble> newMessages, List<SimpleMessageBubble> historyMessages, Sender sender, WeChatClient ownerClient, WeChatClientFactory systemClientFactory, IServiceProvider serviceProvider, string ownerNickName)
        {
            NewMessages = newMessages;
            HistoryMessages = historyMessages;
            Sender = sender;
            Client = ownerClient;
            SystemClientFactory = systemClientFactory;
            ServiceProvider = serviceProvider;
            OwnerNickName = ownerNickName;
        }
        /// <summary>
        /// 当前我的微信昵称
        /// </summary>
        public string OwnerNickName { get; set; }
        /// <summary>
        /// 新消息气泡列表
        /// 参考<see cref="MessageBubble"/>
        /// </summary>
        public List<SimpleMessageBubble> NewMessages { get; set; }
        /// <summary>
        /// 历史消息气泡列表,供大模型参考
        /// 参考<see cref="MessageBubble"/>
        /// </summary>
        public List<SimpleMessageBubble> HistoryMessages { get; set; }

        /// <summary>
        /// 发送者,调用此类可以发送消息、发送文件、发送表情等
        /// 只能调用api给当前窗口发送
        /// </summary>
        public Sender Sender { get; set; }
        /// <summary>
        /// 当前微信客户端,通过Client可以执行发消息等操作
        /// 参考<see cref="WeChatClient"/>
        /// </summary>
        public WeChatClient Client { get; set; }
        /// <summary>
        /// 系统微信客户端工厂,可以通过WeChatClientFactory获取其他微信客户端,发送消息、发送文件、发送表情等
        /// 参考<see cref="WeChatClientFactory"/>
        /// </summary>
        public WeChatClientFactory SystemClientFactory { get; set; }
        /// <summary>
        /// 服务提供者，使用者可以注入自己的服务，在此处获取
        /// 参考<see cref="IServiceProvider"/>
        /// </summary>
        public IServiceProvider ServiceProvider { get; set; }
    }
}