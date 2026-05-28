# Start the ArXiv MCP Server as a standalone HTTP service.
# The FastAPI backend connects to it at http://127.0.0.1:8081/sse

$env:TRANSPORT = "http"
$env:HOST = "127.0.0.1"
$env:PORT = "8081"

$storagePath = "$PSScriptRoot\arxiv_papers"
if (-not (Test-Path $storagePath)) {
    New-Item -ItemType Directory -Path $storagePath | Out-Null
    Write-Host "Created paper storage directory: $storagePath"
}

Write-Host "Starting ArXiv MCP Server on http://127.0.0.1:8081 ..."
Write-Host "SSE endpoint: http://127.0.0.1:8081/sse"
Write-Host "Press Ctrl+C to stop."

try {
    $exePath = "$PSScriptRoot\.mcp-venv\Scripts\arxiv-mcp-server.exe"
    $cmdLine = '"{0}" --storage-path "{1}" 2>&1' -f $exePath, $storagePath
    cmd /c $cmdLine | Where-Object {
        # Filter out benign Windows async cleanup errors during shutdown
        $_ -notmatch "ConnectionResetError|CancelledError|KeyboardInterrupt|_ProactorBasePipeTransport"
    }
} catch {
    # Suppress KeyboardInterrupt errors on Ctrl+C (normal shutdown)
    if ($_ -match "KeyboardInterrupt|Cancelled") {
        Write-Host "MCP Server stopped."
    } else {
        Write-Error $_
    }
}
