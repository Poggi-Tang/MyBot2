using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using OneOf;
using WeChatAuto.Components;
using WeChatAuto.Models;

namespace WeChatAuto.Options
{
    public class SystemMonitorOption
    {
        public string Who { get; set; }
        public CancellationToken Token { get; set; }
        public Func<SystemMessageContext,Task> CallBack { get; set; }
    }
}