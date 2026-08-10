using System.Diagnostics;
using System.IO;
using System;
using System.Threading.Tasks;
using System.Runtime.InteropServices;
using System.Configuration;
using FlaUI.Core;
using FlaUI.UIA3;
using WeChatAuto.Components;

namespace WeChatAuto.Utils
{
    /// <summary>
    /// 微信执行器
    /// </summary>
    public class WeChatInvoker
    {
        /// <summary>
        /// 执行方法
        /// </summary>
        /// <param name="action"></param>
        /// <returns></returns>
        public static async Task Call(Action<UIA3Automation> action)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                action(WeChatClientFactory.MainActionThreadInvoker.Automation);
                await Task.CompletedTask;
                return;
            }
            await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                action(automation);
            }).ConfigureAwait(false);
        }
        /// <summary>
        /// 执行方法
        /// </summary>
        /// <param name="action"></param>
        /// <returns></returns>
        public static async Task Call(Action action)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                action();
                await Task.CompletedTask;
                return;
            }
            await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                action();
            }).ConfigureAwait(false);
        }
        /// <summary>
        /// 执行带一个参数的方法
        /// </summary>
        /// <typeparam name="T"></typeparam>
        /// <param name="action"></param>
        /// <param name="t"></param>
        /// <returns></returns>
        public static async Task Call<T>(Action<UIA3Automation, T> action, T t)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                action(WeChatClientFactory.MainActionThreadInvoker.Automation, t);
                await Task.CompletedTask;
                return;
            }
            await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                action(automation, t);
            }).ConfigureAwait(false);
        }

        /// <summary>
        /// 执行带两个参数的方法
        /// </summary>
        /// <typeparam name="T1"></typeparam>
        /// <typeparam name="T2"></typeparam>
        /// <param name="action"></param>
        /// <param name="t1"></param>
        /// <param name="t2"></param>
        /// <returns></returns>
        public static async Task Call<T1, T2>(Action<UIA3Automation, T1, T2> action, T1 t1, T2 t2)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                action(WeChatClientFactory.MainActionThreadInvoker.Automation, t1, t2);
                await Task.CompletedTask;
                return;
            }
            await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                action(automation, t1, t2);
            }).ConfigureAwait(false);
        }
        /// <summary>
        /// 执行带两个参数方法
        /// </summary>
        /// <typeparam name="T1"></typeparam>
        /// <typeparam name="T2"></typeparam>
        /// <typeparam name="T3"></typeparam>
        /// <param name="action"></param>
        /// <param name="t1"></param>
        /// <param name="t2"></param>
        /// <param name="t3"></param>
        /// <returns></returns>
        public static async Task Call<T1, T2, T3>(Action<UIA3Automation, T1, T2, T3> action, T1 t1, T2 t2, T3 t3)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                action(WeChatClientFactory.MainActionThreadInvoker.Automation, t1, t2, t3);
                await Task.CompletedTask;
                return;
            }
            await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                action(automation, t1, t2, t3);
            }).ConfigureAwait(false);
        }
        /// <summary>
        /// 执行带四个参数的方式
        /// </summary>
        /// <typeparam name="T1"></typeparam>
        /// <typeparam name="T2"></typeparam>
        /// <typeparam name="T3"></typeparam>
        /// <typeparam name="T4"></typeparam>
        /// <param name="action"></param>
        /// <param name="t1"></param>
        /// <param name="t2"></param>
        /// <param name="t3"></param>
        /// <param name="t4"></param>
        /// <returns></returns>
        public static async Task Call<T1, T2, T3, T4>(Action<UIA3Automation, T1, T2, T3, T4> action, T1 t1, T2 t2, T3 t3, T4 t4)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                action(WeChatClientFactory.MainActionThreadInvoker.Automation, t1, t2, t3, t4);
                await Task.CompletedTask;
                return;
            }
            await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                action(automation, t1, t2, t3, t4);
            }).ConfigureAwait(false);
        }

        /// <summary>
        /// 执行一个函数
        /// </summary>
        /// <typeparam name="T"></typeparam>
        /// <param name="Func"></param>
        /// <returns></returns>
        public static async Task<T> Call<T>(Func<UIA3Automation, T> Func)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                return await Task.FromResult(Func(WeChatClientFactory.MainActionThreadInvoker.Automation));
            }
            return await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                return Func(automation);
            }).ConfigureAwait(false);
        }

        /// <summary>
        /// 执行带一个参数函数
        /// </summary>
        /// <typeparam name="T"></typeparam>
        /// <typeparam name="T1"></typeparam>
        /// <param name="Func"></param>
        /// <param name="t1"></param>
        /// <returns></returns>
        public static async Task<T> Call<T1, T>(Func<UIA3Automation, T1, T> Func, T1 t1)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                return await Task.FromResult(Func(WeChatClientFactory.MainActionThreadInvoker.Automation, t1));
            }
            return await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                return Func(automation, t1);
            }).ConfigureAwait(false);
        }
        /// <summary>
        /// 执行一个带两个参数函数
        /// </summary>
        /// <typeparam name="T"></typeparam>
        /// <typeparam name="T1"></typeparam>
        /// <typeparam name="T2"></typeparam>
        /// <param name="Func"></param>
        /// <param name="t1"></param>
        /// <param name="t2"></param>
        /// <returns></returns>
        public static async Task<T> Call<T1, T2, T>(Func<UIA3Automation, T1, T2, T> Func, T1 t1, T2 t2)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                return await Task.FromResult(Func(WeChatClientFactory.MainActionThreadInvoker.Automation, t1, t2));
            }
            return await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                return Func(automation, t1, t2);
            }).ConfigureAwait(false);
        }

        /// <summary>
        /// 执行一个带三个参数函数
        /// </summary>
        /// <typeparam name="T"></typeparam>
        /// <typeparam name="T1"></typeparam>
        /// <typeparam name="T2"></typeparam>
        /// <typeparam name="T3"></typeparam>
        /// <param name="Func"></param>
        /// <param name="t1"></param>
        /// <param name="t2"></param>
        /// <param name="t3"></param>
        /// <returns></returns>
        public static async Task<T> Call<T1, T2, T3, T>(Func<UIA3Automation, T1, T2, T3, T> Func, T1 t1, T2 t2, T3 t3)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                return await Task.FromResult(Func(WeChatClientFactory.MainActionThreadInvoker.Automation, t1, t2, t3));
            }
            return await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                return Func(automation, t1, t2, t3);
            }).ConfigureAwait(false);
        }

        /// <summary>
        /// 执行一个带四个参数函数
        /// </summary>
        /// <typeparam name="T"></typeparam>
        /// <typeparam name="T1"></typeparam>
        /// <typeparam name="T2"></typeparam>
        /// <typeparam name="T3"></typeparam>
        /// <typeparam name="T4"></typeparam>
        /// <param name="Func"></param>
        /// <param name="t1"></param>
        /// <param name="t2"></param>
        /// <param name="t3"></param>
        /// <param name="t4"></param>
        /// <returns></returns>
        public static async Task<T> Call<T1, T2, T3, T4, T>(Func<UIA3Automation, T1, T2, T3, T4, T> Func, T1 t1, T2 t2, T3 t3, T4 t4)
        {
            if (System.Threading.Thread.CurrentThread.ManagedThreadId == WeChatClientFactory.MainActionThreadInvoker.ActionThreadId)
            {
                return await Task.FromResult(Func(WeChatClientFactory.MainActionThreadInvoker.Automation, t1, t2, t3, t4));
            }
            return await WeChatClientFactory.MainActionThreadInvoker.Run(automation =>
            {
                return Func(automation, t1, t2, t3, t4);
            }).ConfigureAwait(false);
        }
    }
}