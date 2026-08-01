#!/usr/bin/env pwsh
<#
.SYNOPSIS
    本地漏洞挖掘脚本 v2.0 — 全本地运行，无需 MCP 云服务
.DESCRIPTION
    覆盖 GDScript 安全(15种)、Rust 不安全模式(15种)、MCP 配置审计(10种)、
    硬编码密钥(20种)、依赖审计、C/C++ 安全检测(10种)、配置安全审计。
    所有检测全部本地执行，不依赖任何外部 API 或云服务。
    支持并行扫描、JSON 输出、排除模式。

    用法:
      vuln-scan.ps1 <project-path> [-OutputDir <dir>] [-Category <cat>] [-Json] [-Exclude <pattern>]
      vuln-scan.ps1 <project-path> -Category gdscript    # 仅 GDScript 检测
      vuln-scan.ps1 <project-path> -Category rust        # 仅 Rust 检测
      vuln-scan.ps1 <project-path> -Category cpp         # 仅 C/C++ 安全检测
      vuln-scan.ps1 <project-path> -Category mcp         # 仅 MCP 配置审计
      vuln-scan.ps1 <project-path> -Category config      # 仅配置安全审计
      vuln-scan.ps1 <project-path> -Category secret      # 仅密钥泄露检测
      vuln-scan.ps1 <project-path> -Category dep         # 仅依赖审计
      vuln-scan.ps1 <project-path> -Category all         # 全量检测（默认）
      vuln-scan.ps1 <project-path> -Json                 # JSON 格式输出
      vuln-scan.ps1 <project-path> -Exclude "test,*.generated.*"  # 排除模式
#>

param(
    [Parameter(Position=0, Mandatory=$true)]
    [string]$ProjectPath,

    [Parameter()]
    [string]$OutputDir = "",

    [Parameter()]
    [ValidateSet('all','gdscript','rust','cpp','mcp','config','secret','dep')]
    [string]$Category = "all",

    [Parameter()]
    [switch]$Json = $false,

    [Parameter()]
    [string]$Exclude = "",

    [Parameter()]
    [int]$Parallelism = 0
)

# ─── 配置 ──────────────────────────────────────────────────────────────
$REPORT_DIR = if ($OutputDir) { $OutputDir } else { Join-Path $ProjectPath "vuln-reports" }
$TIMESTAMP = Get-Date -Format "yyyyMMdd-HHmmss"

# 排除模式列表
$EXCLUDE_PATTERNS = @()
if ($Exclude) {
    $EXCLUDE_PATTERNS = $Exclude -split ',' | ForEach-Object { $_.Trim() }
}
# 默认排除目录
$EXCLUDE_PATTERNS += '.git', 'node_modules', 'target', '.vscode', '.idea', 'bin', 'vuln-reports', 'wf-reports'

# 并行度（默认=CPU 核心数）
if ($Parallelism -le 0) { $Parallelism = [Environment]::ProcessorCount }

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

function New-Finding {
    param([string]$File, [int]$Line, [string]$Severity, [string]$Category, [string]$Description, [string]$CWE = "N/A", [string]$Fix = "")
    return @{
        File        = $File
        Line        = $Line
        Severity    = $Severity
        Category    = $Category
        Description = $Description
        CWE         = $CWE
        Fix         = $Fix
    }
}

function Add-Finding {
    param([string]$File, [int]$Line = 0, [string]$Severity = "Medium", [string]$Category = "general", [string]$Description, [string]$CWE = "N/A", [string]$Fix = "")
    $script:Findings += New-Finding -File $File -Line $Line -Severity $Severity -Category $Category -Description $Description -CWE $CWE -Fix $Fix
}

function New-Report {
    param([string]$Name, [string]$Content)
    if (-not (Test-Path $REPORT_DIR)) {
        New-Item -ItemType Directory -Path $REPORT_DIR -Force | Out-Null
    }
    $path = Join-Path $REPORT_DIR "$Name-$TIMESTAMP.md"
    $Content | Out-File -FilePath $path -Encoding utf8
    Write-Step "报告已保存: $path" "OK" "Green"
    return $path
}

# 检查路径是否应被排除
function Test-Excluded {
    param([string]$Path)
    foreach ($pattern in $EXCLUDE_PATTERNS) {
        if ($Path -match [regex]::Escape($pattern) -or $Path -match $pattern) {
            return $true
        }
    }
    return $false
}

# 并行执行函数（WorkStealer 风格）
function Invoke-Parallel {
    param(
        [scriptblock]$ScriptBlock,
        [array]$InputList,
        [int]$Degree = $Parallelism
    )
    if ($InputList.Count -eq 0) { return }
    if ($Degree -le 1 -or $InputList.Count -lt 2) {
        foreach ($item in $InputList) { & $ScriptBlock $item }
        return
    }

    $jobs = @()
    $chunkSize = [Math]::Max(1, [Math]::Ceiling($InputList.Count / $Degree))
    for ($i = 0; $i -lt $InputList.Count; $i += $chunkSize) {
        $chunk = $InputList[$i..[Math]::Min($i + $chunkSize - 1, $InputList.Count - 1)]
        $jobs += Start-Job -ScriptBlock $ScriptBlock -ArgumentList $chunk
    }
    $jobs | Wait-Job -Timeout 120 | Out-Null
    $results = $jobs | Where-Object { $_.State -eq 'Completed' } | Receive-Job
    $jobs | Remove-Job -Force
    return $results
}

# ─── GDScript 安全检测 ────────────────────────────────────────────────

