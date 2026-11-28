<#
.SYNOPSIS
    Switch Windows default playback (render) audio devices repeatedly via Core Audio COM.
.DESCRIPTION
    PowerShell 5.1+ compatible helper using IMMDeviceEnumerator + IPolicyConfig (no third-party modules).
    Prints active render endpoints, resolves targets via case-insensitive substring (or -Regex),
    fails immediately on NO_MATCH, and performs alternating default-endpoint switches.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\rapid_switch.ps1 -Devices XIBERIA,Realtek -Rounds 2 -IntervalSeconds 1.5
#>

[CmdletBinding()]
param(
    [string[]]$Devices = @("XIBERIA", "Realtek"),
    [int]$Rounds = 2,
    [double]$IntervalSeconds = 1.5,
    [switch]$Regex
)

$ErrorActionPreference = "Stop"

if ($Rounds -lt 1) {
    Write-Error "Rounds must be >= 1 (got $Rounds)."
    exit 1
}
if ($IntervalSeconds -lt 0) {
    Write-Error "IntervalSeconds must be >= 0 (got $IntervalSeconds)."
    exit 1
}

$Targets = @()
foreach ($entry in $Devices) {
    foreach ($part in ($entry -split ",")) {
        $trimmed = $part.Trim()
        if ($trimmed) {
            $Targets += $trimmed
        }
    }
}
if ($Targets.Count -lt 2) {
    Write-Error "At least 2 target device patterns are required."
    exit 1
}

