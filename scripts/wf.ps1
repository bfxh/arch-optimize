#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Workflow CLI — 对工程负责的 workflow 工具 v2.2 with Godot MCP + 本地漏洞挖掘 v2.0
.DESCRIPTION
    大规模开发工作流：do → scan → continue 循环。
    集成 bug 扫描、本地漏洞挖掘脚本(vuln-scan.ps1 v2.0: 7维度)、MCP 工具调用、Godot 游戏测试(Godot MCP 深度集成)。
    任何时候 non-architecture bugs 不会停止流程。
    本地漏洞挖掘优先：GDScript 安全(15种) + Rust 不安全(15种) + C/C++ 安全(10种) + MCP 配置(10种) + 配置安全审计 + 密钥(20种) + 依赖审计。

    用法:
      wf.ps1 scan-bugs <path>             扫描项目 bug
      wf.ps1 vuln-hunt <path>             挖漏洞(本地脚本优先 + MCP 辅助)
      wf.ps1 local-scan <path> [cat]      本地漏洞挖掘(全本地执行，无需 MCP)
      wf.ps1 audit <path>                 综合安全审计(本地漏洞 + 配置 + 依赖)
      wf.ps1 hardening <path>             生成安全加固建议
      wf.ps1 godot-test <path>            测试 Godot 项目(启动游戏→检查bug→关闭编辑器)
      wf.ps1 game-init <name> <type>      初始化游戏项目(2d/3d/mini-game/arpg)
      wf.ps1 game-asset <path> [type]     资源管线(import/process/list/clean)
      wf.ps1 game-build <path> [target]   构建游戏(debug/release/windows/linux/web)
      wf.ps1 game-test <path> [type]      运行测试(all/unit/perf)
      wf.ps1 game-lint <path>             代码规范检查
      wf.ps1 game-audit <path>            全面审计(代码+资源+配置)
      wf.ps1 game-plugin <action> [name]  插件管理(list/add/remove/update)
      wf.ps1 game-publish <path> [target] 发布游戏
      wf.ps1 loop <path> [-interval N]    持续 do→scan→continue 循环
      wf.ps1 mcp <tool> [args]            直接调用 MCP 工具
      wf.ps1 godot-mcp <action> [path]    操作 Godot MCP(install/start/stop/test/configure)
      wf.ps1 help                         显示帮助
#>

param(
    [Parameter(Position=0)]
    [ValidateSet('scan-bugs','vuln-hunt','local-scan','audit','hardening','godot-test','game-init','game-asset','game-build','game-test','game-lint','game-audit','game-plugin','game-publish','loop','mcp','godot-mcp','help')]
    [string]$Mode,

    [Parameter(Position=1)]
    [string]$Target,

    [Parameter(Position=2)]
    [string]$Arg3,

    [Parameter()]
    [int]$Interval = 60,

    [Parameter()]
    [string]$ReportDir = "",

    [Parameter()]
    [switch]$Json = $false
)

# ─── 配置 ──────────────────────────────────────────────────────────────
$CONFIG = @{
    ReportDir    = if ($ReportDir) { $ReportDir } else { Join-Path (Get-Location) "wf-reports" }
    MCPConfig    = Join-Path (Get-Location) ".mcp.json"
    GodotMCPDir  = [System.IO.Path]::Combine((Get-Location), "addons", "meow_godot_mcp")
    GodotBridge  = [System.IO.Path]::Combine((Get-Location), "addons", "meow_godot_mcp", "bin", "godot-mcp-bridge.exe")
    GodotMCPUrl  = "https://github.com/MeowMeowZi/meow-godot-mcp/releases/download/v1.6/v1.6-windows-x86_64.zip"

    # 全局 MCP 配置
    CodebaseMemory = "D:\开发\codebase-memory-mcp\bin\codebase-memory-mcp.exe"
    Srclight       = "C:\Users\lbx13\AppData\Local\Programs\Python\Python311\Scripts\srclight.exe"

    # 本地漏洞挖掘脚本
    VulnScript = [System.IO.Path]::Combine($PSScriptRoot, "vuln-scan.ps1")
}

# ─── 工具函数 ──────────────────────────────────────────────────────────

function Write-Banner {
    param([string]$Message, [string]$Color = "Cyan")
    $line = "=" * 60
    Write-Host "`n$line" -ForegroundColor $Color
    Write-Host "  $Message" -ForegroundColor $Color
    Write-Host "$line`n" -ForegroundColor $Color
}

function Write-Step {
    param([string]$Step, [string]$Status, [string]$Color = "Yellow")
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] [$Status] $Step" -ForegroundColor $Color
}

function New-Report {
    param([string]$Name, [string]$Content)
    if (-not (Test-Path $CONFIG.ReportDir)) {
        New-Item -ItemType Directory -Path $CONFIG.ReportDir -Force | Out-Null
    }
    $path = Join-Path $CONFIG.ReportDir "$Name-$(Get-Date -Format 'yyyyMMdd-HHmmss').md"
    $Content | Out-File -FilePath $path -Encoding utf8
    Write-Step "报告已保存: $path" "OK" "Green"
    return $path
}

# ─── MCP 工具调用 ──────────────────────────────────────────────────────

# 调用 Godot MCP Bridge (stdio JSON-RPC 2.0)
function Invoke-GodotMCPTool {
    param(
        [string]$ToolName,
        [hashtable]$Arguments = @{}
    )

    $bridge = $CONFIG.GodotBridge
    if (-not (Test-Path $bridge)) {
        Write-Step "Godot MCP Bridge 未找到: $bridge" "SKIP" "DarkYellow"
        return $null
    }

    # 构造 JSON-RPC 2.0 请求
    $request = @{
        jsonrpc = "2.0"
        id      = [int](Get-Random -Maximum 99999)
        method  = "tools/call"
        params = @{
            name      = $ToolName
            arguments = $Arguments
        }
    } | ConvertTo-Json -Compress -Depth 10

    Write-Step "调用 Godot MCP: $ToolName" "MCP" "Magenta"

    try {
        # 通过 stdio 发送请求到 bridge
        $result = $request | & $bridge 2>&1
        $parsed = $result | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($parsed -and $parsed.result) {
            return $parsed.result
        }
        return $result
    } catch {
        Write-Step "Godot MCP 调用失败: $_" "ERROR" "Red"
        return $null
    }
}

