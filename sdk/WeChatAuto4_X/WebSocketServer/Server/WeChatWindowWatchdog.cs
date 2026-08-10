using System.Diagnostics;
using Microsoft.Extensions.Options;
using WeChatAuto.Components;
using WeChatAuto.Utils;

internal sealed class WeChatWindowWatchdogOptions
{
    public const string SectionName = "WeChatWindowWatchdog";

    public bool Enabled { get; set; } = true;
    public int CheckIntervalMilliseconds { get; set; } = 1500;
    public int ConsecutiveFailureThreshold { get; set; } = 2;
    public bool RestoreMinimized { get; set; } = true;
    public int FailureCooldownMilliseconds { get; set; } = 10000;
}

internal sealed class WeChatWindowWatchdog : BackgroundService
{
    private readonly WeChatClientFactory _factory;
    private readonly ILogger<WeChatWindowWatchdog> _logger;
    private readonly WeChatWindowWatchdogOptions _options;
    private readonly Dictionary<int, int> _unavailableChecks = new();
    private readonly Dictionary<int, DateTimeOffset> _lastFailedRestore = new();

    public WeChatWindowWatchdog(
        WeChatClientFactory factory,
        ILogger<WeChatWindowWatchdog> logger,
        IOptions<WeChatWindowWatchdogOptions> options)
    {
        _factory = factory;
        _logger = logger;
        _options = options.Value;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_options.Enabled)
        {
            _logger.LogInformation("WeChat window watchdog is disabled");
            return;
        }

        var interval = TimeSpan.FromMilliseconds(Math.Clamp(
            _options.CheckIntervalMilliseconds,
            500,
            60000));
        _logger.LogInformation(
            "WeChat window watchdog started interval_ms={IntervalMs} threshold={Threshold} restore_minimized={RestoreMinimized}",
            interval.TotalMilliseconds,
            Math.Max(1, _options.ConsecutiveFailureThreshold),
            _options.RestoreMinimized);

        await CheckWindowsAsync();
        using var timer = new PeriodicTimer(interval);
        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            await CheckWindowsAsync();
        }
    }

    private Task CheckWindowsAsync()
    {
        WeChatClient[] clients;
        try
        {
            clients = _factory.GetWeChatClientList().Values.ToArray();
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "WeChat window watchdog could not enumerate clients");
            return Task.CompletedTask;
        }

        foreach (var client in clients)
            CheckWindow(client);
        return Task.CompletedTask;
    }

    private void CheckWindow(WeChatClient client)
    {
        var stopwatch = Stopwatch.StartNew();
        IntPtr handle = IntPtr.Zero;
        var stateKnown = false;
        var wasVisible = false;
        var wasMinimized = false;
        try
        {
            handle = (IntPtr)client.GetHandler();
            stateKnown = WinApi.GetWindowVisibility(handle, out wasVisible, out wasMinimized);
            var needsRestore = !stateKnown || !wasVisible || _options.RestoreMinimized && wasMinimized;
            if (!needsRestore)
            {
                _unavailableChecks.Remove(client.ClientProcessId);
                _lastFailedRestore.Remove(client.ClientProcessId);
                return;
            }

            var failedChecks = _unavailableChecks.GetValueOrDefault(client.ClientProcessId) + 1;
            _unavailableChecks[client.ClientProcessId] = failedChecks;
            if (failedChecks < Math.Max(1, _options.ConsecutiveFailureThreshold))
                return;

            if (IsInFailureCooldown(client.ClientProcessId))
            {
                return;
            }

            var restored = stateKnown && client.EnsureMainWindowVisible("window_watchdog");
            var afterKnown = WinApi.GetWindowVisibility(handle, out var isVisible, out var isMinimized);
            var success = restored && afterKnown && isVisible && !isMinimized;
            stopwatch.Stop();
            ServerOperationLog.WindowWatchdog(
                client.NickName,
                client.ClientProcessId,
                handle,
                stateKnown,
                wasVisible,
                wasMinimized,
                success,
                isVisible,
                isMinimized,
                failedChecks,
                stopwatch);

            if (success)
            {
                _unavailableChecks.Remove(client.ClientProcessId);
                _lastFailedRestore.Remove(client.ClientProcessId);
                _logger.LogWarning(
                    "Restored hidden WeChat window account={Account} process_id={ProcessId} handle={Handle} duration_ms={DurationMs}",
                    client.NickName,
                    client.ClientProcessId,
                    handle,
                    stopwatch.Elapsed.TotalMilliseconds);
            }
            else
            {
                _lastFailedRestore[client.ClientProcessId] = DateTimeOffset.Now;
                _logger.LogError(
                    "Failed to restore WeChat window account={Account} process_id={ProcessId} handle={Handle} state_known={StateKnown}",
                    client.NickName,
                    client.ClientProcessId,
                    handle,
                    stateKnown);
            }
        }
        catch (Exception ex)
        {
            if (IsInFailureCooldown(client.ClientProcessId))
                return;
            _lastFailedRestore[client.ClientProcessId] = DateTimeOffset.Now;
            stopwatch.Stop();
            WinApi.GetWindowVisibility(handle, out var isVisible, out var isMinimized);
            ServerOperationLog.WindowWatchdog(
                client.NickName,
                client.ClientProcessId,
                handle,
                stateKnown,
                wasVisible,
                wasMinimized,
                false,
                isVisible,
                isMinimized,
                _unavailableChecks.GetValueOrDefault(client.ClientProcessId),
                stopwatch,
                ex);
            _logger.LogError(ex, "WeChat window watchdog check failed account={Account}", client.NickName);
        }
    }

    private bool IsInFailureCooldown(int processId)
    {
        return _lastFailedRestore.TryGetValue(processId, out var lastFailure)
            && DateTimeOffset.Now - lastFailure < TimeSpan.FromMilliseconds(Math.Max(
                1000,
                _options.FailureCooldownMilliseconds));
    }
}
