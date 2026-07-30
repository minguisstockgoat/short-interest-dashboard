# 대시보드 로컬 서버 (http://127.0.0.1:8765)
#   powershell -ExecutionPolicy Bypass -File .\serve.ps1
$web = Join-Path $PSScriptRoot "web"
Write-Host ""
Write-Host "  대시보드: http://127.0.0.1:8765/"
Write-Host "  종료: Ctrl+C"
Write-Host ""
py -m http.server 8765 --directory $web --bind 127.0.0.1