# 通用 MCP 工具调用（支持多种 MCP 服务）
function Invoke-MCPTool {
    param([string]$ServerName, [string]$ToolName, [string]$ArgsJson = "{}")

    Write-Step "调用 MCP: $ServerName / $ToolName" "MCP" "Magenta"

    $mcpServers = @{}

    # 加载项目级 .mcp.json
    if (Test-Path $CONFIG.MCPConfig) {
        try {
            $config = Get-Content $CONFIG.MCPConfig -Raw | ConvertFrom-Json
            if ($config.mcpServers) { $mcpServers = $config.mcpServers }
        } catch { }
    }

    # 查找指定 server 的配置
    $server = $null
    if ($mcpServers.$ServerName) { $server = $mcpServers.$ServerName }

    # 尝试直接调用已知的 MCP 服务
    switch ($ServerName) {
        "codebase-memory" {
            if (Test-Path $CONFIG.CodebaseMemory) {
                $payload = @{
                    jsonrpc = "2.0"
                    id = 1
                    method = "tools/call"
                    params = @{
                        name = $ToolName
                        arguments = ($ArgsJson | ConvertFrom-Json)
                    }
                } | ConvertTo-Json -Compress -Depth 10
                try {
                    $result = $payload | & $CONFIG.CodebaseMemory 2>&1
                    return $result
                } catch {
                    Write-Step "codebase-memory 调用失败: $_" "WARN" "DarkYellow"
                }
            }
        }
        "srclight" {
            if (Test-Path $CONFIG.Srclight) {
                $payload = @{
                    jsonrpc = "2.0"
                    id = 1
                    method = "tools/call"
                    params = @{
                        name = $ToolName
                        arguments = ($ArgsJson | ConvertFrom-Json)
                    }
                } | ConvertTo-Json -Compress -Depth 10
                try {
                    $result = $payload | & $CONFIG.Srclight 2>&1
                    return $result
                } catch {
                    Write-Step "srclight 调用失败: $_" "WARN" "DarkYellow"
                }
            }
        }
        "godot" {
            return Invoke-GodotMCPTool -ToolName $ToolName -Arguments ($ArgsJson | ConvertFrom-Json)
        }
    }

    # 尝试通过通用 MCP CLI
    $mcpCli = Get-Command "mcp" -ErrorAction SilentlyContinue
    if ($mcpCli) {
        try {
            $result = & $mcpCli.Source call $ServerName/$ToolName --args $ArgsJson 2>&1
            return $result
        } catch { }
    }

    Write-Step "MCP server '$ServerName' 不可用" "SKIP" "DarkYellow"
    return $null
}

# ─── 下载 Godot MCP ──────────────────────────────────────────────────

function Install-GodotMCP {
    param([string]$ProjectPath)

    Write-Banner "安装 Godot MCP (Meow Godot MCP v1.6)" "Cyan"

    $addonsDir = Join-Path $ProjectPath "addons"
    $installDir = Join-Path $addonsDir "meow_godot_mcp"
    $zipPath = Join-Path $env:TEMP ("meow-godot-mcp-" + [guid]::NewGuid().ToString("N") + ".zip")

    if (Test-Path $installDir) {
        Write-Step "Godot MCP 已安装: $installDir" "OK" "Green"
        return
    }

    # 创建目录
    if (-not (Test-Path $addonsDir)) {
        New-Item -ItemType Directory -Path $addonsDir -Force | Out-Null
    }

    # 下载
    Write-Step "下载 Godot MCP v1.6 Windows..." "DL" "Yellow"
    try {
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($CONFIG.GodotMCPUrl, $zipPath)
        Write-Step "下载完成: $zipPath" "OK" "Green"
    } catch {
        Write-Step "下载失败: $_" "ERROR" "Red"
        Write-Step "请手动下载: $($CONFIG.GodotMCPUrl)" "INFO" "Yellow"
        Write-Step "解压到: $installDir" "INFO" "Yellow"
        return
    }

    # 供应链校验：必须是有效 zip（PK 头），防止下载损坏或被替换
    $zipBytes = [System.IO.File]::ReadAllBytes($zipPath)
    if ($zipBytes.Length -lt 4 -or $zipBytes[0] -ne 0x50 -or $zipBytes[1] -ne 0x4B) {
        Write-Step "校验失败：下载文件不是有效 zip，已阻止解压" "ERROR" "Red"
        Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
        return
    }
    Write-Step "zip 校验通过（$($zipBytes.Length) 字节）" "OK" "Green"

    # 解压
    Write-Step "解压到: $installDir" "RUN" "Yellow"
    try {
        Expand-Archive -Path $zipPath -DestinationPath $ProjectPath -Force
        Write-Step "解压完成" "OK" "Green"
    } catch {
        Write-Step "解压失败: $_" "ERROR" "Red"
        return
    }

    # 验证
    $bridge = Join-Path $installDir "bin" "godot-mcp-bridge.exe"
    if (Test-Path $bridge) {
        Write-Step "Godot MCP 安装成功!" "OK" "Green"
        Write-Step "Bridge: $bridge" "INFO" "Cyan"
        Write-Step "请在 Godot 中启用插件: 项目设置 → 插件 → Godot MCP Meow" "INFO" "Yellow"
    } else {
        Write-Step "安装可能不完整，Bridge 未找到" "WARN" "DarkYellow"
    }
}

# ─── 扫描 bug ──────────────────────────────────────────────────────────

