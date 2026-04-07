# Store Ollama model blobs inside this repo. Set once, restart Ollama, then: ollama pull <model>

$target = Join-Path $PSScriptRoot "..\data\ollama-models"
New-Item -ItemType Directory -Force -Path $target | Out-Null
$modelsDir = (Resolve-Path $target).Path

[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $modelsDir, "User")
Write-Host "OLLAMA_MODELS set (User) to: $modelsDir"
Write-Host "Restart the Ollama application, then run: ollama pull <model>"