function Invoke-GDScriptScan {
    param([string]$ProjectPath)

    Write-Banner "GDScript 安全检测" "Green"

    $gdFiles = Get-ChildItem -Path $ProjectPath -Recurse -Filter "*.gd" -ErrorAction SilentlyContinue
    if (-not $gdFiles) {
        Write-Step "未找到 GDScript 文件" "SKIP" "DarkYellow"
        return
    }

    Write-Step "扫描 $($gdFiles.Count) 个 GDScript 文件" "RUN" "Yellow"

    foreach ($file in $gdFiles) {
        $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $content) { continue }
        $lines = $content -split "`n"
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart('\')

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            $lineNum = $i + 1
            $trimmed = $line.Trim()

            # ── 1. eval 执行 ──
            if ($trimmed -match '^\s*eval\(.*\)') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Critical" -Category "gdscript-injection" `
                    -Description "GDScript eval() 动态执行 — 可能导致任意代码执行" `
                    -CWE "CWE-95" -Fix "避免使用 eval()，改用字典映射或状态机替代"
            }

            # ── 2. 字符串拼接执行 ──
            if ($trimmed -match 'execute\(.*\+.*\)' -or $trimmed -match 'exec\(.*\+.*\)') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "gdscript-injection" `
                    -Description "字符串拼接执行命令 — 可能导致命令注入" `
                    -CWE "CWE-78" -Fix "使用数组参数形式代替字符串拼接"
            }

            # ── 3. 不安全的类型转换 ──
            if ($trimmed -match 'as\s+(int|float|bool|string|Vector2|Vector3|Color|Rect2|Transform2D|Transform3D|Plane|Quaternion|AABB|Basis)' -and `
                ($trimmed -match '\.get\(' -or $trimmed -match '\[')) {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "gdscript-unsafe-cast" `
                    -Description "不安全的类型转换 — 类型不匹配时返回 null 导致崩溃" `
                    -CWE "CWE-704" -Fix "使用强制转换前检查类型: is_instance_valid() 或 typeof()"
            }

            # ── 4. get_node 无安全调用 ──
            if ($trimmed -match 'get_node\([^)]+\)\.' -and $trimmed -notmatch 'is_instance_valid' -and $trimmed -notmatch '\?\.') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "gdscript-null" `
                    -Description "get_node() 直接调用 — 节点不存在时返回 null 导致崩溃" `
                    -CWE "CWE-476" -Fix "使用 ?. 安全调用或 is_instance_valid() 检查"
            }

            # ── 5. unsafe 方法 ──
            if ($trimmed -match '\.(free|queue_free)\(\)' -and $lines[$i+1] -and $lines[$i+1] -match '\.') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "gdscript-unsafe" `
                    -Description "free() 后继续访问对象 — Use-After-Free 风险" `
                    -CWE "CWE-416" -Fix "free() 后立即将引用置为 null"
            }

            # ── 6. 硬编码路径 ──
            if ($trimmed -match '"(?:C:|D:|E:|\.\./|/etc|/usr|/var|/tmp|/home|/root|/opt|/mnt|/media|/srv|/sys|/proc|/dev)' -and `
                $trimmed -notmatch 'res://' -and $trimmed -notmatch 'user://') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "gdscript-hardcoded-path" `
                    -Description "硬编码的系统路径 — 跨平台兼容性问题" `
                    -CWE "CWE-22" -Fix "使用 res:// 或 user:// 替代绝对路径"
            }

            # ── 7. 除零风险 ──
            if ($trimmed -match '/(\s*size\s*|\s*count\s*|\s*length\s*|\s*total\s*|\s*num\s*)' -and $trimmed -notmatch 'if' -and $trimmed -notmatch '>') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "gdscript-divzero" `
                    -Description "潜在除零风险 — 变量可能为 0" `
                    -CWE "CWE-369" -Fix "除之前检查除数是否为 0"
            }

            # ── 8. preload 无检查 ──
            if ($trimmed -match 'preload\([^)]+\)' -and $content -notmatch 'is_loaded') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "gdscript-resource" `
                    -Description "preload() 无 is_loaded 检查 — 资源加载失败时崩溃" `
                    -CWE "CWE-754" -Fix "使用 ResourceLoader.load() 并检查返回值"
            }

            # ── 9. 暴露的 RPC ──
            if ($trimmed -match '^remote\s+func\s' -or $trimmed -match '^master\s+func\s' -or $trimmed -match '^puppet\s+func\s') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "gdscript-rpc" `
                    -Description "暴露的 RPC 方法 — 其他客户端可调用" `
                    -CWE "CWE-862" -Fix "确认 RPC 方法需要认证检查，考虑使用 @rpc(\"authority\")"
            }

            # ── 10. 全局变量泄露 ──
            if ($trimmed -match '^extends\s+' -and $i -eq 0) {
                # 检查文件是否有全局变量
                for ($j = 1; $j -lt [Math]::Min($lines.Count, 20); $j++) {
                    if ($lines[$j] -match '^var\s+\w+\s*=' -and $lines[$j] -notmatch 'export' -and $lines[$j] -notmatch '@export') {
                        Add-Finding -File $relPath -Line ($j+1) -Severity "Low" -Category "gdscript-global" `
                            -Description "未导出的全局变量 — 可能泄露内部状态" `
                            -CWE "CWE-200" -Fix "添加 @export 或使用 setter/getter"
                        break
                    }
                }
            }

            # ── 11. 信号连接注入 ──
            if ($trimmed -match 'connect\([^,]+,\s*"[^"]*"\)' -and $trimmed -notmatch '""' -and $trimmed -notmatch '^#') {
                # 检查信号连接是否包含变量
                if ($trimmed -match 'connect\([^,]+,\s*[^",]+\)' -or $trimmed -match '\.connect\("signal",\s*\w+\)') {
                    Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "gdscript-signal" `
                        -Description "信号连接可能使用变量方法名 — 方法名注入风险" `
                        -CWE "CWE-94" -Fix "使用常量字符串作为信号连接目标，避免动态方法名"
                }
            }

            # ── 12. 资源路径遍历 ──
            if ($trimmed -match '(load|preload)\([^)]*\+' -and $trimmed -match 'user_input|get_node|get_parent|name|path') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "gdscript-pathtraversal" `
                    -Description "资源加载使用字符串拼接 — 路径遍历风险" `
                    -CWE "CWE-22" -Fix "对用户输入进行路径验证，使用白名单限制可加载的资源路径"
            }

            # ── 13. @onready 无安全调用 ──
            if ($trimmed -match '@onready\s+var\s+\w+' -and $content -notmatch 'is_instance_valid' -and $content -notmatch 'null') {
                # 检查是否在 _ready 中使用而未有检查
                if ($content -match '_ready\(\)' -and $content -notmatch 'is_inside_tree') {
                    Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "gdscript-onready" `
                        -Description "@onready 变量无 null 检查 — 节点未就绪时访问导致崩溃" `
                        -CWE "CWE-476" -Fix "在 _ready() 中为 @onready 变量添加 is_instance_valid() 检查"
                }
            }

            # ── 14. 属性设置器注入 ──
            # 使用单引号字符串避免转义问题
            $setterRe = 'set\(["\x27]([^"\x27]+)["\x27],\s*[^)]+\)'
            if ($trimmed -match $setterRe -and $trimmed -notmatch '""' -and $trimmed -notmatch '^#') {
                $propName = $Matches[1]
                if ($propName -match 'position|rotation|scale|visible|modulate|name|script') {
                    Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "gdscript-setter-injection" `
                        -Description "set() 动态属性设置 — 属性名可能被用户控制" `
                        -CWE "CWE-94" -Fix "对属性名进行白名单验证，避免设置关键属性"
                }
            }

            # ── 15. 线程不安全共享状态 ──
            if ($trimmed -match 'Thread\.new\(\)|WorkerThreadPool' -and $content -notmatch 'mutex|Mutex|lock|Lock|semaphore|Semaphore') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "gdscript-thread" `
                    -Description "使用线程但缺少 Mutex/Lock 保护 — 竞态条件风险" `
                    -CWE "CWE-362" -Fix "为共享状态添加 Mutex 保护，或使用消息传递模式"
            }
        }
    }

    Write-Step "GDScript 检测完成" "DONE" "Green"
}

# ─── Rust 不安全模式检测 ──────────────────────────────────────────────

function Invoke-RustUnsafeScan {
    param([string]$ProjectPath)

    Write-Banner "Rust 不安全模式检测" "Green"

    $rsFiles = Get-ChildItem -Path $ProjectPath -Recurse -Filter "*.rs" -ErrorAction SilentlyContinue
    if (-not $rsFiles) {
        Write-Step "未找到 Rust 文件" "SKIP" "DarkYellow"
        return
    }

    Write-Step "扫描 $($rsFiles.Count) 个 Rust 文件" "RUN" "Yellow"

    foreach ($file in $rsFiles) {
        $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $content) { continue }
        $lines = $content -split "`n"
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart('\')

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            $lineNum = $i + 1
            $trimmed = $line.Trim()

            # ── 1. unsafe 块 ──
            if ($trimmed -match '^unsafe\s*\{') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-unsafe" `
                    -Description "unsafe 块 — 绕过 Rust 内存安全保证" `
                    -CWE "CWE-119" -Fix "尽量用 safe 抽象替代 unsafe；确保 unsafe 注释说明安全性"
            }

            # ── 2. unsafe 函数 ──
            if ($trimmed -match '^unsafe\s+fn\s') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-unsafe" `
                    -Description "unsafe 函数 — 调用者需保证安全条件" `
                    -CWE "CWE-119" -Fix "添加 Safety 文档注释，说明调用者必须满足的条件"
            }

            # ── 3. transmute ──
            if ($trimmed -match 'transmute[!<]') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Critical" -Category "rust-transmute" `
                    -Description "transmute() — 类型重新解释，极易导致 UB" `
                    -CWE "CWE-704" -Fix "优先使用 transmute_copy/safe 转换/From trait；确保源和目标类型大小一致"
            }

            # ── 4. 裸指针解引用 ──
            if ($trimmed -match '\*const\s' -or $trimmed -match '\*mut\s') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-rawptr" `
                    -Description "裸指针操作 — 可能导致内存安全问题" `
                    -CWE "CWE-822" -Fix "优先使用引用和智能指针，只在 FFI 边界使用裸指针"
            }

            # ── 5. unwrap() 无检查 ──
            if ($trimmed -match '\.unwrap\(\)' -and $trimmed -notmatch '//\s*safe' -and $trimmed -notmatch '//\s*known') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "rust-unwrap" `
                    -Description "unwrap() 无错误处理 — 失败时直接 panic" `
                    -CWE "CWE-754" -Fix "使用 match/if let/expect()/错误传播 ? 替代 unwrap()"
            }

            # ── 6. expect() 无有意义消息 ──
            if ($trimmed -match '\.expect\(""\)' -or $trimmed -match "\.expect\(''\)") {
                Add-Finding -File $relPath -Line $lineNum -Severity "Low" -Category "rust-expect" `
                    -Description "expect() 消息为空 — panic 时无有用信息" `
                    -CWE "CWE-754" -Fix "在 expect() 中添加有意义的错误描述"
            }

            # ── 7. 整数溢出 ──
            if ($trimmed -match '(?<!/)\s*\+\s*=\s*1' -or $trimmed -match '(?<!/)\s*\-\s*=\s*1') {
                # 检查是否在循环中
                $contextStart = [Math]::Max(0, $i - 3)
                $contextEnd = [Math]::Min($lines.Count - 1, $i + 3)
                $isInLoop = $false
                for ($j = $contextStart; $j -le $contextEnd; $j++) {
                    if ($lines[$j] -match '\b(loop|while|for)\b') { $isInLoop = $true; break }
                }
                if ($isInLoop) {
                    Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "rust-overflow" `
                        -Description "循环中的整数运算 — 可能导致整数溢出" `
                        -CWE "CWE-190" -Fix "使用 saturating_add/saturating_sub/wrapping_add 显式处理溢出"
                }
            }

            # ── 8. FFI 边界 ──
            if ($trimmed -match 'extern\s+"C"\s*(fn|block)') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-ffi" `
                    -Description "FFI 外部函数调用 — C ABI 无安全保证" `
                    -CWE "CWE-676" -Fix "为 FFI 函数添加 safe 包装层，验证输入参数合法性"
            }

            # ── 9. maybe_uninit ──
            if ($trimmed -match 'MaybeUninit') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-uninit" `
                    -Description "MaybeUninit 使用 — 未初始化内存可能导致 UB" `
                    -CWE "CWE-457" -Fix "确保所有 MaybeUninit 在读取前被正确初始化"
            }

            # ── 10. 线程间共享可变状态 ──
            if ($trimmed -match '(static\s+mut|Mutex|RwLock|Atomic)' -and $trimmed -match 'static') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "rust-concurrency" `
                    -Description "全局可变状态 — 线程安全需要仔细验证" `
                    -CWE "CWE-362" -Fix "优先使用消息传递；使用静态 Mutex/RwLock 时确保正确锁定"
            }

            # ── 11. std::mem::zeroed() ──
            if ($trimmed -match 'mem::zeroed|std::mem::zeroed|MaybeUninit::zeroed') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-zeroed" `
                    -Description "zeroed() 使用 — 零字节填充对非零类型是 UB" `
                    -CWE "CWE-758" -Fix "优先使用 Default trait 或 safe 构造函数，避免 zeroed()"
            }

            # ── 12. 裸指针算术 ──
            if ($trimmed -match '\.offset\(' -or $trimmed -match '\.add\(' -or $trimmed -match '\.sub\(' -or $trimmed -match '\.wrapping_offset') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-ptr-arithmetic" `
                    -Description "裸指针算术 — 越界访问导致 UB" `
                    -CWE "CWE-823" -Fix "使用 safe 的 slice/iterator API 替代指针算术"
            }

            # ── 13. 不安全 trait 实现 ──
            if ($trimmed -match 'unsafe\s+impl\s+(Send|Sync)' -and $trimmed -notmatch '//\s*safe' -and $trimmed -notmatch '//\s*SAFETY') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-unsafe-trait" `
                    -Description "unsafe impl Send/Sync — 必须确保类型真的是线程安全的" `
                    -CWE "CWE-362" -Fix "添加 SAFETY 注释说明为什么这个 impl 是安全的；考虑使用 #[derive]"
            }

            # ── 14. Pin 错误使用 ──
            if ($trimmed -match 'Pin<&mut' -or $trimmed -match 'Pin::new_unchecked' -or $trimmed -match 'get_unchecked_mut') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "rust-pin" `
                    -Description "Pin 不安全操作 — 错误使用导致自引用类型 UB" `
                    -CWE "CWE-758" -Fix "确保 Pin::new_unchecked 的 Pin 保证不被违反；优先使用 Box::pin"
            }

            # ── 15. 内联汇编 ──
            if ($trimmed -match 'asm!\(' -or $trimmed -match 'core::arch::asm' -or $trimmed -match 'llvm_asm!\(') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Critical" -Category "rust-inline-asm" `
                    -Description "内联汇编 — 完全绕过 Rust 安全保障" `
                    -CWE "CWE-119" -Fix "尽量用 safe 替代；必须使用 asm! 时添加详细安全注释并限制寄存器使用"
            }
        }
    }

    Write-Step "Rust 不安全模式检测完成" "DONE" "Green"
}

# ─── MCP 配置安全审计 ──────────────────────────────────────────────────

function Invoke-MCPAudit {
    param([string]$ProjectPath)

    Write-Banner "MCP 配置安全审计" "Green"

    # 查找各种 MCP 配置文件
    $mcpFiles = @()
    $patterns = @(".mcp.json", "claude_desktop_config.json", "config.toml", "mcp-config.json", ".cursor/mcp.json")

    foreach ($pattern in $patterns) {
        $found = Get-ChildItem -Path $ProjectPath -Recurse -Filter $pattern -ErrorAction SilentlyContinue
        $mcpFiles += $found
    }

    # 全局 MCP 配置
    $globalMCP = @(
        "C:\Users\lbx13\AppData\Roaming\reasonix\config.toml",
        "C:\Users\lbx13\AppData\Roaming\Claude\claude_desktop_config.json",
        "C:\Users\lbx13\.trae-cn\config.json"
    )

    foreach ($path in $globalMCP) {
        if (Test-Path $path) {
            $mcpFiles += Get-Item $path
        }
    }

    if (-not $mcpFiles) {
        Write-Step "未找到 MCP 配置文件" "SKIP" "DarkYellow"
        return
    }

    Write-Step "发现 $($mcpFiles.Count) 个 MCP 配置文件" "RUN" "Yellow"

    foreach ($file in $mcpFiles) {
        $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $content) { continue }
        $relPath = $file.FullName

        # ── 1. 检查 MCP server 指向本地可执行文件 ──
        if ($content -match '"command"\s*:\s*"([^"]+)"') {
            $cmds = [regex]::Matches($content, '"command"\s*:\s*"([^"]+)"')
            foreach ($cmd in $cmds) {
                $cmdPath = $cmd.Groups[1].Value
                if ($cmdPath -match '\.(exe|bat|cmd|ps1|sh)$') {
                    if (-not (Test-Path $cmdPath)) {
                        Add-Finding -File $relPath -Line 0 -Severity "High" -Category "mcp-missing-binary" `
                            -Description "MCP server 配置指向不存在的可执行文件: $cmdPath" `
                            -CWE "CWE-1104" -Fix "安装缺失的 MCP server 或移除配置项"
                    }
                }
            }
        }

        # ── 2. 检查 MCP server 是否使用绝对路径 ──
        if ($content -match '"command"\s*:\s*"(\.\.|\./|[a-zA-Z]:\\)') {
            # 相对路径是 OK 的
        } elseif ($content -match '"command"\s*:\s*"([a-zA-Z]:\\[^"]+)"') {
            Add-Finding -File $relPath -Line 0 -Severity "Low" -Category "mcp-absolute-path" `
                -Description "MCP server 使用绝对路径 — 迁移后需要更新" `
                -CWE "CWE-706" -Fix "考虑使用相对路径或环境变量"
        }

        # ── 3. 检查 MCP server args 中是否有可疑参数 ──
        if ($content -match '"args"\s*:\s*\[([^\]]*)\]') {
            $argsBlock = $Matches[1]
            if ($argsBlock -match '--allow-all' -or $argsBlock -match '--dangerous' -or $argsBlock -match '--no-sandbox' -or $argsBlock -match '--insecure') {
                Add-Finding -File $relPath -Line 0 -Severity "Critical" -Category "mcp-dangerous-args" `
                    -Description "MCP server 使用了危险参数: $($Matches[0])" `
                    -CWE "CWE-284" -Fix "移除危险参数，使用最小权限原则"
            }
        }

        # ── 4. 检查 MCP 工具是否有越权风险 ──
        if ($content -match '"tools"\s*:\s*\{') {
            # 检查是否有文件系统级别的工具
            if ($content -match '"read_file"|"write_file"|"delete_file"|"execute"|"exec"|"shell"|"command"') {
                Add-Finding -File $relPath -Line 0 -Severity "High" -Category "mcp-privilege-escalation" `
                    -Description "MCP server 提供文件系统/命令执行工具 — 权限越界风险" `
                    -CWE "CWE-269" -Fix "限制工具在白名单目录内操作，添加路径验证"
            }
        }

        # ── 5. 检查 MCP server 的环境变量 ──
        if ($content -match '"env"\s*:\s*\{([^}]+)\}') {
            $envBlock = $Matches[1]
            if ($envBlock -match '(?i)(password|secret|token|key|credential|api_key|apikey|auth)') {
                Add-Finding -File $relPath -Line 0 -Severity "Critical" -Category "mcp-secret-in-config" `
                    -Description "MCP 配置中包含敏感凭据 — 配置文件可能被泄露" `
                    -CWE "CWE-798" -Fix "使用环境变量引用或密钥管理服务，不要硬编码"
            }
        }

        # ── 6. MCP 协议版本降级检查 ──
        if ($content -match '"protocolVersion"\s*:\s*"(\d+)"') {
            $version = $Matches[1]
            if ([int]$version -lt 2024) {
                Add-Finding -File $relPath -Line 0 -Severity "Medium" -Category "mcp-protocol-downgrade" `
                    -Description "MCP 协议版本较低 (v$version) — 可能使用已知有漏洞的旧协议" `
                    -CWE "CWE-1104" -Fix "升级 MCP 协议到最新版本"
            }
        }

        # ── 7. MCP 配置投毒风险 ──
        $fileInfo = Get-Item $file.FullName
        $directory = $fileInfo.Directory
        # 检查配置文件是否可被其他用户写入
        try {
            $acl = Get-Acl $file.FullName -ErrorAction SilentlyContinue
            foreach ($access in $acl.Access) {
                if ($access.FileSystemRights -match 'Write|Modify|FullControl' -and $access.IdentityReference -ne "$env:USERNAME") {
                    Add-Finding -File $relPath -Line 0 -Severity "Medium" -Category "mcp-config-tamper" `
                        -Description "MCP 配置文件可被非当前用户写入 — 配置投毒风险" `
                        -CWE "CWE-732" -Fix "限制配置文件权限，仅允许当前用户写入"
                }
            }
        } catch { }

        # ── 8. MCP 传输安全 ──
        if ($content -match '"transport"\s*:\s*"http"' -or $content -match '"url"\s*:\s*"http://[^"]+"') {
            Add-Finding -File $relPath -Line 0 -Severity "High" -Category "mcp-transport-security" `
                -Description "MCP server 使用未加密的 HTTP 传输 — 中间人攻击风险" `
                -CWE "CWE-319" -Fix "使用 HTTPS/WSS 加密传输，或至少在同一台机器上使用 stdio"
        }

        # ── 9. MCP 工具名劫持风险 ──
        if ($content -match '"name"\s*:\s*"(read|write|delete|exec|run|shell|system|command|admin|root|sudo)"') {
            Add-Finding -File $relPath -Line 0 -Severity "Medium" -Category "mcp-tool-hijack" `
                -Description "MCP 工具名使用常见系统命令名 — 工具名劫持风险" `
                -CWE "CWE-285" -Fix "使用更具体的工具命名，避免与系统命令重名"
        }

        # ── 10. MCP 路径遍历 ──
        if ($content -match '"args"\s*:\s*\[[^\]]*\]' -and $content -match '"command"\s*:\s*"[^"]*"') {
            # 检查 args 中是否有路径参数
            if ($content -match '"args"\s*:\s*\[[^\]]*\.\.\.|\.\.\\|\.\.\/[^\]]*\]') {
                Add-Finding -File $relPath -Line 0 -Severity "High" -Category "mcp-pathtraversal" `
                    -Description "MCP 工具参数中包含路径遍历模式 — 可能被用于越权访问" `
                    -CWE "CWE-22" -Fix "对工具参数做路径规范化检查，禁止 .. 序列"
            }
        }
    }

    Write-Step "MCP 配置审计完成" "DONE" "Green"
}

# ─── C/C++ 安全检测（v2.0 新增）────────────────────────────────────────

function Invoke-CppSecurityScan {
    param([string]$ProjectPath)

    Write-Banner "C/C++ 安全检测" "Green"

    $cppFiles = Get-ChildItem -Path $ProjectPath -Recurse -Include "*.c","*.cpp","*.cxx","*.cc","*.h","*.hpp","*.hxx" -ErrorAction SilentlyContinue
    if (-not $cppFiles) {
        Write-Step "未找到 C/C++ 文件" "SKIP" "DarkYellow"
        return
    }

    # 过滤排除目录
    $cppFiles = $cppFiles | Where-Object { -not (Test-Excluded $_.FullName) }

    Write-Step "扫描 $($cppFiles.Count) 个 C/C++ 文件" "RUN" "Yellow"

    foreach ($file in $cppFiles) {
        $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $content) { continue }
        $lines = $content -split "`n"
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart('\')

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            $lineNum = $i + 1
            $trimmed = $line.Trim()

            # ── 1. gets() 缓冲区溢出 ──
            if ($trimmed -match '\bgets\s*\(') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Critical" -Category "cpp-buffer-overflow" `
                    -Description "gets() 使用 — 无条件缓冲区溢出，C11 已移除" `
                    -CWE "CWE-120" -Fix "替换为 fgets() 并指定缓冲区大小"
            }

            # ── 2. printf 格式化字符串 ──
            if ($trimmed -match 'printf\s*\(\s*[^"]' -and $trimmed -notmatch 'printf\s*\(\s*"') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "cpp-format-string" `
                    -Description "printf 直接使用变量作为格式字符串 — 格式化字符串漏洞" `
                    -CWE "CWE-134" -Fix '使用 printf("%s", var) 替代 printf(var)'
            }

            # ── 3. strcpy/strcat 无边界检查 ──
            if ($trimmed -match '\b(strcpy|strcat|sprintf|vsprintf)\s*\(') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "cpp-bounds" `
                    -Description "不安全的字符串拷贝 — 缓冲区溢出风险" `
                    -CWE "CWE-120" -Fix "替换为 strncpy/strncat/snprintf 并指定最大长度"
            }

            # ── 4. 数组访问无边界检查 ──
            if ($trimmed -match '\[.*\]\s*=\s*[^;]+' -and $trimmed -notmatch 'for|while|if|sizeof|std::') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "cpp-bounds" `
                    -Description "数组直接赋值 — 可能越界访问" `
                    -CWE "CWE-119" -Fix "使用 std::array/vector 或添加边界检查"
            }

            # ── 5. malloc/calloc 后无 NULL 检查 ──
            if ($trimmed -match '\b(malloc|calloc|realloc)\s*\(' -and $lines[$i+1] -and $lines[$i+1] -notmatch '!= NULL|== NULL|if\s*\(') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "cpp-null-deref" `
                    -Description "malloc/calloc 后无 NULL 检查 — 内存分配失败时解引用崩溃" `
                    -CWE "CWE-476" -Fix "检查 malloc/calloc 返回值是否为 NULL"
            }

            # ── 6. 整数溢出 ──
            if ($trimmed -match '\b(atoi|atol|atoll)\s*\(' -and $trimmed -notmatch 'if|while|check') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "cpp-overflow" `
                    -Description "atoi/atol — 输入超出 int 范围时行为未定义" `
                    -CWE "CWE-190" -Fix "替换为 strtol/strtoll 并检查 errno 和范围"
            }

            # ── 7. 内存释放后使用 ──
            if ($trimmed -match '\bfree\s*\(' -and $i + 2 -lt $lines.Count) {
                for ($j = 1; $j -le 5; $j++) {
                    if ($i + $j -lt $lines.Count -and $lines[$i + $j] -match $trimmed -replace 'free\(.*\)', '') {
                        Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "cpp-uaf" `
                            -Description "free() 后可能继续使用指针 — Use-After-Free" `
                            -CWE "CWE-416" -Fix "free() 后立即将指针置为 NULL"
                        break
                    }
                }
            }

            # ── 8. 竞争条件 ──
            if ($trimmed -match '\b(access|creat|mktemp|tmpnam|tempnam)\s*\(') {
                Add-Finding -File $relPath -Line $lineNum -Severity "High" -Category "cpp-race" `
                    -Description "TOCTOU 竞争条件函数 — 检查和操作之间条件可能变化" `
                    -CWE "CWE-367" -Fix "使用 O_CREAT|O_EXCL 或 mkstemp() 替代"
            }

            # ── 9. setjmp/longjmp ──
            if ($trimmed -match '\b(setjmp|longjmp)\s*\(') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "cpp-control-flow" `
                    -Description "setjmp/longjmp — 非局部跳转导致资源泄漏和栈破坏" `
                    -CWE "CWE-480" -Fix "使用异常处理(try/catch)或状态机替代"
            }

            # ── 10. 不安全 C 标准库函数 ──
            if ($trimmed -match '\b(strlen|strcmp|strstr|memcpy|memmove|bzero|bcopy)\s*\(' -and $trimmed -notmatch 'n\s*\(|_s\s*\(') {
                Add-Finding -File $relPath -Line $lineNum -Severity "Medium" -Category "cpp-unsafe-lib" `
                    -Description "使用无边界检查的 C 标准库函数 — 建议使用 _s 安全版本" `
                    -CWE "CWE-676" -Fix "使用 strnlen/strncmp/strnstr/memcpy_s 等安全版本"
            }
        }
    }

    Write-Step "C/C++ 安全检测完成" "DONE" "Green"
}

# ─── 配置安全审计（v2.0 新增）──────────────────────────────────────────

function Invoke-ConfigSecurityAudit {
    param([string]$ProjectPath)

    Write-Banner "配置安全审计" "Green"

    $configFiles = @()
    $configPatterns = @("*.env", "*.env.*", "docker-compose*.yml", "docker-compose*.yaml", "Dockerfile*",
                        ".gitignore", ".dockerignore", "*.ini", "*.cfg", "*.conf",
                        "*.toml", "*.yaml", "*.yml", "*.json", "*.xml")

    foreach ($pattern in $configPatterns) {
        $found = Get-ChildItem -Path $ProjectPath -Recurse -Filter $pattern -ErrorAction SilentlyContinue |
            Where-Object { -not (Test-Excluded $_.FullName) }
        $configFiles += $found
    }

    if (-not $configFiles) {
        Write-Step "未找到配置文件" "SKIP" "DarkYellow"
        return
    }

    Write-Step "扫描 $($configFiles.Count) 个配置文件" "RUN" "Yellow"

    foreach ($file in $configFiles) {
        $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $content) { continue }
        $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart('\')
        $ext = [System.IO.Path]::GetExtension($file.FullName).ToLower()
        $name = [System.IO.Path]::GetFileName($file.FullName).ToLower()

        # ── Dockerfile 安全 ──
        if ($name -eq 'dockerfile' -or $name -like 'dockerfile.*') {
            if ($content -match 'FROM\s+.*:latest') {
                Add-Finding -File $relPath -Line 0 -Severity "Medium" -Category "config-docker" `
                    -Description "Dockerfile 使用 :latest 标签 — 构建不可复现" `
                    -CWE "CWE-1104" -Fix "使用明确版本标签替代 :latest"
            }
            if ($content -match 'USER root' -or ($content -notmatch 'USER' -and $content -match 'FROM')) {
                Add-Finding -File $relPath -Line 0 -Severity "High" -Category "config-docker" `
                    -Description "Docker 容器以 root 运行 — 容器逃逸风险" `
                    -CWE "CWE-250" -Fix "使用 USER 指令切换到非 root 用户"
            }
            if ($content -match 'EXPOSE\s+22\b|EXPOSE\s+3389\b') {
                Add-Finding -File $relPath -Line 0 -Severity "High" -Category "config-docker" `
                    -Description "Docker 暴露 SSH/RDP 端口 — 攻击面过大" `
                    -CWE "CWE-284" -Fix "移除不必要的端口暴露，使用 SSH 跳板机"
            }
        }

        # ── docker-compose 安全 ──
        if ($name -like 'docker-compose*') {
            if ($content -notmatch 'restart:\s*unless-stopped' -and $content -notmatch 'restart:\s*always') {
                Add-Finding -File $relPath -Line 0 -Severity "Low" -Category "config-compose" `
                    -Description "docker-compose 服务未设置 restart 策略 — 崩溃后不会自动恢复" `
                    -CWE "CWE-770" -Fix "添加 restart: unless-stopped 策略"
            }
            if ($content -match 'ports:\s*[\s\S]*?:\s*"\d+:\d+"' -and $content -match '0\.0\.0\.0:\d+:\d+') {
                Add-Finding -File $relPath -Line 0 -Severity "Medium" -Category "config-compose" `
                    -Description "docker-compose 端口绑定到 0.0.0.0 — 外部可访问" `
                    -CWE "CWE-200" -Fix "绑定到 127.0.0.1 或使用内部网络"
            }
        }

        # ── .env 文件检查 ──
        if ($name -eq '.env' -or $name -like '.env.*') {
            Add-Finding -File $relPath -Line 0 -Severity "Medium" -Category "config-env" `
                -Description ".env 文件存在于项目中 — 可能包含敏感信息" `
                -CWE "CWE-200" -Fix "确保 .env 在 .gitignore 中，仅存储 .env.example"
        }

        # ── CI/CD 配置文件安全 ──
        if ($name -match '^(\.github|\.gitlab|\.circleci|Jenkinsfile|azure-pipelines)') {
            if ($content -match '(?i)(password|secret|token|key|credential|apikey)\s*[:=]\s*["\x27]?[^"\x27\n]{4,}["\x27]?') {
                Add-Finding -File $relPath -Line 0 -Severity "Critical" -Category "config-ci-cd" `
                    -Description "CI/CD 配置中硬编码凭据 — 流水线日志可能泄露" `
                    -CWE "CWE-798" -Fix "使用 CI/CD 平台的 Secrets 管理功能，在运行时注入环境变量"
            }
        }

        # ── JSON/XML 敏感信息 ──
        if ($ext -in '.json', '.xml') {
            if ($content -match '(?i)"password"\s*:\s*"[^"]{1,}"' -or $content -match '(?i)"secret"\s*:\s*"[^"]{1,}"') {
                Add-Finding -File $relPath -Line 0 -Severity "Critical" -Category "config-json-secret" `
                    -Description "JSON/XML 配置文件包含明文密码/密钥" `
                    -CWE "CWE-798" -Fix "移除硬编码凭据，使用环境变量或密钥管理服务"
            }
        }
    }

    Write-Step "配置安全审计完成" "DONE" "Green"
}

# ─── 密钥泄露检测 ──────────────────────────────────────────────────────

function Invoke-SecretScan {
    param([string]$ProjectPath)

    Write-Banner "密钥泄露检测（本地正则匹配）" "Green"

    # 高熵模式（密钥/令牌格式）
    $secretPatterns = @(
        @{ Pattern = '(?i)(?:api[_-]?key|apikey)\s*[:=]\s*["'']?[A-Za-z0-9_\-]{16,}["'']?'; Severity = "Critical"; Desc = "API Key 泄露" },
        @{ Pattern = '(?i)(?:secret|token|password|passwd|pwd)\s*[:=]\s*["'']?[A-Za-z0-9_\-!@#$%^&*]{8,}["'']?'; Severity = "Critical"; Desc = "密钥/令牌/密码泄露" },
        @{ Pattern = '(?i)sk-[A-Za-z0-9]{32,}'; Severity = "Critical"; Desc = "OpenAI/Anthropic API Key 格式" },
        @{ Pattern = '(?i)ghp_[A-Za-z0-9]{36}'; Severity = "Critical"; Desc = "GitHub Personal Access Token" },
        @{ Pattern = '(?i)gho_[A-Za-z0-9]{36}'; Severity = "Critical"; Desc = "GitHub OAuth Access Token" },
        @{ Pattern = '(?i)ghu_[A-Za-z0-9]{36}'; Severity = "Critical"; Desc = "GitHub User-to-Server Token" },
        @{ Pattern = '(?i)ghs_[A-Za-z0-9]{36}'; Severity = "Critical"; Desc = "GitHub Server-to-Server Token" },
        @{ Pattern = '(?i)AKIA[0-9A-Z]{16}'; Severity = "Critical"; Desc = "AWS Access Key ID" },
        @{ Pattern = '(?i)-----BEGIN\s+(RSA|DSA|EC|PGP|OPENSSH)\s+PRIVATE\s+KEY-----'; Severity = "Critical"; Desc = "私钥泄露" },
        @{ Pattern = '(?i)SG\.[A-Za-z0-9_\-\.]{22,}\.[A-Za-z0-9_\-\.]{43,}'; Severity = "Critical"; Desc = "SendGrid API Key" },
        @{ Pattern = '(?i)pk_live_[A-Za-z0-9]{24,}'; Severity = "Critical"; Desc = "Stripe Live Secret Key" },
        @{ Pattern = '(?i)sk_live_[A-Za-z0-9]{24,}'; Severity = "Critical"; Desc = "Stripe Live Secret Key" },
        @{ Pattern = '(?i)AIza[0-9A-Za-z_\-]{35}'; Severity = "High"; Desc = "Google API Key" },
        @{ Pattern = '(?i)https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/'; Severity = "High"; Desc = "Slack Webhook URL" },
        @{ Pattern = '(?i)(?:mysql|postgres|mongodb|redis|amqp|sqs)://[^:]+:[^@]+@'; Severity = "Critical"; Desc = "数据库连接字符串含密码" },
        @{ Pattern = '(?i)eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}'; Severity = "High"; Desc = "JWT Token 泄露" },
        @{ Pattern = '(?i)(?:azure|AZURE)_(?:client|secret|key|token|connection)[^A-Za-z0-9][A-Za-z0-9_\-]{8,}'; Severity = "Critical"; Desc = "Azure 密钥/连接字符串泄露" },
        @{ Pattern = '(?i)(?:bot|BOT)_?token[^A-Za-z0-9][A-Za-z0-9:]{30,}'; Severity = "High"; Desc = "Telegram Bot Token 泄露" },
        @{ Pattern = '(?i)(?:auth|AUTH|authorization)[^A-Za-z0-9][A-Za-z0-9_\-]{20,}'; Severity = "High"; Desc = "通用认证令牌泄露" },
        @{ Pattern = '(?i)"docker"?\s*:\s*\{[^}]*"auths"\s*:\s*\{[^}]*"auth"\s*:"[A-Za-z0-9+/=]{20,}"'; Severity = "Critical"; Desc = "Docker config.json 认证泄露" }
    )

    # 排除文件
    $excludePatterns = @(
        '\.git\\', 'node_modules\\', 'target\\', '.vscode\\', '.idea\\',
        'vuln-reports\\', 'wf-reports\\', 'bin\\', '\.git\b',
        '\.env.example', '\.env\.sample', 'README\.md', 'LICENSE', '\.svg$'
    )

    $sourceFiles = Get-ChildItem -Path $ProjectPath -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $path = $_.FullName
            $exclude = $false
            foreach ($ex in $excludePatterns) {
                if ($path -match $ex) { $exclude = $true; break }
            }
            -not $exclude -and $_.Length -lt 1MB  # 跳过大于 1MB 的文件
        }

    Write-Step "扫描 $($sourceFiles.Count) 个文件" "RUN" "Yellow"

    foreach ($file in $sourceFiles) {
        try {
            $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart('\')

            # 跳过 .git 目录
            if ($relPath -match '\.git\\') { continue }

            foreach ($sp in $secretPatterns) {
                $matches = [regex]::Matches($content, $sp.Pattern)
                if ($matches.Count -gt 0) {
                    # 找到第一个匹配所在行
                    $lines = $content -split "`n"
                    for ($i = 0; $i -lt [Math]::Min($lines.Count, 10); $i++) {
                        if ($lines[$i] -match $sp.Pattern) {
                            Add-Finding -File $relPath -Line ($i+1) -Severity $sp.Severity -Category "secret-leak" `
                                -Description "$($sp.Desc) — 敏感信息硬编码在源码中" `
                                -CWE "CWE-798" -Fix "移除硬编码密钥，使用环境变量或密钥管理服务"
                            break
                        }
                    }
                }
            }
        } catch { }
    }

    Write-Step "密钥泄露检测完成" "DONE" "Green"
}