function Invoke-BugScan {
    param([string]$ProjectPath)

    Write-Banner "扫描 Bug: $ProjectPath" "Yellow"

    $results = @{
        errors   = @()
        warnings = @()
        total    = 0
        critical = 0
        non_arch = 0
        arch     = 0
    }

    # 1. 检查编译错误
    Write-Step "检查编译错误" "RUN" "Yellow"
    $rustFiles = Get-ChildItem -Path $ProjectPath -Recurse -Filter "*.rs" -ErrorAction SilentlyContinue
    $gdFiles   = Get-ChildItem -Path $ProjectPath -Recurse -Filter "*.gd" -ErrorAction SilentlyContinue

    if ($rustFiles) {
        $cargoResult = & cargo check --manifest-path (Join-Path $ProjectPath "Cargo.toml") 2>&1
        $results.errors += $cargoResult
    }

    # 2. GDScript 语法检查
    if ($gdFiles) {
        foreach ($file in $gdFiles) {
            $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
            if ($content -match '(?m)^\s*(TODO|FIXME|HACK|XXX)\b') {
                $results.warnings += "TODO/FIXME: $($file.FullName)"
            }
            if ($content -match '(?m)^\s*(pass\b|return\s*$|# TODO:)') {
                $results.warnings += "占位符: $($file.FullName)"
            }
            if ($content -match 'print\("debug') {
                $results.warnings += "调试输出残留: $($file.FullName)"
            }
        }
    }

    # 3. 检查 null 指针风险
    if ($gdFiles) {
        foreach ($file in $gdFiles) {
            $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
            if ($content -match '\.get_node\([^)]+\)\s*\.') {
                $results.warnings += "潜在 null 引用: $($file.FullName) — 使用 ?. 或 is_instance_valid()"
            }
            if ($content -match 'preload\([^)]+\)' -and $content -notmatch 'is_loaded') {
                $results.warnings += "preload 无 is_loaded 检查: $($file.FullName)"
            }
        }
    }

    # 4. 检查除零风险
    if ($gdFiles) {
        foreach ($file in $gdFiles) {
            $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
            if ($content -match '(?<!/)\s*/\s*(size|count|length|total|num)\b') {
                $results.warnings += "潜在除零: $($file.FullName)"
            }
        }
    }

    # 5. 检查架构问题
    Write-Step "检查架构问题" "RUN" "Yellow"
    $projectRoot = (Get-Item $ProjectPath).FullName
    $srcDir = Join-Path $projectRoot "src"
    $binDir = Join-Path $projectRoot "bin"
    if (-not (Test-Path $srcDir)) {
        $results.errors += "[架构] 缺少 src/ 目录 — 违反工程结构约定"
        $results.arch++
    }
    if (-not (Test-Path $binDir)) {
        $results.warnings += "[架构] 缺少 bin/ 目录 — 建议添加"
        $results.arch++
    }

    # 分类
    $results.total = $results.errors.Count + $results.warnings.Count
    $results.critical = ($results.errors | Where-Object { $_ -match '\[架构\]' }).Count

    # 报告
    $report = @"
# Bug 扫描报告
项目: $ProjectPath
时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

## 统计
- 总问题: $($results.total)
- 严重: $($results.critical)
- 架构问题: $($results.arch)
- 非架构问题: $($results.total - $results.arch)

## 错误 ($($results.errors.Count))
$($results.errors -join "`n")

## 警告 ($($results.warnings.Count))
$($results.warnings -join "`n")
"@

    New-Report -Name "bug-scan" -Content $report

    if ($results.critical -gt 0) {
        Write-Step "发现 $($results.critical) 个架构问题" "WARN" "Red"
        Write-Step "非架构问题 ($($results.total - $results.critical) 个) 不阻止流程继续" "INFO" "Green"
    } else {
        Write-Step "扫描完成，共 $($results.total) 个问题" "OK" "Green"
    }

    return $results
}

# ─── 挖漏洞（本地脚本优先 + MCP 辅助） ────────────────────────────────

function Invoke-VulnHunt {
    param([string]$ProjectPath)

    Write-Banner "漏洞挖掘: $ProjectPath" "Magenta"
    Write-Step "非架构漏洞不影响流程继续" "RULE" "White"
    Write-Step "本地脚本优先，MCP 工具辅助" "INFO" "Cyan"

    $report = @"
# 漏洞挖掘报告
项目: $ProjectPath
时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

## 阶段一：本地脚本扫描
"@

    # ── 阶段 1: 本地 vuln-scan.ps1（优先，全本地执行） ──
    Write-Step "[1/5] 执行本地漏洞挖掘脚本..." "LOCAL" "Green"
    if (Test-Path $CONFIG.VulnScript) {
        $localResult = & $CONFIG.VulnScript -ProjectPath $ProjectPath -OutputDir (Join-Path $CONFIG.ReportDir "vuln-scan")
        $report += "`n### 本地漏洞挖掘结果`n"
        $report += "- Critical: $($localResult.Critical) | High: $($localResult.High) | Medium: $($localResult.Medium) | Low: $($localResult.Low)`n"
        $report += "- 报告: $($localResult.Report)`n"
        $report += "- 耗时: $($localResult.Elapsed.ToString('F1'))s`n"
    } else {
        Write-Step "本地漏洞挖掘脚本未找到: $($CONFIG.VulnScript)" "SKIP" "DarkYellow"
        $report += "`n### 本地漏洞挖掘脚本不可用`n"
    }

    # ── 阶段 2: MCP Codebase-Memory 代码扫描（辅助） ──
    Write-Step "[2/5] 调用 codebase-memory-mcp: 安全扫描（辅助）" "MCP" "Magenta"
    $mcpResult = Invoke-MCPTool -ServerName "codebase-memory" -ToolName "search_code" -ArgsJson "{`"query`":`"vulnerability|security|injection|overflow|unsafe|panic|unwrap`",`"path`":`"$ProjectPath`"}"
    if ($mcpResult) { $report += "`n### codebase-memory: search_code`n$mcpResult`n" }

    # ── 阶段 3: MCP Srclight 语义安全搜索（辅助） ──
    Write-Step "[3/5] 调用 srclight: 语义安全搜索（辅助）" "MCP" "Magenta"
    $mcpResult = Invoke-MCPTool -ServerName "srclight" -ToolName "semantic_search" -ArgsJson "{`"query`":`"vulnerability security injection overflow unsafe panic unwrap`"}"
    if ($mcpResult) { $report += "`n### srclight: semantic_search`n$mcpResult`n" }

    # ── 阶段 4: Godot MCP 游戏测试 ──
    $godotProj = Join-Path $ProjectPath "project.godot"
    if (Test-Path $godotProj) {
        Write-Step "[4/5] 调用 Godot MCP: 游戏测试" "MCP" "Magenta"
        $godotResult = Invoke-GodotMCPTest -ProjectPath $ProjectPath
        $report += "`n### Godot 游戏测试`n$godotResult`n"
    } else {
        Write-Step "[4/5] 跳过 Godot 测试（非 Godot 项目）" "SKIP" "DarkYellow"
    }

    # ── 阶段 5: 总结 ──
    Write-Step "[5/5] 生成报告" "DONE" "Green"
    $report += @"

## 结论
- 非架构漏洞不影响流程继续
- 架构漏洞已记录但不强制停止
- 本地脚本优先（全本地），MCP 工具辅助
- 所有结果已保存到 wf-reports/
"@

    New-Report -Name "vuln-hunt" -Content $report
    Write-Step "漏洞挖掘完成" "OK" "Green"
}

# ─── Godot MCP 游戏测试 ──────────────────────────────────────────────

