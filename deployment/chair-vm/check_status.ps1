param(
    [string]$RepoLinuxPath = "/home/$env:USERNAME/DA_Price_Forecasting_Pipeline_DE_LU_release",
    [string]$TaskPrefix = "DAForecast"
)

$ErrorActionPreference = "Stop"

Write-Host "--- Scheduled tasks ---"
Get-ScheduledTask -TaskName "$TaskPrefix-*" -ErrorAction SilentlyContinue |
    Select-Object TaskName, State |
    Format-Table -AutoSize

Write-Host ""
Write-Host "--- Last task results ---"
Get-ScheduledTask -TaskName "$TaskPrefix-*" -ErrorAction SilentlyContinue |
    ForEach-Object {
        $info = Get-ScheduledTaskInfo -TaskName $_.TaskName
        [PSCustomObject]@{
            TaskName = $_.TaskName
            LastRunTime = $info.LastRunTime
            LastTaskResult = $info.LastTaskResult
            NextRunTime = $info.NextRunTime
        }
    } |
    Sort-Object TaskName |
    Format-Table -AutoSize

Write-Host ""
Write-Host "--- Submission responses from WSL ---"
$bashCommand = "cd '$RepoLinuxPath' && ./deployment/chair-vm/run_scheduled_job.sh status"
wsl.exe bash -lc $bashCommand
