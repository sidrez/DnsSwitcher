$ErrorActionPreference = "Stop"

$namespace = ".rgn.ukunistroy.ru"
$plainNamespace = "rgn.ukunistroy.ru"
$nameServers = @("10.0.1.120", "10.0.1.186")
$policyPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient\DnsPolicyConfig"
$displayName = "Change_DNS_MALW corporate split DNS"
$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$legacyHostsBegin = "# BEGIN Change_DNS_MALW corporate DNS fallback"
$legacyHostsEnd = "# END Change_DNS_MALW corporate DNS fallback"

# Remove the old static fallback. It covered only SMB host A records, masked
# broken AD SRV resolution and could retain obsolete file-server addresses.
try {
    $hostsText = [System.IO.File]::ReadAllText($hostsPath)
    $legacyPattern = (
        "(?ms)^" + [regex]::Escape($legacyHostsBegin) +
        "\r?\n.*?^" + [regex]::Escape($legacyHostsEnd) + "\r?\n?"
    )
    $updatedHostsText = [regex]::Replace($hostsText, $legacyPattern, "")
    if ($updatedHostsText -ne $hostsText) {
        [System.IO.File]::WriteAllText(
            $hostsPath,
            $updatedHostsText,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
}
catch {
    Write-Warning ("Legacy hosts cleanup skipped: " + $_.Exception.Message)
}

# Domain Group Policy creates an empty DnsPolicyConfig key. While it exists,
# Windows ignores the local NRPT rule and sends domain queries to external DNS.
# Never remove a non-empty policy key because it can contain legitimate GPO rules.
if (Test-Path -LiteralPath $policyPath) {
    $policyChildren = @(Get-ChildItem -LiteralPath $policyPath -ErrorAction Stop)
    if ($policyChildren.Count -eq 0) {
        Remove-Item -LiteralPath $policyPath -Force
    }
    else {
        $policyRule = @(
            Get-DnsClientNrptPolicy -Effective |
                Where-Object {
                    $_.Namespace -contains $namespace -and
                    ((@($_.NameServers) | Sort-Object) -join ",") -eq
                        (($nameServers | Sort-Object) -join ",")
                }
        )
        if ($policyRule.Count -gt 0) {
            Clear-DnsClientCache
            Write-Output "Corporate split DNS is already provided by effective GPO policy."
            exit 0
        }

        throw "A non-empty DnsPolicyConfig policy key overrides corporate split DNS."
    }
}

$localRules = @(
    Get-DnsClientNrptRule |
        Where-Object {
            $_.Namespace -contains $namespace -or
            $_.Namespace -contains $plainNamespace
        }
)
if ($localRules.Count -gt 0) {
    $localRules | Remove-DnsClientNrptRule -Force
}

Add-DnsClientNrptRule `
    -Namespace $namespace `
    -NameServers $nameServers `
    -DisplayName $displayName `
    -Comment "Corporate DNS for AD and SMB resources"

Clear-DnsClientCache

$effectiveRules = @(
    Get-DnsClientNrptPolicy -Effective |
        Where-Object {
            $_.Namespace -contains $namespace -and
            ((@($_.NameServers) | Sort-Object) -join ",") -eq
                (($nameServers | Sort-Object) -join ",")
        }
)
if ($effectiveRules.Count -ne 1) {
    throw "The corporate NRPT rule is not present in effective policy."
}

Write-Output "Corporate split DNS is active."
