param(
    [Parameter(Mandatory=$false)] [string]$DnsName = "localhost",
    [Parameter(Mandatory=$false)] [string]$OutputDir = ".\certs",
    [Parameter(Mandatory=$false)] [string]$CertName = "WhisperLiveKit-Dev"
)

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Create a self-signed cert in LocalMachine\My with server authentication EKU
$cert = New-SelfSignedCertificate \
    -DnsName $DnsName \
    -FriendlyName $CertName \
    -CertStoreLocation "Cert:\\LocalMachine\\My" \
    -KeyExportPolicy Exportable \
    -KeyLength 2048 \
    -KeyAlgorithm RSA \
    -Provider "Microsoft Enhanced RSA and AES Cryptographic Provider" \
    -HashAlgorithm SHA256 \
    -NotAfter (Get-Date).AddYears(2) \
    -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.1") # Server Authentication

# Export PFX (with password prompt)
$pfxPath = Join-Path $OutputDir "$CertName.pfx"
$cerPath = Join-Path $OutputDir "$CertName.cer"

$sec = Read-Host -AsSecureString -Prompt "Enter password for PFX export"
Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $sec | Out-Null

# Export CER (public key) for client trust installation
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

Write-Host "Created:" -ForegroundColor Green
Write-Host "  PFX: $pfxPath" -ForegroundColor Green
Write-Host "  CER: $cerPath" -ForegroundColor Green

