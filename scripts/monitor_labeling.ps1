# Monitor labeling progress

$targetFile = "data\race_200_additional_labeled.jsonl"
$expectedLines = 200

Write-Host "=== Monitoring Labeling Progress ===" -ForegroundColor Cyan
Write-Host "Target: $expectedLines texts"
Write-Host "Press Ctrl+C to stop monitoring"
Write-Host ""

$lastCount = 0
$startTime = Get-Date

while ($true) {
    if (Test-Path $targetFile) {
        $currentCount = (Get-Content $targetFile | Measure-Object -Line).Lines
        $elapsed = (Get-Date) - $startTime
        $elapsedStr = "{0:hh\:mm\:ss}" -f $elapsed
        
        if ($currentCount -ne $lastCount) {
            $percent = [math]::Round(($currentCount / $expectedLines) * 100, 1)
            $bar = "=" * [math]::Floor($percent / 2)
            $space = " " * (50 - [math]::Floor($percent / 2))
            
            Write-Host "`r[$bar$space] $percent% ($currentCount/$expectedLines) | Elapsed: $elapsedStr" -NoNewline
            $lastCount = $currentCount
            
            if ($currentCount -ge $expectedLines) {
                Write-Host ""
                Write-Host ""
                Write-Host "✓ Labeling complete!" -ForegroundColor Green
                Write-Host ""
                Write-Host "Next step: Run final balance"
                Write-Host "  .\scripts\final_balance.ps1" -ForegroundColor Yellow
                break
            }
        }
    } else {
        Write-Host "`rWaiting for labeling to start... (Elapsed: $elapsedStr)" -NoNewline
    }
    
    Start-Sleep -Seconds 2
}