$InteropCode = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace ListenScopeCoreAudio
{
    public sealed class AudioEndpointInfo
    {
        public string Id { get; set; }
        public string Name { get; set; }
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct PROPERTYKEY
    {
        public Guid fmtid;
        public uint pid;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct PROPVARIANT
    {
        public ushort vt;
        public ushort wReserved1;
        public ushort wReserved2;
        public ushort wReserved3;
        public IntPtr pwszVal;
        public IntPtr pad;
    }

    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    internal class MMDeviceEnumeratorComObject { }

    [ComImport, Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")]
    internal class PolicyConfigClientComObject { }

    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IMMDeviceEnumerator
    {
        [PreserveSig] int EnumAudioEndpoints(int dataFlow, int dwStateMask, out IMMDeviceCollection ppDevices);
        [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice ppEndpoint);
        [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string pwstrId, out IMMDevice ppDevice);
        [PreserveSig] int RegisterEndpointNotificationCallback(IntPtr pClient);
        [PreserveSig] int UnregisterEndpointNotificationCallback(IntPtr pClient);
    }

    [Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IMMDeviceCollection
    {
        [PreserveSig] int GetCount(out uint pcDevices);
        [PreserveSig] int Item(uint nDevice, out IMMDevice ppDevice);
    }

    [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IMMDevice
    {
        [PreserveSig] int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, [MarshalAs(UnmanagedType.IUnknown)] out object ppInterface);
        [PreserveSig] int OpenPropertyStore(int stgmAccess, out IPropertyStore ppProperties);
        [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string ppstrId);
        [PreserveSig] int GetState(out int pdwState);
    }

    [Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IPropertyStore
    {
        [PreserveSig] int GetCount(out uint cProps);
        [PreserveSig] int GetAt(uint iProp, out PROPERTYKEY pkey);
        [PreserveSig] int GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
        [PreserveSig] int SetValue(ref PROPERTYKEY key, ref PROPVARIANT propvar);
        [PreserveSig] int Commit();
    }

    [Guid("F8679F50-850A-41CF-9C72-430F290290C8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IPolicyConfig
    {
        [PreserveSig] int GetMixFormat([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, IntPtr ppFormat);
        [PreserveSig] int GetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, bool bDefault, IntPtr ppFormat);
        [PreserveSig] int ResetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName);
        [PreserveSig] int SetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, IntPtr pEndpointFormat, IntPtr mixFormat);
        [PreserveSig] int GetProcessingPeriod([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, bool bDefault, IntPtr pmftDefaultPeriod, IntPtr pmftMinimumPeriod);
        [PreserveSig] int SetProcessingPeriod([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, IntPtr pmftPeriod);
        [PreserveSig] int GetShareMode([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, IntPtr pMode);
        [PreserveSig] int SetShareMode([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, IntPtr mode);
        [PreserveSig] int GetPropertyValue([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, bool bFxStore, IntPtr key, IntPtr pv);
        [PreserveSig] int SetPropertyValue([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, bool bFxStore, IntPtr key, IntPtr pv);
        [PreserveSig] int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string wszDeviceId, int role);
        [PreserveSig] int SetEndpointVisibility([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, bool bVisible);
    }

    public static class AudioSwitcher
    {
        [DllImport("ole32.dll")]
        private static extern int PropVariantClear(ref PROPVARIANT pvar);

        private static PROPERTYKEY PKEY_Device_FriendlyName = new PROPERTYKEY
        {
            fmtid = new Guid("A45C254E-DF1C-4EFD-8020-67D146A850E0"),
            pid = 14
        };

        private static string ReadEndpointName(IMMDevice dev)
        {
            string name = "";
            IPropertyStore store = null;
            try
            {
                if (dev.OpenPropertyStore(0, out store) == 0 && store != null)
                {
                    PROPVARIANT pv;
                    PROPERTYKEY key = PKEY_Device_FriendlyName;
                    if (store.GetValue(ref key, out pv) == 0)
                    {
                        try
                        {
                            if (pv.vt == 31 && pv.pwszVal != IntPtr.Zero)
                            {
                                name = Marshal.PtrToStringUni(pv.pwszVal) ?? "";
                            }
                        }
                        finally
                        {
                            PropVariantClear(ref pv);
                        }
                    }
                }
            }
            finally
            {
                if (store != null) Marshal.ReleaseComObject(store);
            }
            return name;
        }

        public static List<AudioEndpointInfo> GetActiveRenderDevices()
        {
            var list = new List<AudioEndpointInfo>();
            var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorComObject();
            IMMDeviceCollection col = null;
            try
            {
                // eRender = 0, DEVICE_STATE_ACTIVE = 1
                int hr = enumerator.EnumAudioEndpoints(0, 1, out col);
                if (hr != 0 || col == null)
                {
                    Marshal.ThrowExceptionForHR(hr);
                }
                uint count;
                col.GetCount(out count);
                for (uint i = 0; i < count; i++)
                {
                    IMMDevice dev = null;
                    try
                    {
                        if (col.Item(i, out dev) == 0 && dev != null)
                        {
                            string id;
                            if (dev.GetId(out id) == 0 && !string.IsNullOrEmpty(id))
                            {
                                list.Add(new AudioEndpointInfo
                                {
                                    Id = id,
                                    Name = ReadEndpointName(dev)
                                });
                            }
                        }
                    }
                    finally
                    {
                        if (dev != null) Marshal.ReleaseComObject(dev);
                    }
                }
            }
            finally
            {
                if (col != null) Marshal.ReleaseComObject(col);
                Marshal.ReleaseComObject(enumerator);
            }
            return list;
        }

        public static AudioEndpointInfo GetDefaultRenderDevice()
        {
            var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorComObject();
            IMMDevice dev = null;
            try
            {
                // eRender = 0, eConsole = 0
                int hr = enumerator.GetDefaultAudioEndpoint(0, 0, out dev);
                if (hr != 0 || dev == null)
                {
                    return null;
                }
                string id;
                dev.GetId(out id);
                return new AudioEndpointInfo
                {
                    Id = id ?? "",
                    Name = ReadEndpointName(dev)
                };
            }
            finally
            {
                if (dev != null) Marshal.ReleaseComObject(dev);
                Marshal.ReleaseComObject(enumerator);
            }
        }

        public static void SetDefaultRenderDevice(string deviceId)
        {
            var policy = (IPolicyConfig)new PolicyConfigClientComObject();
            try
            {
                // eConsole = 0, eMultimedia = 1, eCommunications = 2
                for (int role = 0; role <= 2; role++)
                {
                    int hr = policy.SetDefaultEndpoint(deviceId, role);
                    if (hr != 0)
                    {
                        Marshal.ThrowExceptionForHR(hr);
                    }
                }
            }
            finally
            {
                Marshal.ReleaseComObject(policy);
            }
        }
    }
}
'@

if (-not ("ListenScopeCoreAudio.AudioSwitcher" -as [type])) {
    Add-Type -TypeDefinition $InteropCode -Language CSharp
}

$activeDevices = [ListenScopeCoreAudio.AudioSwitcher]::GetActiveRenderDevices()
$currentDefault = [ListenScopeCoreAudio.AudioSwitcher]::GetDefaultRenderDevice()
$currentId = if ($currentDefault) { $currentDefault.Id } else { "" }

Write-Host "Active Windows playback (render) devices ($($activeDevices.Count)):" -ForegroundColor Cyan
for ($i = 0; $i -lt $activeDevices.Count; $i++) {
    $d = $activeDevices[$i]
    $marker = if ($d.Id -eq $currentId) { " [DEFAULT]" } else { "" }
    Write-Host ("  [{0}] {1}{2} (id={3})" -f $i, $d.Name, $marker, $d.Id)
}

$resolved = @()
foreach ($pat in $Targets) {
    $matches = @()
    foreach ($d in $activeDevices) {
        $isHit = if ($Regex) {
            $d.Name -match $pat
        } else {
            $d.Name.IndexOf($pat, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        }
        if ($isHit) {
            $matches += $d
        }
    }
    if ($matches.Count -eq 0) {
        Write-Error ("NO_MATCH: target pattern '{0}' matched 0 active playback devices." -f $pat)
        exit 1
    }
    $chosen = $matches[0]
    if ($matches.Count -gt 1) {
        Write-Warning ("Multiple devices matched '{0}'; selecting first: '{1}'" -f $pat, $chosen.Name)
    }
    Write-Host ("Matched '{0}' -> '{1}' (id={2})" -f $pat, $chosen.Name, $chosen.Id) -ForegroundColor Green
    $resolved += $chosen
}

$sequence = @()
$startIdx = 0
if ($currentId -and $resolved[0].Id -eq $currentId) {
    $startIdx = 1
}
for ($r = 0; $r -lt $Rounds; $r++) {
    for ($k = 0; $k -lt $resolved.Count; $k++) {
        $idx = ($startIdx + $k) % $resolved.Count
        $sequence += $resolved[$idx]
    }
}

$total = $sequence.Count
$intervalMs = [int][Math]::Round($IntervalSeconds * 1000.0)
for ($s = 0; $s -lt $total; $s++) {
    $target = $sequence[$s]
    [ListenScopeCoreAudio.AudioSwitcher]::SetDefaultRenderDevice($target.Id)
    $after = [ListenScopeCoreAudio.AudioSwitcher]::GetDefaultRenderDevice()
    $afterName = if ($after) { $after.Name } else { "<unknown>" }
    Write-Host ("[{0}/{1}] Switched default playback device -> '{2}' (verified: '{3}')" -f ($s + 1), $total, $target.Name, $afterName)
    if ($s + 1 -lt $total -and $intervalMs -gt 0) {
        Start-Sleep -Milliseconds $intervalMs
    }
}

Write-Host "Completed $total default playback device switches." -ForegroundColor Green
