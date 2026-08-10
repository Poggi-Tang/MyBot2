using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using Newtonsoft.Json;

namespace WeChatAuto.Utils
{
    internal static class AttachmentOperationLog
    {
        private static readonly object Sync = new object();

        public static void Write(
            string operationId,
            string stage,
            Stopwatch stopwatch,
            bool? success = null,
            Dictionary<string, object> details = null)
        {
            try
            {
                var entry = new Dictionary<string, object>
                {
                    ["timestamp"] = DateTimeOffset.Now.ToString("O"),
                    ["event"] = stage,
                    ["operation_id"] = operationId,
                    ["layer"] = "wechat_sdk",
                    ["operation"] = "SaveReceivedFileAs",
                    ["duration_ms"] = Math.Round(stopwatch.Elapsed.TotalMilliseconds, 3)
                };
                if (success.HasValue)
                    entry["success"] = success.Value;
                if (details != null)
                    entry["details"] = details;

                lock (Sync)
                {
                    var directory = Path.Combine(AppContext.BaseDirectory, "logs");
                    Directory.CreateDirectory(directory);
                    var path = Path.Combine(directory, $"attachment-{DateTime.Now:yyyyMMdd}.jsonl");
                    File.AppendAllText(path, JsonConvert.SerializeObject(entry) + Environment.NewLine, Encoding.UTF8);
                }
            }
            catch
            {
                // Diagnostics must not interrupt message monitoring.
            }
        }
    }
}
