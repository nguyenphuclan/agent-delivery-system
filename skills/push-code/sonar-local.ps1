param(
    [Parameter(Mandatory)] [string] $Repo,
    [Parameter(Mandatory)] [string] $Key,
    [Parameter(Mandatory)] [string] $Org,            # Sonar organization (/o:), from projects.<active>.sonar.org
    [Parameter(Mandatory)] [string] $HostUrl,        # Sonar server URL, from projects.<active>.sonar.host
    [Parameter(Mandatory)] [string] $Build,          # .sln or .csproj to build
    [Parameter(Mandatory)] [string] $TestTarget,     # test project or sln for dotnet test
    [string] $Exclusions = "",
    [string] $CoverageExclusions = "",
    [string] $Filter = ""
)
# push-code step 4 for ONE repo: begin -> ONE no-incremental Debug build -> scoped coverage.
# No `end`, nothing uploaded. Token comes from $env:SONAR_TOKEN and is never echoed.
$ErrorActionPreference = "Continue"
Set-Location $Repo
if (-not $env:SONAR_TOKEN) { Write-Output "NO SONAR_TOKEN"; exit 2 }

$args_ = @("sonarscanner", "begin", "/k:$Key", "/o:$Org",
           "/d:sonar.token=$($env:SONAR_TOKEN)", "/d:sonar.host.url=$HostUrl",
           "/d:sonar.cs.vscoveragexml.reportsPaths=coverage.xml")
if ($Exclusions) { $args_ += "/d:sonar.exclusions=$Exclusions" }
if ($CoverageExclusions) { $args_ += "/d:sonar.coverage.exclusions=$CoverageExclusions" }
$begin = & dotnet @args_ 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Write-Output "BEGIN FAILED"; ($begin -replace [regex]::Escape($env:SONAR_TOKEN), "***") | Select-Object -Last 15; exit 2 }
Write-Output "begin ok"

$build = & dotnet build $Build --no-incremental -c Debug -nologo -v q 2>&1 | Out-String
$errLine = ($build -split "`n" | Where-Object { $_ -match "error CS|Build FAILED|\d+ Error\(s\)" } | Select-Object -First 5) -join "`n"
if ($build -notmatch "Build succeeded" -or $build -match "[1-9]\d* Error\(s\)") { Write-Output "BUILD FAILED"; $errLine; exit 2 }
Write-Output "build ok"

$testCmd = "dotnet test $TestTarget --no-build -c Debug"
if ($Filter) { $testCmd += " --filter `"$Filter`"" }
if (Test-Path coverage.xml) { Remove-Item coverage.xml -Force }
$cov = & dotnet-coverage collect $testCmd -f xml -o coverage.xml 2>&1 | Out-String
($cov -split "`n" | Where-Object { $_ -match "Passed!|Failed!|Total tests|error" } | Select-Object -Last 4) -join "`n"
if (-not (Test-Path coverage.xml)) { Write-Output "NO coverage.xml"; exit 2 }
Write-Output ("coverage.xml {0} KB" -f [int]((Get-Item coverage.xml).Length / 1KB))

Get-ChildItem .sonarqube/out -Directory | ForEach-Object {
    $pi = Join-Path $_.FullName "ProjectInfo.xml"
    $name = if (Test-Path $pi) { ([xml](Get-Content $pi)).ProjectInfo.ProjectName } else { "?" }
    $iss = Get-ChildItem $_.FullName -Filter Issues.json -ErrorAction SilentlyContinue | Select-Object -First 1
    "{0}  {1}  Issues.json={2}" -f $_.Name, $name, $(if ($iss) { $iss.LastWriteTime.ToString("HH:mm:ss") } else { "none" })
}