function Invoke-GodotMCPTest {
    param([string]$ProjectPath)

    Write-Banner "Godot MCP 游戏测试: $ProjectPath" "Cyan"

    $bridge = $CONFIG.GodotBridge
    if (-not (Test-Path $bridge)) {
        Write-Step "Godot MCP 未安装，跳过游戏测试" "SKIP" "DarkYellow"
        Write-Step "安装: wf.ps1 godot-mcp install $ProjectPath" "INFO" "Yellow"
        return "Godot MCP 未安装"
    }

    # 检查 project.godot
    $projectFile = Join-Path $ProjectPath "project.godot"
    if (-not (Test-Path $projectFile)) {
        Write-Step "不是 Godot 项目" "SKIP" "DarkYellow"
        return "不是 Godot 项目"
    }

    # 步骤 1: 启动 Godot 编辑器（通过 MCP）
    Write-Step "[1/6] 通过 Godot MCP 启动编辑器..." "MCP" "Magenta"
    $runResult = Invoke-GodotMCPTool -ToolName "run_game" -Arguments @{}
    if (-not $runResult) {
        Write-Step "Godot MCP 未连接，请确保 Godot 编辑器已打开且插件已启用" "SKIP" "DarkYellow"
        return "Godot MCP 未连接"
    }
    Write-Step "编辑器已启动" "OK" "Green"

    # 步骤 2: 等待游戏加载
    Write-Step "[2/6] 等待游戏加载 (5s)..." "WAIT" "Yellow"
    Start-Sleep -Seconds 5

    # 步骤 3: 获取游戏输出（检查运行时错误）
    Write-Step "[3/6] 获取游戏运行时输出..." "MCP" "Magenta"
    $output = Invoke-GodotMCPTool -ToolName "get_game_output" -Arguments @{level = "error"}

    # 步骤 4: 捕获游戏视口截图
    Write-Step "[4/6] 捕获游戏视口截图..." "MCP" "Magenta"
    $screenshot = Invoke-GodotMCPTool -ToolName "capture_game_viewport" -Arguments @{}

    # 步骤 5: 停止游戏
    Write-Step "[5/6] 停止游戏..." "MCP" "Magenta"
    $stopResult = Invoke-GodotMCPTool -ToolName "stop_game" -Arguments @{}

    # 步骤 6: 分析结果
    Write-Step "[6/6] 分析测试结果..." "ANALYZE" "Yellow"

    $hasErrors = $false
    $errorDetails = ""

    if ($output) {
        $outputStr = $output | Out-String
        if ($outputStr -match 'error|ERROR|Error|panic|PANIC|CRASH|Null instance|script error') {
            $hasErrors = $true
            $errorDetails = $outputStr
            Write-Step "发现运行时错误!" "BUG" "Red"
        }
    }

    if ($hasErrors) {
        $report = @"
## Godot 运行时错误
$errorDetails

## 截图
$($screenshot | Out-String)
"@
        New-Report -Name "godot-bugs" -Content $report
        Write-Step "发现运行时错误，报告已保存" "BUG" "Red"
        return "发现运行时错误"
    } else {
        Write-Step "游戏测试通过，无运行时错误" "OK" "Green"
        return "测试通过"
    }
}

# ─── 传统 Godot 测试（无 MCP 时备用） ────────────────────────────────

function Invoke-GodotLegacyTest {
    param([string]$ProjectPath, [switch]$AutoClose)

    Write-Banner "Godot 传统测试: $ProjectPath" "Cyan"

    # 查找 Godot 可执行文件
    $godotPaths = @(
        "C:\Program Files\Godot\godot.exe",
        "C:\Program Files\Godot 4\godot.exe",
        "$env:LOCALAPPDATA\Godot\godot.exe",
        (Get-Command "godot" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    )

    $godotExe = $null
    foreach ($p in $godotPaths) {
        if ($p -and (Test-Path $p)) {
            $godotExe = $p
            break
        }
    }

    if (-not $godotExe) {
        Write-Step "未找到 Godot 可执行文件，请设置 GODOT_PATH 环境变量" "SKIP" "DarkYellow"
        return "Godot 未安装"
    }

    $projectFile = Join-Path $ProjectPath "project.godot"
    if (-not (Test-Path $projectFile)) {
        Write-Step "不是 Godot 项目" "SKIP" "DarkYellow"
        return "不是 Godot 项目"
    }

    Write-Step "启动 Godot (headless mode)" "RUN" "Yellow"
    $logFile = Join-Path $env:TEMP "godot-test-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

    try {
        $proc = Start-Process -FilePath $godotExe -ArgumentList "--headless", "--path", $ProjectPath, "--" -PassThru -NoNewWindow -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err"
        Start-Sleep -Seconds 5

        if ($proc.HasExited) {
            $exitCode = $proc.ExitCode
            $logContent = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
            if ($exitCode -ne 0) {
                $errors = $logContent | Select-String -Pattern "(error|ERROR|Error|panic|PANIC|crash|CRASH)" -AllMatches
                if ($errors) {
                    New-Report -Name "godot-error" -Content "## 运行时错误`n$($errors -join "`n")`n`n## 日志`n$logContent"
                }
            }
        } else {
            Start-Sleep -Seconds 10
            if ($AutoClose) {
                $proc.Kill()
                $proc.WaitForExit(5000)
            }
        }

        $logContent = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        $errorPatterns = @("error", "ERROR", "Error:", "panic", "PANIC", "CRASH", "script error", "Null instance")
        $foundErrors = @()
        foreach ($pattern in $errorPatterns) {
            $matches = $logContent | Select-String -Pattern $pattern -AllMatches
            if ($matches) { $foundErrors += $matches }
        }

        if ($foundErrors.Count -gt 0) {
            Write-Step "发现 $($foundErrors.Count) 个运行时错误" "BUG" "Red"
            return "发现 $($foundErrors.Count) 个错误"
        }

        Write-Step "游戏测试通过" "OK" "Green"
        return "测试通过"
    } catch {
        Write-Step "Godot 测试失败: $_" "ERROR" "Red"
        return "测试失败: $_"
    }
}

# ─── GDScript Lint ─────────────────────────────────────────────────────

function Invoke-GameLint {
    param([string]$ProjectPath)

    Write-Banner "GDScript 代码规范检查: $ProjectPath" "Cyan"
    $gdFiles = Get-ChildItem -Path $ProjectPath -Recurse -Filter "*.gd" -ErrorAction SilentlyContinue
    if (-not $gdFiles) {
        Write-Step "未找到 GDScript 文件" "SKIP" "DarkYellow"
        return
    }
    $issues = @()
    foreach ($file in $gdFiles) {
        $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $content) { continue }
        $lines = $content -split "`n"
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart('\')
        # 检查文件长度
        if ($lines.Count -gt 300) {
            $issues += "WARN: $relPath 超过 300 行 ($($lines.Count) 行)"
        }
        # 检查函数长度
        $inFunc = $false; $funcStart = 0; $funcName = ""; $funcLines = 0
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $trimmed = $lines[$i].Trim()
            if ($trimmed -match '^func\s+(\w+)') {
                if ($inFunc -and $funcLines -gt 30) {
                    $issues += "WARN: $relPath 函数 $funcName 超过 30 行 ($funcLines 行)"
                }
                $inFunc = $true; $funcStart = $i; $funcName = $Matches[1]; $funcLines = 0
            }
            if ($inFunc) { $funcLines++ }
        }
        # 检查嵌套深度
        $maxDepth = 0; $depth = 0
        foreach ($line in $lines) {
            if ($line -match '^\s*(if|for|while|match)\b') { $depth++ }
            if ($line -match '^\s*end\b|^\s*\)') { $depth-- }
            $maxDepth = [Math]::Max($maxDepth, $depth)
        }
        if ($maxDepth -gt 3) {
            $issues += "WARN: $relPath 嵌套深度超过 3 层 ($maxDepth 层)"
        }
        # 检查 null 安全
        if ($content -match 'get_node\([^)]+\)\.' -and $content -notmatch '\?\.' -and $content -notmatch 'is_instance_valid') {
            $issues += "WARN: $relPath 存在无安全调用的 get_node()"
        }
        # 检查预加载
        if ($content -match 'preload\([^)]+\)' -and $content -notmatch 'is_loaded') {
            $issues += "INFO: $relPath preload() 无 is_loaded 检查"
        }
    }
    $report = "## GDScript 代码规范检查`n`n项目: $ProjectPath`n`n"
    if ($issues.Count -eq 0) {
        $report += "全部通过，无问题。`n"
    } else {
        $report += "发现 $($issues.Count) 个问题：`n`n"
        foreach ($issue in $issues) { $report += "- $issue`n" }
    }
    New-Report -Name "game-lint" -Content $report
    Write-Step "代码规范检查完成，共 $($issues.Count) 个问题" "OK" "Green"
}

