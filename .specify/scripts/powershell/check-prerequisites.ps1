# check-prerequisites.ps1
# SpecKit 必要條件檢查腳本

param(
    [switch]$Json,
    [switch]$RequireTasks,
    [switch]$IncludeTasks,
    [string]$FeatureName
)

$ErrorActionPreference = "Stop"

# 尋找 Git 儲存庫根目錄
function Find-GitRoot {
    $currentDir = Get-Location
    while ($currentDir) {
        if (Test-Path (Join-Path $currentDir ".git")) {
            return $currentDir
        }
        $parent = Split-Path $currentDir -Parent
        if ($parent -eq $currentDir) { break }
        $currentDir = $parent
    }
    return $null
}

# 主要檢查邏輯
try {
    # 尋找儲存庫根目錄
    $repoRoot = Find-GitRoot
    if (-not $repoRoot) {
        $repoRoot = Get-Location
    }

    # 設定路徑
    $specifyDir = Join-Path $repoRoot ".specify"
    $memoryDir = Join-Path $specifyDir "memory"
    $featuresDir = Join-Path $specifyDir "features"
    $templatesDir = Join-Path $specifyDir "templates"
    $constitutionPath = Join-Path $memoryDir "constitution.md"

    # 檢查 .specify 目錄
    if (-not (Test-Path $specifyDir)) {
        throw ".specify 目錄不存在。請先執行 SpecKit 初始化。"
    }

    # 檢查憲章檔案
    $hasConstitution = Test-Path $constitutionPath

    # 決定功能目錄
    $featureDir = $null
    $availableDocs = @{
        spec = $false
        plan = $false
        tasks = $false
    }

    if ($FeatureName) {
        $featureDir = Join-Path $featuresDir $FeatureName
    } else {
        # 尋找最近修改的功能目錄
        if (Test-Path $featuresDir) {
            $features = Get-ChildItem -Path $featuresDir -Directory |
                        Sort-Object LastWriteTime -Descending
            if ($features.Count -gt 0) {
                $featureDir = $features[0].FullName
            }
        }
    }

    # 檢查功能文件
    if ($featureDir -and (Test-Path $featureDir)) {
        $specPath = Join-Path $featureDir "spec.md"
        $planPath = Join-Path $featureDir "plan.md"
        $tasksPath = Join-Path $featureDir "tasks.md"

        $availableDocs.spec = Test-Path $specPath
        $availableDocs.plan = Test-Path $planPath
        $availableDocs.tasks = Test-Path $tasksPath

        # 如果要求必須有 tasks.md
        if ($RequireTasks -and -not $availableDocs.tasks) {
            throw "tasks.md 不存在於 $featureDir。請先執行 /speckit.tasks。"
        }
    } elseif ($RequireTasks) {
        throw "找不到功能目錄。請先執行 /speckit.specify 建立規格。"
    }

    # 準備輸出
    $result = @{
        REPO_ROOT = $repoRoot.Path
        SPECIFY_DIR = $specifyDir
        MEMORY_DIR = $memoryDir
        FEATURES_DIR = $featuresDir
        TEMPLATES_DIR = $templatesDir
        CONSTITUTION_PATH = $constitutionPath
        HAS_CONSTITUTION = $hasConstitution
        FEATURE_DIR = if ($featureDir) { $featureDir } else { "" }
        AVAILABLE_DOCS = $availableDocs
    }

    # 如果要求載入 tasks
    if ($IncludeTasks -and $featureDir -and $availableDocs.tasks) {
        $tasksContent = Get-Content (Join-Path $featureDir "tasks.md") -Raw
        $result.TASKS_CONTENT = $tasksContent
    }

    # 輸出格式
    if ($Json) {
        $result | ConvertTo-Json -Depth 5
    } else {
        Write-Host "=== SpecKit 環境檢查 ===" -ForegroundColor Cyan
        Write-Host "儲存庫根目錄: $($result.REPO_ROOT)" -ForegroundColor Green
        Write-Host "SpecKit 目錄: $($result.SPECIFY_DIR)" -ForegroundColor Green
        Write-Host "憲章檔案: $(if ($hasConstitution) {'✓ 存在'} else {'✗ 不存在'})" -ForegroundColor $(if ($hasConstitution) {'Green'} else {'Yellow'})

        if ($featureDir) {
            Write-Host "`n功能目錄: $featureDir" -ForegroundColor Cyan
            Write-Host "  spec.md:  $(if ($availableDocs.spec) {'✓'} else {'✗'})" -ForegroundColor $(if ($availableDocs.spec) {'Green'} else {'Red'})
            Write-Host "  plan.md:  $(if ($availableDocs.plan) {'✓'} else {'✗'})" -ForegroundColor $(if ($availableDocs.plan) {'Green'} else {'Red'})
            Write-Host "  tasks.md: $(if ($availableDocs.tasks) {'✓'} else {'✗'})" -ForegroundColor $(if ($availableDocs.tasks) {'Green'} else {'Red'})
        } else {
            Write-Host "`n尚未建立功能目錄" -ForegroundColor Yellow
        }
    }

    exit 0

} catch {
    if ($Json) {
        @{
            ERROR = $_.Exception.Message
            SUCCESS = $false
        } | ConvertTo-Json
    } else {
        Write-Error $_.Exception.Message
    }
    exit 1
}
