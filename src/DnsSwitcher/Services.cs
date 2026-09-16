using System.Diagnostics;
using System.Net;
using System.Text;
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
        var scriptPath = ResolveScriptPath(script);
        var args = $"-X utf8 \"{scriptPath}\" --interface \"{config.InterfaceName}\"";
        if (provider is not null)
            args += $" --ipv4 \"{string.Join(',', provider.Ipv4)}\" --ipv6 \"{string.Join(',', provider.Ipv6)}\" --doh \"{provider.Doh}\"";
        return RunAsync(config.PythonPath, args);
    }

    private static string ResolveScriptPath(string script)
    {
        var candidates = new[]
        {
            System.IO.Path.Combine(AppContext.BaseDirectory, "Scripts", "DNS", script),
            System.IO.Path.Combine(Environment.CurrentDirectory, "Scripts", "DNS", script),
        };
        var scriptPath = candidates.FirstOrDefault(File.Exists);
        return scriptPath ?? throw new FileNotFoundException(
            "Не найден скрипт DNS. Запускайте DnsSwitcher.exe вместе с папкой Scripts из каталога publish.",
            candidates[0]);
    }

    public static Task<ProcessResult> FlushAsync() => RunAsync("ipconfig", "/flushdns");

    public static async Task<ProcessResult> RunAsync(string fileName, string arguments)
    {
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo(fileName, arguments)
            {
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            },
        };
        process.StartInfo.Environment["PYTHONUTF8"] = "1";
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
        using var response = await Client.GetAsync(provider.CheckUrl);
        response.EnsureSuccessStatusCode();
        var html = Encoding.UTF8.GetString(await response.Content.ReadAsByteArrayAsync());
        return FindDnsPair(html);
    }

    private static List<string> FindDnsPair(string html)
    {
        var matches = Regex.Matches(html, @"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])")
            .Cast<Match>().ToList();
        var pairs = new Dictionary<string, (List<string> Addresses, int Count, int Position)>();

        for (var index = 0; index < matches.Count - 1; index++)
        {
            var first = matches[index];
            var second = matches[index + 1];
            if (second.Index - first.Index > 700) continue;

            var contextStart = Math.Max(0, first.Index - 500);
            var context = html.Substring(contextStart, Math.Min(900, html.Length - contextStart));
            if (!Regex.IsMatch(context, @"(?i)DNS|IPv4|server|address|сервер|адрес")) continue;

            var addresses = new[] { IPAddress.Parse(first.Value).ToString(), IPAddress.Parse(second.Value).ToString() }.ToList();
            var key = string.Join(",", addresses);
            pairs[key] = pairs.TryGetValue(key, out var existing)
                ? (existing.Addresses, existing.Count + 1, existing.Position)
                : (addresses, 1, first.Index);
        }

        var best = pairs.Values.OrderByDescending(pair => pair.Count).ThenBy(pair => pair.Position).FirstOrDefault();
        return best.Addresses ?? throw new InvalidOperationException("На странице не найдена пара IPv4, отмеченная как DNS-настройка.");
    }
}
