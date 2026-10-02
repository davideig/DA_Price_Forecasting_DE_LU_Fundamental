param(
    [string]$RepoLinuxPath = "/home/$env:USERNAME/DA_Price_Forecasting_Pipeline_DE_LU_release",
    [string]$TaskPrefix = "DAForecastCutoff",
    [switch]$WhatIfOnly
)

$ErrorActionPreference = "Stop"

$obsoleteTasks = @(
    "$TaskPrefix-price-cutoff-1200-compute",
    "$TaskPrefix-dwd-run00-update",
    "$TaskPrefix-renewable-run00-features-update"
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
    @{ Name = "dwd-run03-update"; Time = "06:21"; Job = "dwd-run03-update"; DurationHours = 2 },
    @{ Name = "renewable-run03-features-update"; Time = "06:24"; Job = "renewable-run03-features-update"; DurationHours = 2 },
    @{ Name = "price-cutoff-0700-submit"; Time = "06:40"; Job = "price-cutoff-0700-submit"; DurationHours = 2 },
    @{ Name = "price-cutoff-0800-submit"; Time = "07:40"; Job = "price-cutoff-0800-submit"; DurationHours = 2 },
    @{ Name = "reserve-publication-poll"; Time = "07:55"; Job = "reserve-publication-poll"; DurationHours = 4 },
    @{ Name = "price-cutoff-0900-submit"; Time = "08:40"; Job = "price-cutoff-0900-submit"; DurationHours = 2 },
    @{ Name = "dwd-run06-cutoff-update"; Time = "09:23"; Job = "dwd-run06-cutoff-update"; DurationHours = 2 },
    @{ Name = "renewable-cutoff-features-update"; Time = "09:38"; Job = "renewable-cutoff-features-update"; DurationHours = 2 },
    @{ Name = "price-cutoff-1000-submit"; Time = "09:40"; Job = "price-cutoff-1000-submit"; DurationHours = 2 },
    @{ Name = "price-cutoff-1100-submit"; Time = "10:40"; Job = "price-cutoff-1100-submit"; DurationHours = 2 },
    @{ Name = "price-cutoff-1200-submit"; Time = "11:40"; Job = "price-cutoff-1200-submit"; DurationHours = 2 }
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
            -Description "DA Price Forecasting Pipeline cutoff job: $($entry.Job)" `
            -Force | Out-Null
    }
}

Write-Host ""
Write-Host "Done. Inspect tasks with:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskPrefix-*'"
Write-Host ""
Write-Host "Run one manually, for example:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskPrefix-price-cutoff-1200-submit'"
