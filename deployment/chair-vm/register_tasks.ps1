param(
    [string]$RepoLinuxPath = "/home/$env:USERNAME/DA_Price_Forecasting_Pipeline_DE_LU_release",
    [string]$TaskPrefix = "DAForecast",
    [switch]$WhatIfOnly
)

$ErrorActionPreference = "Stop"

$obsoleteTasks = @(
    "$TaskPrefix-dwd-wind-update",
    "$TaskPrefix-renewable-wind-warmup",
    "$TaskPrefix-dwd-solar-update",
    "$TaskPrefix-renewable-solar-submit",
    "$TaskPrefix-renewable-wind-submit",
    "$TaskPrefix-price-submit",
    "$TaskPrefix-load-point-submit",
    "$TaskPrefix-price-deadline-safety-submit"
)

foreach ($taskName in $obsoleteTasks) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        Write-Host "Removing obsolete task $taskName"
        if (-not $WhatIfOnly) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
    }
}

$jobs = @(
    @{ Name = "repair-operational-data"; Time = "12:25"; Job = "repair-operational-data"; DurationHours = 3 },
    @{ Name = "commit-operational-archive"; Time = "14:00"; Job = "commit-operational-archive"; DurationHours = 2 },
    @{ Name = "backup-operational-artifacts"; Time = "14:30"; Job = "backup-operational-artifacts"; DurationHours = 2 }
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
Write-Host "  Start-ScheduledTask -TaskName '$TaskPrefix-repair-operational-data'"
