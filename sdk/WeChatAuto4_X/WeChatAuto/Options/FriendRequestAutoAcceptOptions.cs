using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using OneOf;
using WeChatAuto.Components;
using WeChatAuto.Models;

namespace WeChatAuto.Options
{
    public class FriendRequestAutoAcceptOptions: FriendRequestAutoAcceptOptionsPrefix
    {
        /// <summary>
        /// 通过后的回调,返回给调用者三个信息:
        /// - 通过的好友昵称列表
        /// - WeChatClient对象，可以通过此对象发送消息等
        /// - 依赖注入 - 调用者可以通过依赖注入容器取出自己注入的对象，执行自己的业务逻辑;
        /// </summary>    
        public Func<List<NewFriendBackItem>, WeChatClient, IServiceProvider, Task> PassedCallBack { get; set; }

        public static FriendRequestAutoAcceptOptions CreateFriendRequestAutoAcceptOptions(FriendRequestAutoAcceptOptionsPrefix oriObject)
        {
            var result = new FriendRequestAutoAcceptOptions();
            result.PassedDelete = oriObject.PassedDelete;
            result.KeyWord = oriObject.KeyWord;
            result.Suffix = oriObject.Suffix;
            result.Label = oriObject.Label;
            return result;
        }
    }

    public class FriendRequestAutoAcceptOptionsPrefix
    {
        /// <summary>
        /// 通过后是否删除申请记录
        /// </summary>
        [JsonProperty("passed_delete")]
        public bool PassedDelete { get; set; } = true;

        /// <summary>
        /// 打招呼关键词过滤,可以设置多个，回调的时候会携带此KeyWord的信息返回给调用者，调用者应该根据关键词做相应的处理.
        /// </summary>
        [JsonProperty("keyword")]
        public List<string> KeyWord { get; set; }

        /// <summary>
        /// 好友备注后缀
        /// 如果设置后缀，被通过的好友会自动加上此后缀,如:AI.Net_Test
        /// </summary>
        [JsonProperty("suffix")]
        public string Suffix { get; set; }

        /// <summary>
        /// 微信标签
        /// </summary>
        [JsonProperty("label")]
        public string Label { get; set; }
    }
}