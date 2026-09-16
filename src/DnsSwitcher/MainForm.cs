namespace DnsSwitcher;

public sealed class MainForm : Form
{
    private readonly Label _indicator = new() { AutoSize = true, Font = new Font("Segoe UI", 14, FontStyle.Bold), ForeColor = Color.Gainsboro, Location = new Point(24, 22) };
    private readonly Label _status = new() { AutoSize = false, ForeColor = Color.Silver, Location = new Point(20, 220), Size = new Size(400, 54) };
    private readonly List<Button> _switchButtons = [];
    private AppConfiguration _config = null!;

    public MainForm()
    {
        Text = "DnsSwitcher"; ClientSize = new Size(440, 300); FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; BackColor = Color.FromArgb(30, 30, 30); StartPosition = FormStartPosition.CenterScreen;
        Controls.Add(_indicator); Controls.Add(_status);
        AddButton("COMSS", 20, 78, async () => await SwitchAsync("comss"), 126);
        AddButton("Xbox DNS", 157, 78, async () => await SwitchAsync("xbox"), 126);
        AddButton("MALW", 294, 78, async () => await SwitchAsync("malw"), 126);
        AddButton("Сбросить на DHCP", 20, 146, async () => await SwitchAsync(null), 195);
        var settings = new Button { Text = "Настройки", Location = new Point(225, 146), Size = new Size(195, 48), FlatStyle = FlatStyle.Flat, ForeColor = Color.Gainsboro, BackColor = Color.FromArgb(55, 55, 55) };
        settings.Click += (_, _) => { using var dialog = new SettingsForm(_config); if (dialog.ShowDialog(this) == DialogResult.OK) { _config = ConfigurationStore.Load(); _ = RefreshIndicatorAsync(); } };
        Controls.Add(settings);
        Load += async (_, _) => { try { _config = ConfigurationStore.Load(); await RefreshIndicatorAsync(); } catch (Exception ex) { SetStatus(ex.Message); } };
    }

    private void AddButton(string text, int x, int y, Func<Task> handler, int width)
    {
        var button = new Button { Text = text, Location = new Point(x, y), Size = new Size(width, 48), FlatStyle = FlatStyle.Flat, ForeColor = Color.White, BackColor = Color.FromArgb(55, 55, 55) };
        button.Click += async (_, _) => await handler(); _switchButtons.Add(button); Controls.Add(button);
    }

    private async Task SwitchAsync(string? key)
    {
        try
        {
            ToggleSwitchButtons(false); SetStatus("Выполняется переключение DNS…");
            var provider = key is null ? null : _config.Providers.Single(p => p.Key == key);
            var result = await DnsService.RunScriptAsync(_config, provider);
            if (result.ExitCode != 0) throw new InvalidOperationException(FormatScriptError(result));
            await DnsService.FlushAsync(); await RefreshIndicatorAsync();
            SetStatus(key is null ? "DNS возвращён в автоматический режим (DHCP)." : $"DNS переключён на {provider!.Name}.");
        }
        catch (Exception ex) { SetStatus("Ошибка: " + ex.Message.Trim()); }
        finally { ToggleSwitchButtons(true); }
    }

    private async Task RefreshIndicatorAsync()
    {
        var current = await DnsService.GetCurrentAsync(_config);
        _indicator.Text = "●  " + current.Name;
        _indicator.ForeColor = current.IsDhcp ? Color.DeepSkyBlue : current.Name == "Неизвестный DNS" ? Color.OrangeRed : Color.LightGreen;
    }
    private void ToggleSwitchButtons(bool enabled) => _switchButtons.ForEach(b => b.Enabled = enabled);
    private void SetStatus(string text) => _status.Text = text;

    private static string FormatScriptError(ProcessResult result)
    {
        var message = string.Join('\n', (result.StandardError + "\n" + result.StandardOutput)
            .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(line => !line.StartsWith("[DNS_", StringComparison.Ordinal)));
        return string.IsNullOrWhiteSpace(message) ? $"Скрипт завершился с кодом {result.ExitCode}." : message;
    }
}