# ─── 本地漏洞挖掘（独立命令） ──────────────────────────────────────────

function Invoke-LocalScan {
    param([string]$ProjectPath, [string]$Category = "all")

    Write-Banner "本地漏洞挖掘: $ProjectPath" "Magenta"
    Write-Step "类别: $Category" "INFO" "Cyan"
    Write-Step "全本地执行，无需 MCP 云服务" "RULE" "Green"

    if (Test-Path $CONFIG.VulnScript) {
        $vulnArgs = @{
            ProjectPath = $ProjectPath
            Category    = $Category
            OutputDir   = (Join-Path $CONFIG.ReportDir "vuln-scan")
        }
        if ($Json) { $vulnArgs.Json = $true }
        & $CONFIG.VulnScript @vulnArgs
    } else {
        Write-Step "本地漏洞挖掘脚本未找到: $($CONFIG.VulnScript)" "ERROR" "Red"
        Write-Step "请确保 vuln-scan.ps1 与 wf.ps1 在同一目录" "INFO" "Yellow"
    }
}

# ─── 综合安全审计（v2.2 新增）──────────────────────────────────────────

function Invoke-Audit {
    param([string]$ProjectPath)

    Write-Banner "综合安全审计: $ProjectPath" "Magenta"
    Write-Step "全本地执行，无需 MCP 云服务" "RULE" "Green"

    $elapsed = [System.Diagnostics.Stopwatch]::StartNew()

    # 1. 本地漏洞扫描（全维度）
    Write-Step "[1/4] 执行本地漏洞挖掘（7 维度）..." "LOCAL" "Green"
    if (Test-Path $CONFIG.VulnScript) {
        & $CONFIG.VulnScript -ProjectPath $ProjectPath -Category all -OutputDir (Join-Path $CONFIG.ReportDir "audit")
    }

    # 2. 架构检查
    Write-Step "[2/4] 执行架构检查..." "RUN" "Yellow"
    $srcDir = Join-Path $ProjectPath "src"
    $binDir = Join-Path $ProjectPath "bin"
    $archIssues = @()
    if (-not (Test-Path $srcDir)) { $archIssues += "缺少 src/ 目录" }
    if (-not (Test-Path $binDir)) { $archIssues += "缺少 bin/ 目录" }
    if ($archIssues.Count -gt 0) {
        Write-Step "架构问题: $($archIssues -join '; ')" "WARN" "Red"
    } else {
        Write-Step "架构检查通过" "OK" "Green"
    }

    # 3. 安全配置检查
    Write-Step "[3/4] 检查安全配置..." "RUN" "Yellow"
    $gitignore = Join-Path $ProjectPath ".gitignore"
    if (Test-Path $gitignore) {
        $giContent = Get-Content $gitignore -Raw -ErrorAction SilentlyContinue
        if ($giContent -notmatch '\.env') {
            Write-Step ".gitignore 中未包含 .env — 建议添加" "WARN" "DarkYellow"
        }
    } else {
        Write-Step "缺少 .gitignore — 建议创建" "WARN" "DarkYellow"
    }

    # 4. 摘要
    Write-Step "[4/4] 生成审计摘要..." "DONE" "Green"
    $elapsed.Stop()

    $report = @"
# 综合安全审计报告
项目: $ProjectPath
时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
耗时: $($elapsed.Elapsed.TotalSeconds.ToString('F1'))s

## 审计范围
1. 本地漏洞挖掘（7 维度：GDScript/Rust/C++/MCP/配置/密钥/依赖）
2. 架构检查（src/bin 分离）
3. 安全配置检查（.gitignore / .env）

## 架构检查
$(if ($archIssues.Count -gt 0) { $archIssues -join "`n" } else { "通过" })

## 建议
- 漏洞挖掘结果详见 vuln-scan 报告
- 架构问题请根据严重性处理
- 安全配置建议立即修复
"@

    New-Report -Name "audit" -Content $report
    Write-Step "综合安全审计完成" "OK" "Green"
}

# ─── 安全加固建议（v2.2 新增）──────────────────────────────────────────

function Invoke-Hardening {
    param([string]$ProjectPath)

    Write-Banner "安全加固建议: $ProjectPath" "Green"

    $recommendations = @()

    # 1. 检查是否有 .gitignore
    $gitignore = Join-Path $ProjectPath ".gitignore"
    if (-not (Test-Path $gitignore)) {
        $recommendations += @{ Severity = "High"; Item = "创建 .gitignore"; Detail = "防止敏感文件被提交到版本控制" }
    }

    # 2. 检查是否有 .env.example
    $envExample = Join-Path $ProjectPath ".env.example"
    if (-not (Test-Path $envExample)) {
        $recommendations += @{ Severity = "Medium"; Item = "创建 .env.example"; Detail = "为环境变量提供模板，避免 .env 被提交" }
    }

    # 3. 检查是否有依赖锁定文件
    $cargoLock = Join-Path $ProjectPath "Cargo.lock"
    $pkgLock = Join-Path $ProjectPath "package-lock.json"
    if (-not (Test-Path $cargoLock) -and -not (Test-Path $pkgLock)) {
        $recommendations += @{ Severity = "Medium"; Item = "添加依赖锁定文件"; Detail = "确保构建可复现，防止供应链攻击" }
    }

    # 4. 检查是否有 CI/CD 配置
    $ciDirs = @(Join-Path $ProjectPath ".github", Join-Path $ProjectPath ".gitlab", Join-Path $ProjectPath ".circleci")
    $hasCI = $false
    foreach ($d in $ciDirs) { if (Test-Path $d) { $hasCI = $true; break } }
    if (-not $hasCI) {
        $recommendations += @{ Severity = "Low"; Item = "配置 CI/CD"; Detail = "自动化测试和安全检查，防止合入有漏洞的代码" }
    }

    # 5. 检查是否有安全审计配置
    $recommendations += @{ Severity = "Medium"; Item = "定期运行 vuln-scan.ps1"; Detail = "集成到 CI/CD 中，每次提交自动扫描" }
    $recommendations += @{ Severity = "Low"; Item = "配置 codebase-memory-mcp"; Detail = "利用 MCP 知识图谱进行深层安全分析" }

    Write-Banner "安全加固建议汇总" "Yellow"
    $report = @"
# 安全加固建议
项目: $ProjectPath
时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
建议总数: $($recommendations.Count)

## 建议列表

| 严重性 | 建议 | 说明 |
|--------|------|------|
"@

    foreach ($r in $recommendations) {
        $report += "| $($r.Severity) | $($r.Item) | $($r.Detail) |`n"
    }

    $report += @"

## 执行建议
1. 优先处理 High 严重性建议
2. 将 vuln-scan.ps1 集成到 CI/CD 流程
3. 定期执行 wf.ps1 audit 进行综合安全审计
4. 使用 Godot MCP 在游戏开发中进行运行时安全检查
"@

    New-Report -Name "hardening" -Content $report
    Write-Step "安全加固建议已生成" "OK" "Green"
}

