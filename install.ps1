$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Write-Host @'
███████╗███████╗██████╗ ████████╗██╗   ██╗██╗
██╔════╝██╔════╝██╔══██╗╚══██╔══╝██║   ██║██║
█████╗  ███████╗██████╔╝   ██║   ██║   ██║██║
██╔══╝  ╚════██║██╔═══╝    ██║   ██║   ██║██║
███████╗███████║██║        ██║   ╚██████╔╝██║
╚══════╝╚══════╝╚═╝        ╚═╝    ╚═════╝ ╚═╝
'@
$Work = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $Work | Out-Null
$script:Child = $null
function Get-Download([string]$Url, [string]$Output) {
    $Headers = @{}
    if ($Url.StartsWith('https://api.github.com/') -and $env:GITHUB_TOKEN) {
        $Headers.Authorization = "Bearer $env:GITHUB_TOKEN"
    }
    Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $Headers -OutFile $Output
}
function Invoke-Step([string]$Title, [string]$File, [string[]]$CommandArgs) {
    $Out = Join-Path $Work 'stdout.log'
    $Err = Join-Path $Work 'stderr.log'
    $QuotedArgs = ($CommandArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $script:Child = Start-Process -FilePath $File -ArgumentList $QuotedArgs -NoNewWindow -PassThru -RedirectStandardOutput $Out -RedirectStandardError $Err
    $Frames = @('|', '/', '-', '\')
    $Index = 0
    while (-not $script:Child.HasExited) {
        if (-not [Console]::IsOutputRedirected) {
            Write-Host ("`r[{0}] {1}" -f $Frames[$Index % 4], $Title) -NoNewline
        }
        $Index++
        Start-Sleep -Milliseconds 100
        $script:Child.Refresh()
    }
    $script:Child.WaitForExit()
    $Code = $script:Child.ExitCode
    $script:Child = $null
    if ($Code -ne 0) {
        Get-Content $Out, $Err | Write-Host
        throw "$Title fallo con codigo $Code"
    }
    Write-Host "`r[OK] $Title"
}
$OldInstallDir = $env:UV_INSTALL_DIR
# Conserva la politica previa para no alterar la sesion del usuario al terminar.
$OldPythonDownloads = $env:UV_PYTHON_DOWNLOADS
try {
    $Ref = 'main'
    if ($env:ESPTUI_REF) { $Ref = $env:ESPTUI_REF }
    elseif ($env:TUIESP32_REF) { $Ref = $env:TUIESP32_REF }
    $Archive = Join-Path $Work 'source.zip'
    Write-Host '[...] Descargando ESPTUI'
    try { Get-Download "https://github.com/j7j7j7/ESPTUI/archive/refs/heads/$Ref.zip" $Archive }
    catch {
        try { Get-Download "https://api.github.com/repos/j7j7j7/ESPTUI/zipball/$Ref" $Archive }
        catch { throw 'No se pudo descargar el repositorio ESPTUI.' }
    }
    $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($UvCommand) { $Uv = $UvCommand.Source }
    else {
        $UvScript = Join-Path $Work 'uv.ps1'
        Get-Download 'https://astral.sh/uv/install.ps1' $UvScript
        $env:UV_INSTALL_DIR = Join-Path $HOME '.local\bin'
        Invoke-Step 'Instalando uv' (Get-Process -Id $PID).Path @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $UvScript)
        $Uv = Join-Path $env:UV_INSTALL_DIR 'uv.exe'
    }
    # Habilita la descarga automatica de Python mediante la variable soportada.
    $env:UV_PYTHON_DOWNLOADS = 'automatic'
    Invoke-Step 'Preparando Python y dependencias' $Uv @('tool', 'install', '--python', '3.12', '--force', '--reinstall', $Archive)
    Invoke-Step 'Configurando PATH' $Uv @('tool', 'update-shell')
    $Bin = (& $Uv tool dir --bin).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo localizar el comando instalado.' }
    & (Join-Path $Bin 'esptui.exe') --version
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la verificacion del comando.' }
    Write-Host 'Listo. Reabre la terminal y ejecuta: esptui (o tuiesp32)'
    Write-Host 'Actualiza repitiendo el instalador. Desinstala con: uv tool uninstall esptui'
}
finally {
    if ($script:Child -and -not $script:Child.HasExited) { $script:Child.Kill() }
    $env:UV_INSTALL_DIR = $OldInstallDir
    # Restaura tambien la politica de descarga incluso si la instalacion falla.
    $env:UV_PYTHON_DOWNLOADS = $OldPythonDownloads
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