# ─── 依赖安全审计（本地） ──────────────────────────────────────────────

function Invoke-DepAudit {
    param([string]$ProjectPath)

    Write-Banner "依赖安全审计（本地）" "Green"

    $hasDep = $false

    # ── Rust Cargo 依赖 ──
    $cargoFile = Join-Path $ProjectPath "Cargo.toml"
    if (Test-Path $cargoFile) {
        $hasDep = $true
        Write-Step "检查 Rust 依赖" "RUN" "Yellow"

        # 1. 检查 Cargo.lock 是否存在
        $cargoLock = Join-Path $ProjectPath "Cargo.lock"
        if (-not (Test-Path $cargoLock)) {
            Add-Finding -File "Cargo.toml" -Line 0 -Severity "Medium" -Category "dep-lockfile" `
                -Description "缺少 Cargo.lock — 依赖版本不锁定，构建不可复现" `
                -CWE "CWE-1104" -Fix "提交 Cargo.lock 到版本控制"
        }

        # 2. 检查 Cargo.toml 中依赖版本是否固定
        $cargoContent = Get-Content $cargoFile -Raw -ErrorAction SilentlyContinue
        if ($cargoContent) {
            # 检查是否有通配符依赖
            if ($cargoContent -match '"[*]"') {
                Add-Finding -File "Cargo.toml" -Line 0 -Severity "High" -Category "dep-wildcard" `
                    -Description "依赖使用通配符版本 '*' — 可能导致意外升级" `
                    -CWE "CWE-1104" -Fix "指定确切的版本号或范围"
            }
            # 检查是否有 git 依赖（非官方源）
            if ($cargoContent -match 'git\s*=\s*"[^"]+"' -and $cargoContent -notmatch 'crates\.io') {
                Add-Finding -File "Cargo.toml" -Line 0 -Severity "Medium" -Category "dep-git-source" `
                    -Description "依赖来自 Git 仓库 — 供应链风险" `
                    -CWE "CWE-1357" -Fix "优先使用 crates.io 官方源，git 依赖需指定 commit hash"
            }
        }

        # 3. 尝试 cargo audit（如果安装）
        $cargoAudit = Get-Command "cargo-audit" -ErrorAction SilentlyContinue -or (Get-Command "cargo" -ErrorAction SilentlyContinue)
        if (Get-Command "cargo" -ErrorAction SilentlyContinue) {
            try {
                $auditResult = & cargo audit --manifest-path $cargoFile 2>&1 | Out-String
                if ($auditResult -match 'RUSTSEC|CVE|Vulnerability') {
                    $vulns = [regex]::Matches($auditResult, 'RUSTSEC-\d{4}-\d{4}')
                    foreach ($v in $vulns) {
                        Add-Finding -File "Cargo.toml" -Line 0 -Severity "Critical" -Category "dep-cve" `
                            -Description "Cargo 依赖存在已知 CVE: $($v.Value)" `
                            -CWE "CWE-1104" -Fix "更新依赖版本到修复漏洞的版本"
                    }
                }
            } catch { }
        }
    }

    # ── npm 依赖 ──
    $packageFile = Join-Path $ProjectPath "package.json"
    if (Test-Path $packageFile) {
        $hasDep = $true
        Write-Step "检查 npm 依赖" "RUN" "Yellow"

        $packageContent = Get-Content $packageFile -Raw -ErrorAction SilentlyContinue
        if ($packageContent) {
            # 检查是否有通配符依赖
            if ($packageContent -match '"[*]"') {
                Add-Finding -File "package.json" -Line 0 -Severity "High" -Category "dep-wildcard" `
                    -Description "npm 依赖使用通配符版本 '*' — 可能导致意外升级" `
                    -CWE "CWE-1104" -Fix "指定确切的版本号"
            }
            # 检查是否有 package-lock.json
            $pkgLock = Join-Path $ProjectPath "package-lock.json"
            if (-not (Test-Path $pkgLock)) {
                Add-Finding -File "package.json" -Line 0 -Severity "Medium" -Category "dep-lockfile" `
                    -Description "缺少 package-lock.json — 依赖版本不锁定" `
                    -CWE "CWE-1104" -Fix "提交 package-lock.json 到版本控制"
            }
        }
    }

    # ── Godot 插件依赖 ──
    $godotPluginFile = Join-Path $ProjectPath "project.godot"
    if (Test-Path $godotPluginFile) {
        $hasDep = $true
        Write-Step "检查 Godot 插件依赖" "RUN" "Yellow"

        $godotContent = Get-Content $godotPluginFile -Raw -ErrorAction SilentlyContinue
        if ($godotContent) {
            # 检查插件配置
            $addonsDir = Join-Path $ProjectPath "addons"
            if (Test-Path $addonsDir) {
                $plugins = Get-ChildItem -Path $addonsDir -Directory -ErrorAction SilentlyContinue
                foreach ($plugin in $plugins) {
                    $pluginConfig = Join-Path $plugin.FullName "plugin.cfg"
                    if (Test-Path $pluginConfig) {
                        $pluginContent = Get-Content $pluginConfig -Raw -ErrorAction SilentlyContinue
                        if ($pluginContent -match 'version\s*=\s*"([^"]+)"') {
                            $version = $Matches[1]
                            if ($version -eq "0.0.0" -or $version -eq "1.0" -or $version -eq "0.1") {
                                Add-Finding -File "addons/$($plugin.Name)/plugin.cfg" -Line 0 -Severity "Low" -Category "dep-plugin-version" `
                                    -Description "Godot 插件 $($plugin.Name) 版本号可能未正确设置: $version" `
                                    -CWE "CWE-1104" -Fix "更新插件版本号"
                            }
                        }
                    }
                }
            }
        }
    }

    if (-not $hasDep) {
        Write-Step "未找到依赖配置文件" "SKIP" "DarkYellow"
    }

    Write-Step "依赖审计完成" "DONE" "Green"
}

