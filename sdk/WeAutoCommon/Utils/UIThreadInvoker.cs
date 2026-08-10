using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using FlaUI.UIA3;
using FlaUI.Core.AutomationElements;
using System.Diagnostics;

namespace WeAutoCommon.Utils
{
    /// <summary>
    /// 用于在UI线程中执行操作的类
    /// </summary>
    public class UIThreadInvoker : IDisposable
    {
        private readonly Thread _uiThread;
        private readonly BlockingCollection<Action<UIA3Automation>> _queue = new BlockingCollection<Action<UIA3Automation>>();
        private readonly TaskCompletionSource<bool> _started = new TaskCompletionSource<bool>();
        private readonly CancellationTokenSource _cts = new CancellationTokenSource();
        private volatile bool _IsRunning = false;
        private UIA3Automation _automation;
        private readonly string _ThreadName;
        public string ThreadName => _ThreadName;
        private volatile bool _disposed = false;
        public UIA3Automation Automation => _automation;

        public readonly int ActionThreadId;


        public UIThreadInvoker(string threadName)
        {
            _ThreadName = threadName;
            _uiThread = new Thread(ThreadMain);
            _uiThread.Name = _ThreadName;
            _uiThread.SetApartmentState(ApartmentState.STA);
            _uiThread.Priority = ThreadPriority.Normal;
            _uiThread.IsBackground = false;
            _uiThread.Start();
            _started.Task.GetAwaiter().GetResult();
            ActionThreadId = _uiThread.ManagedThreadId;
        }

        public override string ToString()
        {
            return $"UIThreadInvoker: {_ThreadName}";
        }

        private void ThreadMain()
        {
            try
            {
                using (_automation = new UIA3Automation())
                {
                    _started.SetResult(true);

                    foreach (var action in _queue.GetConsumingEnumerable(_cts.Token))
                    {
                        if (_disposed) break;
                        try
                        {
                            _IsRunning = true;
                            action(_automation);
                        }
                        catch (OperationCanceledException)
                        {
                            Trace.WriteLine($"UIThreadInvoker thread [{_ThreadName}] normally cancelled");
                            break;
                        }
                        catch (Exception ex)
                        {
                            // 记录异常，但不中断整个线程
                            Trace.WriteLine($"UIThreadInvoker thread [{_ThreadName}] Action execution failed: {ex}");
                        }
                        finally
                        {
                            _IsRunning = false;
                        }
                    }
                }
            }
            catch (OperationCanceledException)
            {
                // 正常取消，不需要记录
                Trace.WriteLine($"UIThreadInvoker thread [{_ThreadName}] normally cancelled");
            }
            catch (Exception ex)
            {
                Trace.WriteLine($"UIThreadInvoker thread [{_ThreadName}] failed: {ex}");
                _started.TrySetException(ex);
            }
        }
        /// <summary>
        /// 在UI线程中执行操作，返回结果
        /// </summary>
        /// <typeparam name="T">返回类型</typeparam>
        /// <param name="func">要执行的操作</param>
        /// <returns>返回结果</returns>
        public Task<T> Run<T>(Func<UIA3Automation, T> func)
        {
            if (_disposed)
                return Task.FromResult(default(T));

            var tcs = new TaskCompletionSource<T>();
            _queue.Add(automation =>
            {
                try
                {
                    var result = func(automation);
                    tcs.SetResult(result);
                }
                catch (Exception ex)
                {
                    tcs.SetException(ex);
                }
            });
            return tcs.Task;
        }
        /// <summary>
        /// 在UI线程中执行操作，不返回结果
        /// </summary>
        /// <param name="action">要执行的操作</param>
        /// <returns>返回结果</returns>
        public Task Run(Action<UIA3Automation> action)
        {
            if (_disposed)
                return Task.CompletedTask;
            return Run<object>(automation =>
            {
                action(automation);
                return null;
            });
        }

        /// <summary>
        /// 检查是否在运行中.
        /// </summary>
        /// <returns></returns>
        public bool IsSessionRunning() => _queue.Count != 0 || _IsRunning;

        public virtual void Dispose(bool disposing)
        {
            if (_disposed) return;
            _disposed = true;
            if (disposing)
            {
                _cts.Cancel();
                _queue.CompleteAdding();

                // 等待线程结束
                if (_uiThread.IsAlive)
                {
                    if (!_uiThread.Join(TimeSpan.FromSeconds(3)))
                        _uiThread.Interrupt();
                }

                _cts.Dispose();
                _queue.Dispose();
                _automation?.Dispose();
            }
        }

        ~UIThreadInvoker()
        {
            Dispose(false);
        }
        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }
    }
}



