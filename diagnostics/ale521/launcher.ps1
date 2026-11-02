$ErrorActionPreference='Stop'
$env:PYTHONDONTWRITEBYTECODE='1'
Add-Type -AssemblyName System.Windows.Forms
function Notice([string]$text) { [System.Windows.Forms.MessageBox]::Show($text,'ALE-521: диагностика') | Out-Null }
try {
 $folder=New-Object System.Windows.Forms.FolderBrowserDialog
 $folder.Description='Выберите папку работающей программы (там находится start_windows.bat и .venv)'
 if($folder.ShowDialog() -ne 'OK'){exit 0}
 $app=$folder.SelectedPath
 $python=Join-Path $app '.venv\Scripts\python.exe'
 if(!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath (Join-Path $app 'backend\app\version.py'))){
  Notice 'В этой папке не найдено существующее окружение программы. Выберите папку, из которой обычно запускаете приложение. Ничего устанавливать не нужно.';exit 1
 }
 $pick=New-Object System.Windows.Forms.OpenFileDialog
 $pick.Title='Выберите финальный XLSX, который не удаётся импортировать'
 $pick.Filter='Файлы Excel (*.xlsx)|*.xlsx';$pick.CheckFileExists=$true
 if($pick.ShowDialog() -ne 'OK'){exit 0}
 $save=New-Object System.Windows.Forms.SaveFileDialog
 $save.Title='Куда сохранить безопасный JSON для передачи Александру?'
 $save.Filter='JSON (*.json)|*.json';$save.FileName=('ALE521_diagnostic_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.json')
 $save.InitialDirectory=[Environment]::GetFolderPath('Desktop')
 if($save.ShowDialog() -ne 'OK'){exit 0}
 if(Test-Path -LiteralPath $save.FileName){Notice 'Выберите новое имя JSON, существующий отчёт не перезаписывается.';exit 1}
 $probe=& $python -B -c 'import sys,sqlite3,openpyxl,dotenv,pydantic;assert sys.version_info>=(3,11)' 2>&1
 if($LASTEXITCODE -ne 0){Notice 'Существующее окружение не запускается или в нём нет зависимостей приложения. Не устанавливайте Python и не обновляйте программу: передайте Александру это сообщение и укажите выбранную папку.';exit 1}
 Write-Host 'Проверяем файл и карточки. Приложение не останавливается; данные не записываются. Подождите.'
 Push-Location -LiteralPath $app
 try {
  $answer=& $python -B (Join-Path $PSScriptRoot 'diagnose_enrichment_import.py') --app-dir $app --xlsx $pick.FileName --output $save.FileName 2>&1
  $code=$LASTEXITCODE
 } finally {Pop-Location}
 if($code -ne 0 -or !(Test-Path -LiteralPath $save.FileName)){Notice 'JSON не создан. Передайте Александру сообщение «Диагностический комплект не смог завершить проверку». Ключи и файлы базы отправлять не нужно.';exit 1}
 Notice ('Готово. Передайте Александру только JSON:'+[Environment]::NewLine+$save.FileName+[Environment]::NewLine+'Наличие ошибок в JSON — результат диагностики, а не потеря биографий.')
} catch {Notice 'Не удалось запустить комплект. Ничего не устанавливайте и не меняйте: передайте Александру это сообщение.';exit 1}