# ─── 主入口 ────────────────────────────────────────────────────────────

function Main {
    param([string]$ProjectPath, [string]$Category)

    $script:Findings = @()

    Write-Banner "本地漏洞挖掘 v2.0: $ProjectPath" "Magenta"
    Write-Step "类别: $Category" "INFO" "Cyan"
    Write-Step "报告: $REPORT_DIR" "INFO" "Cyan"
    Write-Step "并行度: $Parallelism | JSON: $Json | 排除: $($EXCLUDE_PATTERNS -join ', ')" "INFO" "Cyan"

    $elapsed = [System.Diagnostics.Stopwatch]::StartNew()

    switch ($Category) {
        "all" {
            Invoke-GDScriptScan -ProjectPath $ProjectPath
            Invoke-RustUnsafeScan -ProjectPath $ProjectPath
            Invoke-CppSecurityScan -ProjectPath $ProjectPath
            Invoke-MCPAudit -ProjectPath $ProjectPath
            Invoke-ConfigSecurityAudit -ProjectPath $ProjectPath
            Invoke-SecretScan -ProjectPath $ProjectPath
            Invoke-DepAudit -ProjectPath $ProjectPath
        }
        "gdscript" { Invoke-GDScriptScan -ProjectPath $ProjectPath }
        "rust"     { Invoke-RustUnsafeScan -ProjectPath $ProjectPath }
        "cpp"      { Invoke-CppSecurityScan -ProjectPath $ProjectPath }
        "mcp"      { Invoke-MCPAudit -ProjectPath $ProjectPath }
        "config"   { Invoke-ConfigSecurityAudit -ProjectPath $ProjectPath }
        "secret"   { Invoke-SecretScan -ProjectPath $ProjectPath }
        "dep"      { Invoke-DepAudit -ProjectPath $ProjectPath }
    }

    $elapsed.Stop()

    # ── 汇总报告 ──
    $criticalCount = ($Findings | Where-Object { $_.Severity -eq "Critical" }).Count
    $highCount     = ($Findings | Where-Object { $_.Severity -eq "High" }).Count
    $mediumCount   = ($Findings | Where-Object { $_.Severity -eq "Medium" }).Count
    $lowCount      = ($Findings | Where-Object { $_.Severity -eq "Low" }).Count

    Write-Banner "漏洞挖掘汇总" "Yellow"
    Write-Step "耗时: $($elapsed.Elapsed.TotalSeconds.ToString('F1'))s" "INFO" "Cyan"
    Write-Step "Critical: $criticalCount | High: $highCount | Medium: $mediumCount | Low: $lowCount" "STATS" "White"

    # 生成 Markdown 报告
    $report = @"
# 本地漏洞挖掘报告

项目: $ProjectPath
时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
耗时: $($elapsed.Elapsed.TotalSeconds.ToString('F1'))s
类别: $Category

## 统计

| 严重性 | 数量 | 操作 |
|--------|------|------|
| Critical | $criticalCount | 必须修复 |
| High | $highCount | 强烈建议修复 |
| Medium | $mediumCount | 建议修复 |
| Low | $lowCount | 可选 |

## 发现详情

"@

    if ($Findings.Count -eq 0) {
        $report += "**无发现，本次扫描未检测到任何漏洞。**`n"
    } else {
        # 按严重性分组
        $groups = $Findings | Group-Object -Property Severity
        foreach ($group in $groups) {
            $report += "### $($group.Name) ($($group.Count) 项)`n`n"
            $report += "| 文件 | 行 | 类别 | 描述 | CWE | 修复建议 |`n"
            $report += "|------|----|------|------|-----|---------|`n"
            foreach ($f in $group.Group) {
                $fileEscaped = $f.File -replace '\|', '\|'
                $descEscaped = $f.Description -replace '\|', '\|'
                $fixEscaped  = $f.Fix -replace '\|', '\|'
                $report += "| $fileEscaped | $($f.Line) | $($f.Category) | $descEscaped | $($f.CWE) | $fixEscaped |`n"
            }
            $report += "`n"
        }
    }

    $report += @"

## 分类统计

| 类别 | 数量 |
|------|------|
"@

    $catGroups = $Findings | Group-Object -Property Category
    foreach ($cg in $catGroups) {
        $report += "| $($cg.Name) | $($cg.Count) |`n"
    }

    $report += @"

## 建议

"@

    if ($criticalCount -gt 0) {
        $report += "- **Critical 漏洞必须立即修复**，否则存在严重安全风险`n"
    }
    if ($highCount -gt 0) {
        $report += "- **High 漏洞强烈建议修复**，建议在下一个迭代中处理`n"
    }
    if ($mediumCount -gt 0) {
        $report += "- **Medium 漏洞建议修复**，可在常规维护中处理`n"
    }
    $report += "- 本次扫描**全部本地执行**，不依赖任何外部 API 或云服务`n"

    # 保存报告
    $reportPath = New-Report -Name "vuln-scan" -Content $report

    # JSON 输出（如果指定）
    if ($Json) {
        $jsonOutput = @{
            scan_version = "2.0"
            project      = $ProjectPath
            timestamp    = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
            elapsed_ms   = [int]($elapsed.Elapsed.TotalMilliseconds)
            category     = $Category
            summary = @{
                critical = $criticalCount
                high     = $highCount
                medium   = $mediumCount
                low      = $lowCount
                total    = $Findings.Count
            }
            findings = $Findings | ForEach-Object {
                @{
                    file        = $_.File
                    line        = $_.Line
                    severity    = $_.Severity
                    category    = $_.Category
                    description = $_.Description
                    cwe         = $_.CWE
                    fix         = $_.Fix
                }
            }
        } | ConvertTo-Json -Depth 10

        $jsonPath = $reportPath -replace '\.md$', '.json'
        $jsonOutput | Out-File -FilePath $jsonPath -Encoding utf8
        Write-Step "JSON 输出已保存: $jsonPath" "OK" "Green"
        Write-Host "`n$jsonOutput" -ForegroundColor Cyan
    }

    # 返回结构化结果
    return @{
        Findings  = $Findings
        Critical  = $criticalCount
        High      = $highCount
        Medium    = $mediumCount
        Low       = $lowCount
        Total     = $Findings.Count
        Report    = $reportPath
        Elapsed   = $elapsed.Elapsed.TotalSeconds
    }
}

# ─── 执行入口 ──────────────────────────────────────────────────────────

$result = Main -ProjectPath $ProjectPath -Category $Category
$result