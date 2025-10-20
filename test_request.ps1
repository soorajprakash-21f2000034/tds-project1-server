# test_request.ps1

$uri = "http://127.0.0.1:8000/handle_task"

$headers = @{
    "Content-Type" = "application/json"
}

$body = @{
    secret = "imfromthepalebluedot"
    round = 1
    task = "test_task"
    email = "you@example.com"
    brief = "Build a simple page"
    checks = @()
    attachments = @()
    evaluation_url = "https://example.com/eval"
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest -Uri $uri -Method Post -Headers $headers -Body $body
    Write-Host "Status Code:" $response.StatusCode
    Write-Host "Response Body:"
    Write-Host $response.Content
} catch {
    Write-Error "Request failed: $($_.Exception.Message)"
}