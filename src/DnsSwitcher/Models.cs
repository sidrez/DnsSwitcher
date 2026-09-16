using System.Text.Json;

namespace DnsSwitcher;

public sealed class AppConfiguration
{
    public string PythonPath { get; set; } = "python";
    public string InterfaceName { get; set; } = "Ethernet";
    public List<DnsProvider> Providers { get; set; } = [];
}

public sealed class DnsProvider
{
    public string Key { get; set; } = "";
    public string Name { get; set; } = "";
    public List<string> Ipv4 { get; set; } = [];
    public List<string> Ipv6 { get; set; } = [];
    public string Doh { get; set; } = "";
    public string CheckUrl { get; set; } = "";
    public string Script { get; set; } = "";
}

public static class ConfigurationStore
{
    private static readonly JsonSerializerOptions Options = new() { PropertyNameCaseInsensitive = true, WriteIndented = true };
    public static string Path => System.IO.Path.Combine(AppContext.BaseDirectory, "providers.json");
    public static AppConfiguration Load() => JsonSerializer.Deserialize<AppConfiguration>(File.ReadAllText(Path), Options)
        ?? throw new InvalidDataException("providers.json пуст или имеет неверный формат.");
    public static void Save(AppConfiguration config) => File.WriteAllText(Path, JsonSerializer.Serialize(config, Options));
}