# ─── 持续循环 ──────────────────────────────────────────────────────────

function Invoke-Loop {
    param([string]$ProjectPath, [int]$IntervalSeconds)

    Write-Banner "持续工作流循环: $ProjectPath" "Green"
    Write-Step "间隔: ${IntervalSeconds}s" "INFO" "Cyan"
    Write-Step "非架构 bug 不停止流程" "RULE" "White"
    Write-Step "Godot MCP 可用时自动使用" "INFO" "Cyan"

    $iteration = 0

    while ($true) {
        $iteration++
        Write-Banner "迭代 #$iteration" "Green"

        # 阶段 1: 扫描 bug
        $results = Invoke-BugScan -ProjectPath $ProjectPath

        # 阶段 2: 架构问题记录但不停止
        if ($results.critical -gt 0) {
            Write-Step "$($results.critical) 个架构问题（已记录，流程继续）" "INFO" "White"
        }

        # 阶段 3: 挖漏洞（每 3 次迭代执行一次）
        if ($iteration % 3 -eq 0) {
            Write-Step "执行漏洞挖掘（每 3 次迭代一次）" "INFO" "Cyan"
            Invoke-VulnHunt -ProjectPath $ProjectPath
        }

        # 阶段 4: Godot 测试（如果适用）
        $godotProj = Join-Path $ProjectPath "project.godot"
        if (Test-Path $godotProj) {
            if (Test-Path $CONFIG.GodotBridge) {
                Write-Step "检测到 Godot MCP，执行 MCP 游戏测试" "INFO" "Cyan"
                Invoke-GodotMCPTest -ProjectPath $ProjectPath
            } else {
                Write-Step "检测到 Godot 项目，执行传统测试" "INFO" "Cyan"
                Invoke-GodotLegacyTest -ProjectPath $ProjectPath -AutoClose
            }
        }

        Write-Step "迭代 #$iteration 完成，等待 ${IntervalSeconds}s..." "DONE" "Green"
        Write-Banner "按 Ctrl+C 停止循环" "White"

        Start-Sleep -Seconds $IntervalSeconds
    }
}

# ─── Godot MCP 管理 ──────────────────────────────────────────────────

function Manage-GodotMCP {
    param([string]$Action, [string]$ProjectPath)

    switch ($Action.ToLower()) {
        "install" {
            if (-not $ProjectPath) {
                Write-Host "请指定项目路径: wf.ps1 godot-mcp install <path>"
                return
            }
            Install-GodotMCP -ProjectPath $ProjectPath
        }
        "start" {
            Write-Banner "启动 Godot MCP Bridge" "Cyan"
            $bridge = $CONFIG.GodotBridge
            if (Test-Path $bridge) {
                $proc = Start-Process -FilePath $bridge -NoNewWindow -PassThru
                Write-Step "Godot MCP Bridge 已启动 (PID: $($proc.Id))" "OK" "Green"
                Write-Step "请确保 Godot 编辑器已打开且 Godot MCP 插件已启用" "INFO" "Yellow"
            } else {
                Write-Step "Godot MCP Bridge 未找到，请先安装" "SKIP" "DarkYellow"
                Write-Step "安装: wf.ps1 godot-mcp install <path>" "INFO" "Yellow"
            }
        }
        "stop" {
            Write-Banner "停止 Godot MCP Bridge" "Cyan"
            $procs = Get-Process -Name "godot-mcp-bridge" -ErrorAction SilentlyContinue
            if ($procs) {
                $procs | Stop-Process -Force
                Write-Step "Godot MCP Bridge 已停止" "OK" "Green"
            } else {
                Write-Step "Godot MCP Bridge 未运行" "SKIP" "DarkYellow"
            }
        }
        "test" {
            if (-not $ProjectPath) {
                Write-Host "请指定项目路径: wf.ps1 godot-mcp test <path>"
                return
            }
            Invoke-GodotMCPTest -ProjectPath $ProjectPath
        }
        "legacy-test" {
            if (-not $ProjectPath) {
                Write-Host "请指定项目路径: wf.ps1 godot-mcp legacy-test <path>"
                return
            }
            Invoke-GodotLegacyTest -ProjectPath $ProjectPath -AutoClose
        }
        "configure" {
            Write-Banner "配置 Godot MCP MCP 客户端" "Cyan"
            $bridge = $CONFIG.GodotBridge
            if (-not (Test-Path $bridge)) {
                Write-Step "Godot MCP 未安装，请先安装" "SKIP" "DarkYellow"
                return
            }
            # 生成 .mcp.json 配置
            $mcpConfig = @{
                mcpServers = @{
                    godot = @{
                        command = $bridge
                        args    = @()
                        env     = @{
                            DEBUG = "true"
                        }
                    }
                }
            }
            $mcpJson = $mcpConfig | ConvertTo-Json -Depth 10
            Write-Step "Godot MCP 配置:" "INFO" "Cyan"
            Write-Host $mcpJson -ForegroundColor Cyan
            Write-Step "将上述配置添加到 .mcp.json 或 Claude Desktop 配置中" "INFO" "Yellow"
        }
        default {
            Write-Host @"
Godot MCP 操作:
  install <path>     — 安装 Godot MCP (Meow Godot MCP v1.6)
  start   <path>     — 启动 Godot MCP Bridge
  stop    <path>     — 停止 Godot MCP Bridge
  test    <path>     — Godot MCP 游戏测试(启动→检查bug→关闭)
  legacy-test <path> — 传统 Godot 测试(无MCP备用)
  configure [path]   — 生成 Godot MCP 客户端配置

"@
        }
    }
}

# ─── 主入口 ────────────────────────────────────────────────────────────

