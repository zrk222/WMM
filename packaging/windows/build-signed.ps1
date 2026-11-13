# Build on a trusted Windows signing workstation from a reviewed checkout.
# The private key stays in the configured Windows provider.
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('\A[0-9A-Fa-f]{40}\z')]
    [string]$Thumbprint,

    [Parameter(Mandatory)]
    [ValidatePattern('\Ahttps://[A-Za-z0-9.-]+(?::[0-9]+)?(?:/[A-Za-z0-9._/-]*)?\z')]
    [string]$TimestampUrl,

    [Parameter(Mandatory)]
    [string]$SignTool,

    [switch]$MachineStore
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).ProviderPath
$signer = (Resolve-Path -LiteralPath $SignTool).ProviderPath
if ([IO.Path]::GetFileName($signer) -ine 'signtool.exe' -or $signer -match '[$"\r\n%&|<>^]') {
    throw 'Use the full path to Windows SDK signtool.exe.'
}
$store = if ($MachineStore) { 'LocalMachine' } else { 'CurrentUser' }
$certificate = Get-Item -LiteralPath "Cert:\$store\My\$Thumbprint"
if (-not $certificate.HasPrivateKey -or
    '1.3.6.1.5.5.7.3.3' -notin $certificate.EnhancedKeyUsageList.ObjectId) {
    throw 'The selected certificate must have an accessible code-signing key.'
}
$compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
$installer = Join-Path $root 'dist/installer/WMM-Setup.exe'
$launchers = @('WMM.exe', 'WMM-Mission-Control.exe') | ForEach-Object {
    Join-Path $root "dist/desktop/WMM/$_"
}
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
    throw 'Inno Setup 6 compiler is unavailable.'
}
if (Test-Path -LiteralPath $installer) {
    throw 'Use a fresh installer output path; an existing WMM-Setup.exe would obscure build provenance.'
}
foreach ($path in $launchers) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw 'Build the reviewed Windows bundle with --native-window first.'
    }
}

$machine = if ($MachineStore) { ' /sm' } else { '' }
$command = '$q' + $signer + '$q sign /fd SHA256 /td SHA256 /tr ' +
    $TimestampUrl + ' /s My' + $machine + ' /sha1 ' + $Thumbprint + ' $f'
& $compiler '-dWmmByok' "-swmm_byok=$command" (Join-Path $PSScriptRoot 'WMM.iss')
if ($LASTEXITCODE -ne 0) { throw 'Signed installer compilation failed.' }

& $signer verify /q /pa /all /tw $installer
if ($LASTEXITCODE -ne 0) { throw 'Installer signature verification failed.' }
$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne 'Valid' -or
    $signature.SignerCertificate.Thumbprint -ine $Thumbprint -or
    -not $signature.TimeStamperCertificate) {
    throw 'The installer does not carry the expected signer and timestamp.'
}
[ordered]@{
    status = 'INSTALLER_SIGNATURE_VERIFIED'
    signer_thumbprint = $Thumbprint.ToUpperInvariant()
    file = [IO.Path]::GetFileName($installer)
    sha256 = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    installed_uninstaller = 'NOT_RUN'
} | ConvertTo-Json -Depth 4
