# Sync Script Audit — AgentBus

## Вердикт

**Скрипт работоспособен, но имеет критические уязвимости.**

Скрипт `D:\Workspace\mirror-to-drive.ps1` (388 строк) выполняет синхронизацию `D:\Workspace\AgentBus` → `F:\Мой диск\AgentBus` через robocopy + git. Архитектурно продуман (снимок состояния, лимиты удалений, фильтрация мусора), но содержит несколько мест с риском потери данных.

---

## Найденные уязвимости

### 1. Дубликаты на Drive (КРИТИЧНО)

**Проблема:** robocopy с флагом `/E` копирует все файлы, но **не удаляет** лишние на приёмнике. Если файл переименован локально, robocopy создаст новую копию на Drive, а старый останется.

**Строки:** 160–162
```powershell
$rcArgs = @($SOURCE, $DRIVE, '/E', '/FFT', '/XJ', '/NFL', '/NDL',
            '/NJH', '/NJS', '/NP', '/R:2', '/W:2', '/XD') + $dirMasks + @('/XF') + $fileMasks
```

**Почему происходит:** `/E` = копировать все подкаталоги, включая пустые. Нет флага `/MIR` (зеркалирование с удалением). Удаление выполняется только через снимок состояния (этап 5), но он отслеживает только файлы, которые были на ПК в прошлый раз. Переименование не отслеживается.

**Риск:** При переименовании файла на ПК, старый файл останется на Drive до следующего цикла удаления, и может быть закоммичен в GitHub как отдельный файл.

---

### 2. Очистка устаревших файлов (СРЕДНЕ)

**Проблема:** Логика удаления с Drive (этап 5) зависит от снимка `mirror-state.json`. Если снимок повреждён или потерян, удаления не произойдут вообще.

**Строки:** 236–243
```powershell
$prev = @()
if (Test-Path $STATE) {
    try {
        $saved = Get-Content $STATE -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.files) { $prev = @($saved.files) }
    } catch { Write-Log 'снимок не читается, удаления в этот раз пропущены' }
}
```

**Почему происходит:** При ошибке чтения снимка скрипт молча пропускает удаления. Нет резервной копии снимка.

**Риск:** При повреждении `mirror-state.json` файлы, удалённые на ПК, останутся на Drive неограниченно долго.

---

### 3. Обработка ошибок robocopy (СРЕДНЕ)

**Проблема:** При ошибке доступа к файлу (заблокирован редактором) robocopy возвращает код ≥ 8, и скрипт прерывает работу. Нет механизма повторных попыток для отдельных файлов.

**Строки:** 163–167
```powershell
$code = $LASTEXITCODE
if ($code -ge 8) {
    $err = (@($out | Where-Object { $_ -match 'ERROR|Access|denied' }) -join '; ')
    throw "robocopy код $code. $err"
}
```

**Почему происходит:** `$ErrorActionPreference = 'Stop'` (строка 46) превращает любую ошибку в критическую.

**Риск:** Один заблокированный файл останавливает всю синхронизацию.

---

### 4. Фильтрация .gitignore (НИЗКО)

**Проблема:** Фильтрация мусора через `git check-ignore` работает корректно, но список `$NEVER_TOUCH` и `$JUNK_DIRS` дублирует логику `.gitignore`. Расхождение между ними уже было зафиксировано в комментариях скрипта.

**Строки:** 58–69
```powershell
$NEVER_TOUCH = @(
    '.git', '.venv', '.venv-aider', 'venv', 'env', 'node_modules',
    '.agentbus', '.testruns'
)
$JUNK_DIRS = @(
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov',
    'dist', 'build', '*.egg-info', '.idea', '.vscode',
    'channels', 'events', 'logs', 'incoming', 'projects',
    'gemini_archive', 'GeminiProcessed'
)
```

**Риск:** При добавлении новых мусорных файлов в `.gitignore` нужно синхронно обновлять скрипт.

---

### 5. Блокировка файлов (НИЗКО)

**Проблема:** Файл заблокирован другой программой вызовет ошибку robocopy. Нет механизма ожидания или пропуска.

**Строки:** 84–90 (блокировка через lock-файл)
```powershell
if (Test-Path $LOCK) {
    if (((Get-Date) - (Get-Item $LOCK).LastWriteTime).TotalMinutes -lt 9) { exit 0 }
    Remove-Item $LOCK -Force
}
```

**Риск:** Два параллельных запуска скрипта могут конфликтовать.

---

## Рекомендуемый рефакторинг

### 1. Безопасное копирование с проверкой хеша

```powershell
# Замена этапа 2 (строки 159-168)
function Copy-FileSafe {
    param([string]$Source, [string]$Dest)
    
    $srcHash = (Get-FileHash -Path $Source -Algorithm SHA256 -ErrorAction SilentlyContinue).Hash
    $destHash = $null
    if (Test-Path $Dest) {
        $destHash = (Get-FileHash -Path $Dest -Algorithm SHA256 -ErrorAction SilentlyContinue).Hash
    }
    
    if ($srcHash -eq $destHash) { return $true }
    
    $retry = 0
    while ($retry -lt 3) {
        try {
            Copy-Item -Path $Source -Destination $Dest -Force -ErrorAction Stop
            $newHash = (Get-FileHash -Path $Dest -Algorithm SHA256).Hash
            if ($newHash -eq $srcHash) { return $true }
        } catch {
            $retry++
            Start-Sleep -Seconds 2
        }
    }
    return $false
}
```

