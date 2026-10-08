# Remove o agente do Pula Anúncio do Windows (tarefa agendada e regra do firewall).
#Requires -RunAsAdministrator
$nome = "Pula Anuncio"
Stop-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $nome -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName $nome -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -like "*agente.py*" } |
    Stop-Process -Force
Write-Host "Pula Anúncio removido." -ForegroundColor Green
Read-Host "Enter para fechar"
