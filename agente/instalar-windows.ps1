# Instala o agente do Pula Anúncio no Windows.
# Roda escondido (pythonw), sobe sozinho quando o usuário entra no Windows e volta se cair.
# Use o instalar-windows.bat (dois cliques), que abre este script como administrador.
#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"
$pasta = $PSScriptRoot
$nome = "Pula Anuncio"

function Sair($msg) { Write-Host $msg -ForegroundColor Red; Read-Host "Enter para fechar"; exit 1 }

# 1) Python
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw -or $pythonw -like "*WindowsApps*") {
    Sair "Python não encontrado. Instale em https://python.org marcando 'Add python.exe to PATH' e rode de novo."
}

# 2) Usuário que está usando o PC (o agente precisa da tela dele para mexer no mouse)
$usuario = (Get-CimInstance Win32_ComputerSystem).UserName
if (-not $usuario) { $usuario = "$env:USERDOMAIN\$env:USERNAME" }

# 3) Tarefa agendada: ao entrar no Windows, sem limite de tempo, reinicia se cair
Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -like "*agente.py*" } |
    Stop-Process -Force
$acao = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$pasta\agente.py`"" -WorkingDirectory $pasta
$gatilho = New-ScheduledTaskTrigger -AtLogOn -User $usuario
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$quem = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $config -Principal $quem -Force | Out-Null
Write-Host "Tarefa '$nome' criada para $usuario" -ForegroundColor Green

# 4) Firewall: libera a porta 8765 só para a rede local
Get-NetFirewallRule -DisplayName $nome -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $nome -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow `
    -Profile Any -RemoteAddress LocalSubnet | Out-Null
Write-Host "Porta 8765 liberada para a rede local" -ForegroundColor Green

# 5) mDNS: deixa o celular achar este PC por NOME.local mesmo em rede marcada como "Pública"
Get-NetFirewallRule -DisplayName "$nome (nome .local)" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "$nome (nome .local)" -Direction Inbound -Protocol UDP -LocalPort 5353 `
    -Action Allow -Profile Any -RemoteAddress LocalSubnet | Out-Null
Write-Host "Nome $($env:COMPUTERNAME.ToLower()).local liberado na rede local" -ForegroundColor Green

# 6) Liga agora e confere
Start-ScheduledTask -TaskName $nome
Start-Sleep -Seconds 4
try {
    Invoke-RestMethod http://127.0.0.1:8765/status -TimeoutSec 5 | Out-Null
    $ips = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -eq "Dhcp" }).IPAddress -join ", "
    $local = "$($env:COMPUTERNAME.ToLower()).local"
    Write-Host "`nPronto! Agente rodando. No celular, cadastre esta máquina como:" -ForegroundColor Green
    Write-Host "   $local   (funciona mesmo se o IP mudar)" -ForegroundColor Green
    Write-Host "   ou pelo IP: $ips" -ForegroundColor Green
} catch {
    Write-Host "`nA tarefa foi criada, mas o agente não respondeu. Teste rodando 'python agente.py' nesta pasta para ver o erro." -ForegroundColor Yellow
}
Read-Host "Enter para fechar"
