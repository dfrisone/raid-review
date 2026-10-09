$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m unittest discover -s tests -t .
python -m PyInstaller --noconfirm --clean --onefile --name RaidReview `
    --add-data "raidreview/static;raidreview/static" `
    run.py
Write-Host "Built dist\RaidReview.exe"
