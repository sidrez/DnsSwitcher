using System.Diagnostics;
using System.Net;
using System.Text.RegularExpressions;

namespace DnsSwitcher;

public static class DnsService
{
    public static async Task<(string Name, bool IsDhcp)> GetCurrentAsync(AppConfiguration config)
    {
        var alias = config.InterfaceName.Replace("'", "''");
        var command = "$dns = Get-DnsClientServerAddress -InterfaceAlias '" + alias + "' -AddressFamily IPv4 -ErrorAction Stop; " +
            "$adapter = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object { $_.InterfaceIndex -eq $dns.InterfaceIndex }; " +
            "if ($null -eq $adapter.DNSServerSearchOrder) { '__DHCP__' } else { $dns.ServerAddresses | ForEach-Object { $_.IPAddressToString } }";
        var output = await RunAsync("powershell", $"-NoProfile -Command \"{command}\"");
        var current = output.StandardOutput.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (current.Length == 0 || current.Contains("__DHCP__")) return ("Авто (DHCP)", true);
        var provider = config.Providers.FirstOrDefault(p => p.Ipv4.OrderBy(x => x).SequenceEqual(current.OrderBy(x => x)));
        return provider is null ? ("Неизвестный DNS", false) : (provider.Name, false);
    }

    public static Task<ProcessResult> RunScriptAsync(AppConfiguration config, DnsProvider? provider)
    {
        var script = provider?.Script ?? "Restore-DNS.py";
        var scriptPath = System.IO.Path.Combine(AppContext.BaseDirectory, "Scripts", "DNS", script);
        if (!File.Exists(scriptPath)) throw new FileNotFoundException("Не найден скрипт DNS.", scriptPath);
        var args = $"\"{scriptPath}\" --interface \"{config.InterfaceName}\"";
        if (provider is not null)
            args += $" --ipv4 \"{string.Join(',', provider.Ipv4)}\" --ipv6 \"{string.Join(',', provider.Ipv6)}\" --doh \"{provider.Doh}\"";
        return RunAsync(config.PythonPath, args);
    }

    public static Task<ProcessResult> FlushAsync() => RunAsync("ipconfig", "/flushdns");

    public static async Task<ProcessResult> RunAsync(string fileName, string arguments)
    {
        using var process = new Process { StartInfo = new ProcessStartInfo(fileName, arguments) { CreateNoWindow = true, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true } };
        process.Start();
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        return new ProcessResult(process.ExitCode, await stdout, await stderr);
    }
}

public sealed record ProcessResult(int ExitCode, string StandardOutput, string StandardError);

public static class ProviderCheckService
{
    private static readonly HttpClient Client = new() { Timeout = TimeSpan.FromSeconds(12) };
    public static async Task<List<string>> FindIpv4Async(DnsProvider provider)
    {
        Client.DefaultRequestHeaders.UserAgent.ParseAdd("DnsSwitcher/1.0");
        var html = await Client.GetStringAsync(provider.CheckUrl);
        var relevant = Regex.Match(html, "(?is)(?:стандартн\\w*|standard|DNS.{0,80}(?:сервер|server|адрес|address)).{0,2500}");
        if (!relevant.Success) throw new InvalidOperationException("На странице не найден блок со стандартными DNS-адресами.");
        var ips = Regex.Matches(relevant.Value, @"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])")
            .Select(m => IPAddress.Parse(m.Value).ToString()).Distinct().Take(2).ToList();
        return ips.Count == 2 ? ips : throw new InvalidOperationException("Не удалось надёжно извлечь два DNS-адреса из релевантного блока страницы.");
    }
}