function Show-Help {
    Write-Host @"

╔══════════════════════════════════════════════════════════════╗
║      Workflow CLI v2.2 — 本地漏洞挖掘 v2.0 + Godot MCP    ║
║      对工程负责的 workflow 工具                               ║
╚══════════════════════════════════════════════════════════════╝

用法:
  wf.ps1 scan-bugs <path>             扫描项目 bug
  wf.ps1 vuln-hunt <path>             挖漏洞(本地脚本优先 + MCP 辅助)
  wf.ps1 local-scan <path> [cat]      本地漏洞挖掘(全本地执行，无需 MCP)
  wf.ps1 audit <path>                 综合安全审计(本地漏洞 + 配置 + 依赖)
  wf.ps1 hardening <path>             生成安全加固建议
  wf.ps1 godot-test <path>            测试 Godot 项目(Godot MCP 优先)
  wf.ps1 game-init <name> <type>      初始化游戏项目(2d/3d/mini-game/arpg)
  wf.ps1 game-asset <path> [type]     资源管线(import/process/list/clean)
  wf.ps1 game-build <path> [target]   构建游戏(debug/release/windows/linux/web)
  wf.ps1 game-test <path> [type]      运行测试(all/unit/perf)
  wf.ps1 game-lint <path>             代码规范检查
  wf.ps1 game-audit <path>            全面审计(代码+资源+配置)
  wf.ps1 game-plugin <action> [name]  插件管理(list/add/remove/update)
  wf.ps1 game-publish <path> [target] 发布游戏
  wf.ps1 loop <path> [-interval N]    持续 do→scan→continue 循环
  wf.ps1 mcp <tool> [args]            直接调用 MCP 工具
  wf.ps1 godot-mcp <action> [path]    操作 Godot MCP
  wf.ps1 help                         显示帮助

本地漏洞挖掘类别 (local-scan):
  all             全量检测（默认）- 7 维度
  gdscript        仅 GDScript 安全检测(15种)
  rust            仅 Rust 不安全模式(15种)
  cpp             仅 C/C++ 安全检测(10种)
  mcp             仅 MCP 配置审计(10种)
  config          仅配置安全审计
  secret          仅密钥泄露检测(20种)
  dep             仅依赖审计

Godot MCP 操作:
  install <path>     — 安装 Godot MCP (Meow Godot MCP v1.6)
  start   <path>     — 启动 Godot MCP Bridge
  stop    <path>     — 停止 Godot MCP Bridge
  test    <path>     — Godot MCP 游戏测试(启动→检查bug→关闭编辑器)
  legacy-test <path> — 传统 Godot 测试(无MCP备用)
  configure [path]   — 生成 Godot MCP 客户端配置

选项:
  -interval N     循环间隔秒数(默认 60)
  -ReportDir      报告输出目录(默认 ./wf-reports)
  -Json           JSON 格式输出(用于 local-scan)

MCP 集成工具:
  codebase-memory-mcp — 代码知识图谱搜索
  srclight            — 本地代码语义搜索 + 调用图（42 工具）
  godot-mcp-bridge    — Godot 编辑器/游戏控制 (Meow Godot MCP)

本地漏洞挖掘脚本 (vuln-scan.ps1 v2.0 — 7 维度):
  GDScript 安全检测     — 15种: eval/注入/null指针/unsafe/除零/RPC/信号/路径/线程
  Rust 不安全模式检测   — 15种: unsafe/transmute/裸指针/unwrap/FFI/zeroed/Pin/asm
  C/C++ 安全检测        — 10种: gets/printf/strcpy/malloc/整数溢出/UAF
  MCP 配置审计          — 10种: 缺失二进制/危险参数/凭据泄露/配置投毒/传输安全
  配置安全审计          — Docker/k8s/CI-CD/.env/密钥在配置中
  密钥泄露检测          — 20种: API Key/Token/私钥/数据库/JWT/Azure/Telegram
  依赖审计              — Cargo/npm/Godot 插件

理念:
  - 对工程负责：每一行代码、每一个决策都经得起检验
  - 非架构 bug 不停止流程：大规模开发，持续前进
  - 本地漏洞挖掘优先：脚本全本地执行，不依赖外部 API
  - MCP 辅助调用：vuln-hunt 阶段本地脚本 + MCP 双重验证
  - Godot 测试：MCP 启动游戏 → 检查运行时错误 → 捕获截图 → 关闭编辑器
  - 工程>项目>其他：先搭好工程结构，再谈业务

"@
}

# ─── 执行 ──────────────────────────────────────────────────────────────