### 2. Безопасная очистка с резервной копией снимка

```powershell
# Замена этапа 4 (строки 236-243)
$prev = @()
$stateBackup = "$STATE.bak"
if (Test-Path $STATE) {
    try {
        Copy-Item -Path $STATE -Destination $stateBackup -Force -ErrorAction SilentlyContinue
        $saved = Get-Content $STATE -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.files) { $prev = @($saved.files) }
    } catch {
        Write-Log 'снимок не читается, пробуем резервную копию'
        if (Test-Path $stateBackup) {
            try {
                $saved = Get-Content $stateBackup -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($saved.files) { $prev = @($saved.files) }
                Write-Log 'резервная копия снимка загружена'
            } catch {
                Write-Log 'резервная копия тоже повреждена, удаления пропущены'
            }
        }
    }
}
```

### 3. Улучшенная обработка ошибок robocopy

```powershell
# Замена этапа 2 (строки 163-167)
$code = $LASTEXITCODE
if ($code -ge 8) {
    $err = (@($out | Where-Object { $_ -match 'ERROR|Access|denied' }) -join '; ')
    # Пробуем повторить с флагом /COPY:DAT (без ACL)
    Write-Log "robocopy код $code, пробуем повторить с /COPY:DAT"
    $rcArgs2 = @($SOURCE, $DRIVE, '/E', '/FFT', '/XJ', '/NFL', '/NDL',
                 '/NJH', '/NJS', '/NP', '/R:1', '/W:1', '/COPY:DAT', '/XD') + $dirMasks + @('/XF') + $fileMasks
    $out2 = & robocopy @rcArgs2
    $code2 = $LASTEXITCODE
    if ($code2 -ge 8) {
        throw "robocopy повторно код $code2. $err"
    }
}
```

### 4. Удаление дубликатов при переименовании

```powershell
# Добавить после этапа 2 (после строки 168)
# Сравниваем хеши файлов на Drive и удаляем дубликаты
$driveFiles = Get-ChildItem $DRIVE -Recurse -File -Force -ErrorAction SilentlyContinue |
              Where-Object { $_.FullName.Substring($DRIVE.Length + 1) -notmatch '^(NEVER_TOUCH)' }
$hashMap = @{}
foreach ($f in $driveFiles) {
    $rel = $f.FullName.Substring($DRIVE.Length + 1) -replace '\\', '/'
    if (Test-AnyDir $rel $NEVER_TOUCH) { continue }
    $hash = (Get-FileHash -Path $f.FullName -Algorithm SHA256 -ErrorAction SilentlyContinue).Hash
    if ($hash) {
        if ($hashMap.ContainsKey($hash)) {
            # Дубликат — удаляем
            try {
                Remove-Item -LiteralPath $f.FullName -Force
                Write-Log "  удалён дубликат: $rel"
            } catch {
                Write-Log "  НЕ удалён дубликат $rel : $($_.Exception.Message)"
            }
        } else {
            $hashMap[$hash] = $rel
        }
    }
}
```

---

## Чек-лист для ручной проверки

### Тест 1: Базовая синхронизация
1. Создайте тестовый файл `D:\Workspace\AgentBus\test_sync.txt`
2. Запустите скрипт: `powershell -File D:\Workspace\mirror-to-drive.ps1`
3. Проверьте, что файл появился на `F:\Мой диск\AgentBus\test_sync.txt`
4. Удалите файл локально
5. Запустите скрипт повторно
6. Убедитесь, что файл удалился с Drive

### Тест 2: Переименование файла
1. Создайте `D:\Workspace\AgentBus\test_rename.txt`
2. Запустите скрипт
3. Переименуйте файл в `test_renamed.txt`
4. Запустите скрипт
5. Проверьте, что на Drive есть только `test_renamed.txt` (старый удалён)

### Тест 3: Мусорные файлы
1. Создайте `D:\Workspace\AgentBus\__pycache__\test.pyc`
2. Создайте `D:\Workspace\AgentBus\.env`
3. Запустите скрипт
4. Убедитесь, что эти файлы НЕ появились на Drive

### Тест 4: Заблокированный файл
1. Откройте файл на Drive в текстовом редакторе
2. Запустите скрипт
3. Убедитесь, что скрипт не упал, а записал ошибку в лог

### Тест 5: Повреждение снимка
1. Остановите скрипт
2. Повредите `D:\Workspace\logs\mirror-state.json` (добавьте мусор)
3. Запустите скрипт
4. Убедитесь, что скрипт загрузил резервную копию и продолжил работу

### Тест 6: Лимит удалений
1. Удалите локально 30+ файлов
2. Запустите скрипт
3. Убедитесь, что скрипт остановился с сообщением о превышении лимита
4. Удалите ещё 10 файлов
5. Запустите скрипт
6. Убедитесь, что удаления прошли

---

## Дополнительные рекомендации

1. **Добавить логирование в файл с ротацией** — сейчас лог только при превышении 2MB
2. **Добавить уведомления об ошибках** — через Windows Event Log или email
3. **Добавить dry-run режим** — для проверки изменений без применения
4. **Добавить проверку целостности снимка** — через контрольную сумму
5. **Рассмотреть переход на rclone** — более надёжный инструмент для синхронизации с облачными хранилищами
