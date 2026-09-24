param(
    [string]$RepoLinuxPath = "/home/$env:USERNAME/DA_Price_Forecasting_Pipeline_DE_LU_release",
    [string]$TaskPrefix = "DAForecast",
    [switch]$WhatIfOnly
)

$ErrorActionPreference = "Stop"

$jobs = @(
    @{ Name = "dwd-wind-update"; Time = "10:00"; Job = "dwd-wind-update"; DurationHours = 2 },
    @{ Name = "renewable-wind-warmup"; Time = "10:35"; Job = "renewable-wind-warmup"; DurationHours = 2 },
    @{ Name = "dwd-solar-update"; Time = "10:50"; Job = "dwd-solar-update"; DurationHours = 2 },
    @{ Name = "renewable-solar-submit"; Time = "11:10"; Job = "renewable-solar-submit"; DurationHours = 2 },
    @{ Name = "renewable-wind-submit"; Time = "11:20"; Job = "renewable-wind-submit"; DurationHours = 2 },
    @{ Name = "price-submit"; Time = "11:30"; Job = "price-submit"; DurationHours = 2 },
    @{ Name = "load-point-submit"; Time = "11:35"; Job = "load-point-submit"; DurationHours = 2 },
    @{ Name = "price-deadline-safety-submit"; Time = "11:54"; Job = "price-deadline-safety-submit"; DurationHours = 1 },
    @{ Name = "commit-operational-archive"; Time = "12:25"; Job = "commit-operational-archive"; DurationHours = 2 },
    @{ Name = "backup-operational-artifacts"; Time = "13:15"; Job = "backup-operational-artifacts"; DurationHours = 2 }
)

function New-WslAction {
    param(
        [string]$RepoLinuxPath,
        [string]$Job
    )
    # Keep wsl.exe attached so Task Scheduler tracks the actual job instead of
    # terminating a detached Linux process when the launcher exits.
    $bashCommand = "cd '$RepoLinuxPath' && exec ./deployment/chair-vm/run_scheduled_job.sh '$Job'"
    $argument = "bash -lc `"$bashCommand`""
    New-ScheduledTaskAction -Execute "wsl.exe" -Argument $argument
}

foreach ($entry in $jobs) {
    $taskName = "$TaskPrefix-$($entry.Name)"
    $at = [DateTime]::ParseExact($entry.Time, "HH:mm", $null)
    $action = New-WslAction -RepoLinuxPath $RepoLinuxPath -Job $entry.Job
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours $entry.DurationHours)

    Write-Host "Registering $taskName at $($entry.Time) -> $($entry.Job)"
    if (-not $WhatIfOnly) {
        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Description "DA Price Forecasting Pipeline job: $($entry.Job)" `
            -Force | Out-Null
    }
}

Write-Host ""
Write-Host "Done. Inspect tasks with:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskPrefix-*'"
Write-Host ""
Write-Host "Run one manually, for example:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskPrefix-load-point-submit'"