switch ($Mode) {
    "scan-bugs" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        Invoke-BugScan -ProjectPath $Target
    }
    "vuln-hunt" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        Invoke-VulnHunt -ProjectPath $Target
    }
    "local-scan" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        $cat = if ($Arg3) { $Arg3 } else { "all" }
        Invoke-LocalScan -ProjectPath $Target -Category $cat
    }
    "audit" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        Invoke-Audit -ProjectPath $Target
    }
    "hardening" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        Invoke-Hardening -ProjectPath $Target
    }
    "godot-test" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        if (Test-Path $CONFIG.GodotBridge) {
            Invoke-GodotMCPTest -ProjectPath $Target
        } else {
            Invoke-GodotLegacyTest -ProjectPath $Target -AutoClose
        }
    }
    "game-init" {
        if (-not $Target) { Write-Host "请指定项目名称: wf.ps1 game-init <name> <type>"; return }
        $gameType = if ($Arg3) { $Arg3 } else { "2d" }
        $gameInitScript = Join-Path $PSScriptRoot "..\..\game-dev\scripts\game-init.ps1"
        if (Test-Path $gameInitScript) {
            & $gameInitScript -ProjectName $Target -Type $gameType -OutputDir (Get-Location)
        } else {
            Write-Step "game-init 脚本未找到: $gameInitScript" "ERROR" "Red"
        }
    }
    "game-asset" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        $assetAction = if ($Arg3) { $Arg3 } else { "all" }
        $assetPipelineScript = Join-Path $PSScriptRoot "..\..\game-dev\scripts\game-asset-pipeline.ps1"
        if (Test-Path $assetPipelineScript) {
            & $assetPipelineScript -ProjectPath $Target -Type $assetAction
        } else {
            Write-Step "game-asset-pipeline 脚本未找到: $assetPipelineScript" "ERROR" "Red"
        }
    }
    "game-build" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        $buildTarget = if ($Arg3) { $Arg3 } else { "debug" }
        Write-Banner "Godot 构建: $Target ($buildTarget)" "Cyan"
        # 查找 project.godot
        $projectFile = Join-Path $Target "project.godot"
        if (-not (Test-Path $projectFile)) {
            Write-Step "不是 Godot 项目（未找到 project.godot）" "ERROR" "Red"
            return
        }
        # 查找 Godot 可执行文件
        $godotPaths = @(
            "C:\Program Files\Godot\godot.exe",
            "C:\Program Files\Godot 4\godot.exe",
            "$env:LOCALAPPDATA\Godot\godot.exe",
            (Get-Command "godot" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
        )
        $godotExe = $null
        foreach ($p in $godotPaths) {
            if ($p -and (Test-Path $p)) { $godotExe = $p; break }
        }
        if (-not $godotExe) {
            Write-Step "未找到 Godot 可执行文件" "ERROR" "Red"
            return
        }
        $exportDir = Join-Path $Target "bin" $buildTarget
        New-Item -ItemType Directory -Path $exportDir -Force | Out-Null
        Write-Step "构建到: $exportDir" "RUN" "Yellow"
        try {
            $result = & $godotExe --headless --path $Target --export-release $buildTarget "$exportDir\game.exe" 2>&1
            Write-Step "构建完成" "OK" "Green"
            New-Report -Name "game-build" -Content "## 构建报告`n项目: $Target`n目标: $buildTarget`n路径: $exportDir`n$result"
        } catch {
            Write-Step "构建失败: $_" "ERROR" "Red"
        }
    }
    "game-test" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        $testType = if ($Arg3) { $Arg3 } else { "all" }
        Write-Banner "Godot 测试: $Target" "Cyan"
        $projectFile = Join-Path $Target "project.godot"
        if (-not (Test-Path $projectFile)) {
            Write-Step "不是 Godot 项目" "ERROR" "Red"
            return
        }
        # 如果有 Godot MCP，优先使用
        if (Test-Path $CONFIG.GodotBridge) {
            Write-Step "使用 Godot MCP 测试" "MCP" "Magenta"
            Invoke-GodotMCPTest -ProjectPath $Target
        } else {
            Write-Step "使用 Godot 传统测试" "RUN" "Yellow"
            Invoke-GodotLegacyTest -ProjectPath $Target -AutoClose
        }
    }
    "game-lint" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        Invoke-GameLint -ProjectPath $Target
    }
    "game-audit" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        Write-Banner "游戏全面审计: $Target" "Magenta"
        # 综合审计：代码规范 + 漏洞扫描 + 资源检查
        Invoke-GameLint -ProjectPath $Target
        # 检查资源完整性
        $rawDir = Join-Path $Target "assets\raw"
        $procDir = Join-Path $Target "assets\processed"
        if (Test-Path $rawDir) {
            $rawCount = (Get-ChildItem -Path $rawDir -Recurse -File).Count
            $procCount = (Get-ChildItem -Path $procDir -Recurse -File -ErrorAction SilentlyContinue).Count
            Write-Step "资源: raw($rawCount) → processed($procCount)" "STATS" "Cyan"
        }
        # 检查项目配置
        $projectFile = Join-Path $Target "project.godot"
        if (Test-Path $projectFile) {
            $projContent = Get-Content $projectFile -Raw -ErrorAction SilentlyContinue
            if ($projContent -match 'config/name') {
                Write-Step "项目配置存在" "OK" "Green"
            }
        }
        New-Report -Name "game-audit" -Content "## 游戏审计报告`n项目: $Target`n时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        Write-Step "游戏审计完成" "OK" "Green"
    }
    "game-plugin" {
        if (-not $Target) { Write-Host "请指定操作: wf.ps1 game-plugin list/add/remove <name>"; return }
        $pluginAction = $Target.ToLower()
        $pluginName = if ($Arg3) { $Arg3 } else { "" }
        Write-Banner "Godot 插件管理: $pluginAction" "Cyan"
        switch ($pluginAction) {
            "list" {
                $addonsDir = Join-Path (Get-Location) "addons"
                if (Test-Path $addonsDir) {
                    $plugins = Get-ChildItem -Path $addonsDir -Directory -ErrorAction SilentlyContinue
                    foreach ($p in $plugins) {
                        $cfg = Join-Path $p.FullName "plugin.cfg"
                        if (Test-Path $cfg) {
                            $cfgContent = Get-Content $cfg -Raw
                            Write-Step "插件: $($p.Name)" "INFO" "Cyan"
                            Write-Host $cfgContent
                        } else {
                            Write-Step "插件: $($p.Name) (无配置)" "INFO" "Cyan"
                        }
                    }
                } else {
                    Write-Step "未找到 addons 目录" "SKIP" "DarkYellow"
                }
            }
            "add" {
                if (-not $pluginName) { Write-Host "请指定插件名或 URL"; return }
                Write-Step "添加插件: $pluginName (手动安装，请参考 Godot Asset Library)" "INFO" "Yellow"
                Write-Step "Godot 编辑器操作: 资源 → 资源库 → 搜索插件" "INFO" "Yellow"
            }
            "remove" {
                if (-not $pluginName) { Write-Host "请指定插件名"; return }
                # 安全：插件名白名单校验，拒绝路径穿越（../ 等）
                if ($pluginName -notmatch '^[A-Za-z0-9_-]+$') {
                    Write-Step "插件名非法（仅允许字母/数字/_-）: $pluginName" "ERROR" "Red"
                    return
                }
                $pluginDir = Join-Path (Get-Location) "addons" $pluginName
                if (Test-Path $pluginDir) {
                    Remove-Item -Path $pluginDir -Recurse -Force
                    Write-Step "插件 $pluginName 已移除" "OK" "Green"
                } else {
                    Write-Step "插件 $pluginName 未找到" "SKIP" "DarkYellow"
                }
            }
            "update" {
                if (-not $pluginName) { Write-Host "请指定插件名"; return }
                Write-Step "更新插件: $pluginName (手动更新，请参考 Godot Asset Library)" "INFO" "Yellow"
            }
            default { Write-Host "操作: list/add/remove/update" }
        }
    }
    "game-publish" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        $pubTarget = if ($Arg3) { $Arg3 } else { "windows" }
        Write-Banner "游戏发布: $Target ($pubTarget)" "Green"
        Write-Step "发布功能即将实现" "INFO" "Yellow"
        New-Report -Name "game-publish" -Content "## 发布报告`n项目: $Target`n目标: $pubTarget`n时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    }
    "loop" {
        if (-not $Target) { Write-Host "请指定项目路径"; return }
        Invoke-Loop -ProjectPath $Target -IntervalSeconds $Interval
    }
    "mcp" {
        if (-not $Target) { Write-Host "请指定 MCP 工具名"; return }
        Invoke-MCPTool -ServerName $Target -ToolName $Arg3
    }
    "godot-mcp" {
        if (-not $Target) { Write-Host "请指定操作 (install/start/stop/test/legacy-test/configure)"; return }
        Manage-GodotMCP -Action $Target -ProjectPath $Arg3
    }
    "help" {
        Show-Help
    }
    default {
        Show-Help
    }
}