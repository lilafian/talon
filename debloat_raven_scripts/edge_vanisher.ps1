# Edge Vanisher
# filename: edge_vanisher.ps1
#
# This script's purpose is to remove Edge from Windows 11 systems and prevent the system from reinstalling it.
# The user can still reinstall Edge by downloading it from Microsoft's website. Preserves msedgewebview2.


if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
	[Security.Principal.WindowsBuiltInRole]::Administrator)) {
	Write-Host "Administrator rights required." -ForegroundColor Red
	exit 1
}

$edgeInstaller = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\*\Installer\setup.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($edgeInstaller) {
	Start-Process $edgeInstaller.FullName -ArgumentList "--uninstall --system-level --force-uninstall --verbose-logging" -Wait
}

Get-Process | Where-Object { $_.Name -like "*edge*" } | Stop-Process -Force -ErrorAction SilentlyContinue

$pathsToRemove = @(
	"$env:LOCALAPPDATA\Microsoft\Edge",
	"${env:ProgramFiles(x86)}\Microsoft\Edge",
	"${env:ProgramFiles(x86)}\Microsoft\EdgeCore",
	"$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Microsoft Edge.lnk",
	"$env:PUBLIC\Desktop\Microsoft Edge.lnk"
)

foreach ($path in $pathsToRemove) {
	if (Test-Path $path) {
		takeown /F $path /R /D Y | Out-Null
		icacls $path /grant Administrators:F /T | Out-Null
		Remove-Item -Path $path -Recurse -Force -ErrorAction SilentlyContinue
	}
}

$regKeys = @(
	"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
	"HKLM:\SOFTWARE\Microsoft\Edge",
	"HKLM:\SOFTWARE\WOW6432Node\Microsoft\Edge",
	"HKCU:\Software\Microsoft\Edge"
)

foreach ($key in $regKeys) {
	if (Test-Path $key) {
		Remove-Item -Path $key -Recurse -Force -ErrorAction SilentlyContinue
	}
}

$protectBase = "${env:ProgramFiles(x86)}\Microsoft\Edge"
$protectApp  = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application"

New-Item -ItemType Directory -Path $protectBase -Force | Out-Null
New-Item -ItemType Directory -Path $protectApp -Force | Out-Null

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner([System.Security.Principal.NTAccount]$currentUser)
$acl.SetAccessRuleProtection($true, $false)

$allowRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
	$currentUser,
	"FullControl,TakeOwnership,ChangePermissions",
	"ContainerInherit,ObjectInherit",
	"None",
	"Allow"
)

$denySids = @(
	"S-1-5-18",
	"S-1-5-32-544",
	"S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
)

$acl.AddAccessRule($allowRule)

foreach ($sid in $denySids) {
	$acl.AddAccessRule(
		(New-Object System.Security.AccessControl.FileSystemAccessRule(
			(New-Object System.Security.Principal.SecurityIdentifier($sid)),
			"TakeOwnership,ChangePermissions",
			"ContainerInherit,ObjectInherit",
			"None",
			"Deny"
		))
	)
}

Set-Acl -Path $protectBase -AclObject $acl

Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Process explorer
