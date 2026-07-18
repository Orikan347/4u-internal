[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$CandidateZip,
    [Parameter(Mandatory = $true)][string]$ContractPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [ValidateSet("CapabilityOnly", "AuthorizedMainWindowNoSend")][string]$Mode = "CapabilityOnly"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$script:Screenshots = @()
$script:Process = $null
$script:ForbiddenAction = "FINAL_CONFIRM_OK"
$script:WorkRoot = $null
$script:CallbackRegistryCleanupCompleted = $false
$script:EnvironmentReadback = [ordered]@{}
$script:Observations = [ordered]@{
    auth_required_window_visible = $false
    cancel_by_closing_app = $false
    retry_by_relaunching_same_exe = $false
    blank_input_rejected = $false
    deidentified_input_entered = $false
    preview_visible = $false
    preview_cancelled = $false
}

function Get-LowerSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Stop-Candidate {
    if ($script:Process -and !$script:Process.HasExited) {
        Stop-Process -Id $script:Process.Id -Force -ErrorAction SilentlyContinue
        $script:Process.WaitForExit(5000) | Out-Null
    }
    $script:Process = $null
}

function Get-LineProcesses {
    return @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -match '^(LINE|LineLauncher|LineCall)$'
    })
}

function Clear-EphemeralState {
    Stop-Candidate
    try {
        $callbackKey = "HKCU:\Software\Classes\dealalliance-line-windows"
        if (Test-Path -LiteralPath $callbackKey) {
            Remove-Item -LiteralPath $callbackKey -Recurse -Force
        }
        $script:CallbackRegistryCleanupCompleted = !(Test-Path -LiteralPath $callbackKey)
    } catch {
        $script:CallbackRegistryCleanupCompleted = $false
    }
    if ($script:WorkRoot -and (Test-Path -LiteralPath $script:WorkRoot)) {
        Remove-Item -LiteralPath $script:WorkRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Write-Result([string]$Status, [string]$Overall, [string]$Detail, [string]$ExePath = "") {
    Stop-Candidate
    $exeHashAfter = $null
    if ($ExePath -and (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
        $exeHashAfter = Get-LowerSha256 $ExePath
    }
    Clear-EphemeralState
    $report = [ordered]@{
        schema_version = "line_windows_8000_github_hosted_gui_runtime_v1"
        status = $Status
        overall = $Overall
        mode = $Mode
        release_id = "DA-LINE-WINDOWS-20260717-8000"
        source_run_id = "29644293092"
        candidate_exe_sha256 = $exeHashAfter
        exact_exe_bytes_unchanged = ($exeHashAfter -eq "63594612df121c7bf49fb909c4f1b004a81e329fb1519a8250f50dce3f4145cd")
        detail = $Detail
        environment = $script:EnvironmentReadback
        observations = $script:Observations
        screenshots = $script:Screenshots
        callback_registry_cleanup_completed = $script:CallbackRegistryCleanupCompleted
        local_ephemeral_writes = @("isolated_appdata", "callback_registry_then_cleanup")
        external_writes = 0
        provider_dependent_cases_executed = ($Mode -eq "AuthorizedMainWindowNoSend")
        real_data = $false
        line_process_started = $false
        line_ui_touched = $false
        desktop_driver_exercised = $false
        keyboard_or_clipboard_sent_to_line = $false
        final_send_clicked = $false
        messages_sent = 0
        send_attempts = 0
        external_delivery_actions = @()
        gui_no_send_passed = $false
        authenticode_allowed = $false
        formal_registry_allowed = $false
        upload_product_allowed = $false
        download_catalog_allowed = $false
    }
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory "runtime-report.json") -Encoding UTF8
    Write-Host "LINE_WINDOWS_8000_GUI_CAPABILITY_STATUS=$Status"
    Write-Host "MESSAGES_SENT=0 SEND_ATTEMPTS=0 LINE_STARTED=false FINAL_SEND_CLICKED=false"
}

function Get-DesktopName {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class DesktopProbe {
  [DllImport("user32.dll")] public static extern IntPtr GetThreadDesktop(uint id);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll", SetLastError=true)] public static extern bool GetUserObjectInformation(IntPtr h, int n, StringBuilder s, int l, ref int needed);
  public static string Name() {
    IntPtr h = GetThreadDesktop(GetCurrentThreadId()); int needed = 0;
    GetUserObjectInformation(h, 2, null, 0, ref needed);
    var b = new StringBuilder(Math.Max(needed, 256));
    return GetUserObjectInformation(h, 2, b, b.Capacity, ref needed) ? b.ToString() : "";
  }
}
"@
    return [DesktopProbe]::Name()
}

function Save-Screen([string]$Name) {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $path = Join-Path $OutputDirectory $Name
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        $script:Screenshots += [ordered]@{ name = $Name; sha256 = (Get-LowerSha256 $path) }
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Get-AppElements([int]$ProcessId) {
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcessId)
    return [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Get-ElementNames([int]$ProcessId) {
    $names = @()
    foreach ($item in (Get-AppElements $ProcessId)) {
        try {
            $name = [string]$item.Current.Name
            if ($name) { $names += $name }
        } catch {}
    }
    return @($names | Select-Object -Unique)
}

function Wait-ForName([int]$ProcessId, [string]$Pattern, [int]$Seconds = 15) {
    $limit = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        foreach ($name in (Get-ElementNames $ProcessId)) {
            if ($name -like "*$Pattern*") { return $true }
        }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $limit)
    return $false
}

function Find-Element([int]$ProcessId, [string]$NamePattern, [string]$ControlType = "") {
    foreach ($item in (Get-AppElements $ProcessId)) {
        try {
            $name = [string]$item.Current.Name
            $type = [string]$item.Current.ControlType.ProgrammaticName
            if ($name -like "*$NamePattern*" -and (!$ControlType -or $type -like "*$ControlType*")) { return $item }
        } catch {}
    }
    return $null
}

function Invoke-UIAElement($Element) {
    $pattern = $null
    if (!$Element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { return $false }
    $pattern.Invoke()
    return $true
}

function Set-UIAValue($Element, [string]$Value) {
    $pattern = $null
    if (!$Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) { return $false }
    if ($pattern.Current.IsReadOnly) { return $false }
    $pattern.SetValue($Value)
    return $true
}

function Start-Candidate([string]$ExePath, [string]$IsolatedAppData) {
    $env:APPDATA = $IsolatedAppData
    $script:Process = Start-Process -FilePath $ExePath -PassThru
    $limit = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $script:Process.Refresh()
        if ($script:Process.HasExited) { return $false }
        if ($script:Process.MainWindowHandle -ne 0) { return $true }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $limit)
    return $false
}

try {
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw "WIN-GUI-HOST-001: Windows is required" }
    if (!(Test-Path -LiteralPath $ContractPath -PathType Leaf)) { throw "WIN-GUI-CONTRACT-001: missing contract" }
    if (!(Test-Path -LiteralPath $CandidateZip -PathType Leaf)) { throw "WIN-GUI-INPUT-001: missing candidate ZIP" }

    $contract = Get-Content -Raw -LiteralPath $ContractPath | ConvertFrom-Json
    if ($contract.release_identity.release_id -ne "DA-LINE-WINDOWS-20260717-8000") { throw "WIN-GUI-CONTRACT-002: wrong release" }
    if ((Get-LowerSha256 $CandidateZip) -ne $contract.candidate.package_sha256) { throw "WIN-GUI-HASH-001: ZIP hash mismatch" }

    $script:WorkRoot = Join-Path $env:RUNNER_TEMP ("line-win-8000-gui-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $script:WorkRoot -Force | Out-Null
    $probe = Join-Path $script:WorkRoot "candidate-probe"
    Expand-Archive -LiteralPath $CandidateZip -DestinationPath $probe -Force
    $candidateRoot = Join-Path $probe "LINE自動發訊息_Windows候選版"
    $exe = Join-Path $candidateRoot "LINE_AutoSender.exe"
    $manifestPath = Join-Path $candidateRoot "CANDIDATE_MANIFEST.json"
    $sbomPath = Join-Path $candidateRoot "SBOM.cdx.json"
    if ((Get-LowerSha256 $exe) -ne $contract.candidate.exe_sha256) { throw "WIN-GUI-HASH-002: EXE hash mismatch" }
    if ((Get-LowerSha256 $manifestPath) -ne $contract.candidate.manifest_sha256) { throw "WIN-GUI-HASH-003: manifest hash mismatch" }
    if ((Get-LowerSha256 $sbomPath) -ne $contract.candidate.sbom_sha256) { throw "WIN-GUI-HASH-004: SBOM hash mismatch" }
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    if ($manifest.status -ne "PRIVATE_UNSIGNED_CANDIDATE_NOT_FOR_DELIVERY" -or
        $manifest.gates.customer_delivery_allowed -ne $false -or
        $manifest.gates.formal_registry_allowed -ne $false -or
        $manifest.gates.protected_download_allowed -ne $false) {
        throw "WIN-GUI-MANIFEST-001: delivery gate is open"
    }

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $script:EnvironmentReadback = [ordered]@{
        user_interactive = [Environment]::UserInteractive
        session_id = (Get-Process -Id $PID).SessionId
        desktop_name = Get-DesktopName
        screen_width = $screen.Width
        screen_height = $screen.Height
        uiautomation_root_available = ([System.Windows.Automation.AutomationElement]::RootElement -ne $null)
    }
    if (!$script:EnvironmentReadback.user_interactive -or $script:EnvironmentReadback.session_id -eq 0 -or
        $script:EnvironmentReadback.desktop_name -ne "Default" -or $screen.Width -lt 800 -or $screen.Height -lt 600) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_NO_INTERACTIVE_DESKTOP" "CAPABILITY_BLOCKED" "Hosted runner lacks a supported interactive Default desktop." $exe
        exit 0
    }
    if (!$script:EnvironmentReadback.uiautomation_root_available) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_UIAUTOMATION_TREE_UNAVAILABLE" "CAPABILITY_BLOCKED" "UIAutomation root is unavailable." $exe
        exit 0
    }
    if ((Get-LineProcesses).Count -ne 0) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_ABORTED_LINE_PROCESS_PRESENT" "SAFETY_ABORT" "A LINE process already exists; no App launch occurred." $exe
        exit 0
    }

    # Replace Python webbrowser with a local no-op executable. It accepts the URL but records nothing,
    # preventing OAuth state, device id or callback values from entering logs or the network.
    $safeBrowser = Join-Path $script:WorkRoot "zero-network-browser.exe"
    Add-Type -TypeDefinition 'using System; using System.IO; public static class Program { public static int Main(string[] args) { string p = Environment.GetEnvironmentVariable("LINE_GUI_SAFE_BROWSER_MARKER"); if (!String.IsNullOrEmpty(p)) File.WriteAllText(p, "invoked"); return 0; } }' `
        -OutputAssembly $safeBrowser -OutputType ConsoleApplication
    $env:BROWSER = ('"' + $safeBrowser + '" %s')
    $browserMarker = Join-Path $script:WorkRoot "safe-browser-invoked.txt"
    $env:LINE_GUI_SAFE_BROWSER_MARKER = $browserMarker
    $isolatedAppData = Join-Path $script:WorkRoot "isolated-appdata"
    New-Item -ItemType Directory -Path $isolatedAppData -Force | Out-Null

    if (!(Start-Candidate $exe $isolatedAppData)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_AUTH_REQUIRED_WINDOW_NOT_OBSERVED" "CAPABILITY_BLOCKED" "The exact EXE did not expose a top-level window." $exe
        exit 0
    }
    Start-Sleep -Seconds 2
    if (!(Test-Path -LiteralPath $browserMarker -PathType Leaf)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_ABORTED_BROWSER_STUB_NOT_INVOKED" "SAFETY_ABORT" "Python webbrowser did not invoke the zero-network stub; stopped before continuing." $exe
        exit 0
    }
    $names = Get-ElementNames $script:Process.Id
    if ($names -contains "建立預覽並最後確認") {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_ABORTED_UNEXPECTED_AUTHENTICATED_MAIN_WINDOW" "SAFETY_ABORT" "Main window appeared in capability-only mode; stopped before input." $exe
        exit 0
    }
    $authVisible = (($names | Where-Object { $_ -like "*請先登入成交聯盟*" }).Count -gt 0) -or
        (($names | Where-Object { $_ -like "*開啟成交聯盟登入*" }).Count -gt 0)
    if (!$authVisible) {
        Save-Screen "01-auth-required-not-observed.png"
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_UIAUTOMATION_TREE_UNAVAILABLE" "CAPABILITY_BLOCKED" "Tk UI rendered but expected auth controls were not exposed to UIAutomation." $exe
        exit 0
    }
    $script:Observations.auth_required_window_visible = $true
    Save-Screen "01-auth-required.png"
    Stop-Candidate
    $script:Observations.cancel_by_closing_app = $true
    Remove-Item -LiteralPath $browserMarker -Force -ErrorAction SilentlyContinue

    if (!(Start-Candidate $exe $isolatedAppData)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_AUTH_REQUIRED_WINDOW_NOT_OBSERVED" "CAPABILITY_BLOCKED" "Relaunch did not expose a top-level window." $exe
        exit 0
    }
    Start-Sleep -Seconds 2
    if (!(Test-Path -LiteralPath $browserMarker -PathType Leaf)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_ABORTED_BROWSER_STUB_NOT_INVOKED" "SAFETY_ABORT" "Retry did not invoke the zero-network browser stub." $exe
        exit 0
    }
    $retryNames = Get-ElementNames $script:Process.Id
    $retryVisible = (($retryNames | Where-Object { $_ -like "*請先登入成交聯盟*" }).Count -gt 0) -or
        (($retryNames | Where-Object { $_ -like "*開啟成交聯盟登入*" }).Count -gt 0)
    if (!$retryVisible) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_AUTH_REQUIRED_WINDOW_NOT_OBSERVED" "CAPABILITY_BLOCKED" "Auth-required retry was not observable after relaunch." $exe
        exit 0
    }
    $script:Observations.retry_by_relaunching_same_exe = $true
    Save-Screen "02-auth-required-retry.png"

    if ($Mode -eq "CapabilityOnly") {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_PASS_AUTH_REQUIRED_ONLY" "CAPABILITY_PASS_GUI_GATE_PENDING" "Interactive UIAutomation observed auth-required close and same-hash relaunch; main-window cases remain provider-dependent." $exe
        exit 0
    }

    if (!$contract.lanes.provider_dependent_main_window.allowed -or $env:LINE_WINDOWS_STAGING_OAUTH_READY -ne "1") {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_PROVIDER_IDENTITY_REQUIRED" "CAPABILITY_BLOCKED" "Main-window no-send requires a separately approved fresh staging browser identity; no bypass is allowed." $exe
        exit 0
    }

    # This lane is intentionally unreachable under the current contract. If separately authorized,
    # the exact app must naturally reach the main window through OAuth PKCE before these UIA actions.
    if (!(Wait-ForName $script:Process.Id "建立預覽並最後確認" 120)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_PROVIDER_IDENTITY_REQUIRED" "CAPABILITY_BLOCKED" "Authorized main window was not reached naturally." $exe
        exit 0
    }
    $start = Find-Element $script:Process.Id "建立預覽並最後確認" "Button"
    if (!$start -or !(Invoke-UIAElement $start)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_TK_UIA_PATTERN_UNAVAILABLE" "CAPABILITY_BLOCKED" "Preview button lacks an invokable UIAutomation pattern." $exe
        exit 0
    }
    if (!(Wait-ForName $script:Process.Id "請輸入要發送的文字內容" 5)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_TK_UIA_PATTERN_UNAVAILABLE" "CAPABILITY_BLOCKED" "Blank-input rejection was not exposed to UIAutomation." $exe
        exit 0
    }
    $script:Observations.blank_input_rejected = $true
    Save-Screen "03-blank-input-rejected.png"
    $ok = Find-Element $script:Process.Id "確定" "Button"
    if (!$ok) { $ok = Find-Element $script:Process.Id "OK" "Button" }
    if (!$ok -or !(Invoke-UIAElement $ok)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_TK_UIA_PATTERN_UNAVAILABLE" "CAPABILITY_BLOCKED" "Blank warning could not be dismissed through UIAutomation." $exe
        exit 0
    }
    $edits = @(Get-AppElements $script:Process.Id | Where-Object {
        try { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit } catch { $false }
    } | Sort-Object { try { -1 * $_.Current.BoundingRectangle.Height } catch { 0 } })
    if ($edits.Count -eq 0 -or !(Set-UIAValue $edits[0] $contract.safety.deidentified_fixture_text)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_TK_UIA_PATTERN_UNAVAILABLE" "CAPABILITY_BLOCKED" "Message edit control lacks a writable ValuePattern." $exe
        exit 0
    }
    $script:Observations.deidentified_input_entered = $true
    Save-Screen "04-deidentified-input.png"
    if (!(Invoke-UIAElement $start) -or !(Wait-ForName $script:Process.Id "這是最後確認" 5)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_TK_UIA_PATTERN_UNAVAILABLE" "CAPABILITY_BLOCKED" "Preview dialog was not exposed to UIAutomation." $exe
        exit 0
    }
    $script:Observations.preview_visible = $true
    Save-Screen "05-preview-visible-before-cancel.png"
    $cancel = Find-Element $script:Process.Id "取消" "Button"
    if (!$cancel) { $cancel = Find-Element $script:Process.Id "Cancel" "Button" }
    if (!$cancel -or !(Invoke-UIAElement $cancel)) {
        Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_TK_UIA_PATTERN_UNAVAILABLE" "CAPABILITY_BLOCKED" "Preview cancel control lacks an invokable UIAutomation pattern." $exe
        exit 0
    }
    $script:Observations.preview_cancelled = $true
    Save-Screen "06-preview-cancelled.png"
    Write-Result "GITHUB_HOSTED_WINDOWS_GUI_NO_SEND_PASS" "PASS" "Exact app completed authorized blank/input/preview-cancel without final confirmation." $exe
    exit 0
} catch {
    $detail = [string]$_.Exception.Message
    Write-Result "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_INPUT_REJECTED" "FAIL_INPUT" $detail
    exit 1
} finally {
    Clear-EphemeralState
}
