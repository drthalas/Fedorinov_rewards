param(
    [string]$Filename = 'desktop-current.png'
)

$ErrorActionPreference = 'Stop'
$state = Join-Path $env:LOCALAPPDATA 'FedorinovGate\PhysicalGui'
$target = Join-Path $state $Filename
New-Item -ItemType Directory -Path $state -Force | Out-Null

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size)
    $bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}

[ordered]@{
    path = $target
    bytes = (Get-Item $target).Length
    sha256 = (Get-FileHash $target -Algorithm SHA256).Hash
    captured_at = (Get-Date).ToString('o')
} | ConvertTo-Json -Compress
