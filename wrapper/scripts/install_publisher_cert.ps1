param(
    [Parameter(Mandatory=$false)]
    [string]$CerPath = "Publisher.cer"
)

function Ensure-Admin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "Re-launching with Administrator privileges..." -ForegroundColor Yellow
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = "powershell.exe"
        $psi.Arguments = "-ExecutionPolicy Bypass -File `"$PSCommandPath`" -CerPath `"$CerPath`""
        $psi.Verb = "runas"
        try { [System.Diagnostics.Process]::Start($psi) | Out-Null } catch { throw }
        exit
    }
}

Ensure-Admin

if (-not (Test-Path -LiteralPath $CerPath)) {
    Write-Error "CER file not found: $CerPath"
    exit 1
}

Write-Host "Installing publisher certificate to 'Trusted People' (Local Machine)..." -ForegroundColor Cyan
certutil -addstore -f "TrustedPeople" "$CerPath"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to import certificate to Trusted People."
    exit $LASTEXITCODE
}

Write-Host "Done. You can now install the MSIX package signed by this publisher." -ForegroundColor Green

