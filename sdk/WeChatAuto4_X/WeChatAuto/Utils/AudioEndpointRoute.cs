using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using NAudio.CoreAudioApi;

namespace WeChatAuto.Utils
{
    internal sealed class AudioEndpointRoute : IDisposable
    {
        private readonly Dictionary<Role, string> _previousEndpoints;
        private bool _disposed;

        private AudioEndpointRoute(Dictionary<Role, string> previousEndpoints)
        {
            _previousEndpoints = previousEndpoints;
        }

        public static AudioEndpointRoute UseCaptureDevice(string deviceName)
        {
            using var enumerator = new MMDeviceEnumerator();
            MMDevice target = null;
            foreach (var device in enumerator.EnumerateAudioEndPoints(DataFlow.Capture, DeviceState.Active))
            {
                if (device.FriendlyName.Contains(deviceName, StringComparison.OrdinalIgnoreCase))
                {
                    target = device;
                    break;
                }
            }

            if (target == null)
                throw new InvalidOperationException($"Capture endpoint was not found: {deviceName}");

            var previous = new Dictionary<Role, string>();
            var roles = new[] { Role.Console, Role.Multimedia, Role.Communications };
            foreach (var role in roles)
            {
                try
                {
                    previous[role] = enumerator.GetDefaultAudioEndpoint(DataFlow.Capture, role).ID;
                }
                catch
                {
                    // A role can legitimately have no default endpoint.
                }
            }

            try
            {
                foreach (var role in roles)
                    SetDefaultEndpoint(target.ID, role);
                Thread.Sleep(900);
                return new AudioEndpointRoute(previous);
            }
            catch
            {
                Restore(previous);
                throw;
            }
        }

        public void Dispose()
        {
            if (_disposed)
                return;
            _disposed = true;
            Restore(_previousEndpoints);
        }

        private static void Restore(Dictionary<Role, string> endpoints)
        {
            foreach (var endpoint in endpoints)
            {
                try
                {
                    SetDefaultEndpoint(endpoint.Value, endpoint.Key);
                }
                catch
                {
                    // Do not mask the original send result during cleanup.
                }
            }
        }

        private static void SetDefaultEndpoint(string deviceId, Role role)
        {
            var policy = (IPolicyConfig)new PolicyConfigClient();
            try
            {
                var result = policy.SetDefaultEndpoint(deviceId, role);
                if (result != 0)
                    Marshal.ThrowExceptionForHR(result);
            }
            finally
            {
                Marshal.FinalReleaseComObject(policy);
            }
        }

        [ComImport]
        [Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")]
        private class PolicyConfigClient
        {
        }

        [ComImport]
        [Guid("F8679F50-850A-41CF-9C72-430F290290C8")]
        [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        private interface IPolicyConfig
        {
            [PreserveSig] int GetMixFormat(string deviceId, IntPtr format);
            [PreserveSig] int GetDeviceFormat(string deviceId, int defaultFormat, IntPtr format);
            [PreserveSig] int ResetDeviceFormat(string deviceId);
            [PreserveSig] int SetDeviceFormat(string deviceId, IntPtr endpointFormat, IntPtr mixFormat);
            [PreserveSig] int GetProcessingPeriod(string deviceId, int defaultPeriod, IntPtr period, IntPtr minimumPeriod);
            [PreserveSig] int SetProcessingPeriod(string deviceId, IntPtr period);
            [PreserveSig] int GetShareMode(string deviceId, IntPtr mode);
            [PreserveSig] int SetShareMode(string deviceId, IntPtr mode);
            [PreserveSig] int GetPropertyValue(string deviceId, IntPtr propertyKey, IntPtr propertyValue);
            [PreserveSig] int SetPropertyValue(string deviceId, IntPtr propertyKey, IntPtr propertyValue);
            [PreserveSig] int SetDefaultEndpoint(
                [MarshalAs(UnmanagedType.LPWStr)] string deviceId,
                [MarshalAs(UnmanagedType.U4)] Role role);
            [PreserveSig] int SetEndpointVisibility(string deviceId, int visible);
        }
    }
}
