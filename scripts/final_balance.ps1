# Final balance script to create 20 topics × 5 texts dataset

Write-Host "=== Creating final balanced dataset ===" -ForegroundColor Cyan
Write-Host ""

# Check if labeling is complete
Write-Host "Checking if labeling is complete..." -ForegroundColor Yellow
$labeledFile = "data\race_200_additional_labeled.jsonl"

if (-not (Test-Path $labeledFile)) {
    Write-Host "⚠️  Waiting for labeling to complete: $labeledFile" -ForegroundColor Red
    Write-Host "   Run: python scripts/label_topics_for_sources.py --input data/race_200_additional.jsonl --output data/race_200_additional_labeled.jsonl --topics benchmark/topics_locked.json --model gemini-2.5-flash-lite"
    exit 1
}

# Count lines to verify completion
$lines = (Get-Content $labeledFile | Measure-Object -Line).Lines
Write-Host "Found $lines labeled texts in race_200_additional_labeled.jsonl" -ForegroundColor Green

if ($lines -lt 190) {
    Write-Host "⚠️  Labeling may not be complete (expected ~200 lines, got $lines)" -ForegroundColor Red
    Write-Host "   Please wait for the labeling process to finish"
    exit 1
}

Write-Host ""
Write-Host "✓ Labeling complete, proceeding with balance..." -ForegroundColor Green
Write-Host ""

# Combine all three files and balance
python scripts/balance_topics.py `
    --input data/race_50_combined_balanced.jsonl data/race_100_additional_labeled.jsonl data/race_200_additional_labeled.jsonl `
    --output data/race_final_balanced_20x5.jsonl `
    --per-topic 5 `
    --target-topics 20 `
    --stats-json data/final_balance_stats.json

Write-Host ""
Write-Host "=== Complete ===" -ForegroundColor Cyan

