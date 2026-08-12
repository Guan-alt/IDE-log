# 重启 OTA 测试平台开发服务
# 用法: 右键 -> 使用 PowerShell 运行, 或在终端执行: .\restart.ps1

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host "=== OTA 测试平台服务重启 ===" -ForegroundColor Cyan

# 1. 停止打包 exe（防止占用端口）
Write-Host "[1/4] 检查打包 exe..." -ForegroundColor Yellow
$exes = Get-Process "OTA-Test-Platform" -ErrorAction SilentlyContinue
if ($exes) {
    $exes | Stop-Process -Force
    Write-Host "  已停止 $($exes.Count) 个 exe 进程" -ForegroundColor Green
    Start-Sleep -Seconds 2
} else {
    Write-Host "  无 exe 进程" -ForegroundColor Gray
}

# 2. 停止 python 开发服务
Write-Host "[2/4] 停止 python 服务..." -ForegroundColor Yellow
$py = Get-Process python -ErrorAction SilentlyContinue
if ($py) {
    $py | Stop-Process -Force
    Write-Host "  已停止 python 进程" -ForegroundColor Green
    Start-Sleep -Seconds 1
} else {
    Write-Host "  无 python 进程" -ForegroundColor Gray
}

# 3. 启动开发服务
Write-Host "[3/4] 启动开发服务..." -ForegroundColor Yellow
Start-Process -FilePath python -ArgumentList "app.py" -WorkingDirectory $ProjectDir -WindowStyle Minimized

# 4. 等待并验证
Write-Host "[4/4] 等待服务启动..." -ForegroundColor Yellow
$ok = $false
for ($i = 1; $i -le 8; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/' -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
    Write-Host "  等待中... ($i)" -ForegroundColor Gray
}

if ($ok) {
    Write-Host ""
    Write-Host "=== 重启成功 ===" -ForegroundColor Green
    Write-Host "服务地址: http://127.0.0.1:5000" -ForegroundColor Green
    Write-Host "按任意键退出..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
} else {
    Write-Host ""
    Write-Host "=== 启动失败 ===" -ForegroundColor Red
    Write-Host "请检查 app.py 是否有错误" -ForegroundColor Red
    Write-Host "按任意键退出..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
}
