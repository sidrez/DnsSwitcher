namespace DnsSwitcher;

public sealed class MainForm : Form
{
    private readonly Label _indicator = new() { AutoSize = true, Font = new Font("Segoe UI", 14, FontStyle.Bold), ForeColor = Color.Gainsboro, Location = new Point(24, 22) };
    private readonly Label _status = new() { AutoSize = false, ForeColor = Color.Silver, Location = new Point(24, 247), Size = new Size(392, 34) };
    private readonly List<Button> _switchButtons = [];
    private AppConfiguration _config = null!;

    public MainForm()
    {
        Text = "DnsSwitcher"; ClientSize = new Size(440, 300); FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; BackColor = Color.FromArgb(30, 30, 30); StartPosition = FormStartPosition.CenterScreen;
        Controls.Add(_indicator); Controls.Add(_status);
        AddButton("COMSS", 24, async () => await SwitchAsync("comss"));
        AddButton("Xbox DNS", 160, async () => await SwitchAsync("xbox"));
        AddButton("MALW", 296, async () => await SwitchAsync("malw"));
        AddButton("Сбросить на DHCP", 24, 146, async () => await SwitchAsync(null), 272);
        var settings = new Button { Text = "Настройки", Location = new Point(24, 200), Size = new Size(392, 34), FlatStyle = FlatStyle.Flat, ForeColor = Color.Gainsboro, BackColor = Color.FromArgb(55, 55, 55) };
        settings.Click += (_, _) => { using var dialog = new SettingsForm(_config); if (dialog.ShowDialog(this) == DialogResult.OK) { _config = ConfigurationStore.Load(); _ = RefreshIndicatorAsync(); } };
        Controls.Add(settings);
        Load += async (_, _) => { try { _config = ConfigurationStore.Load(); await RefreshIndicatorAsync(); } catch (Exception ex) { SetStatus(ex.Message); } };
    }

    private void AddButton(string text, int x, Func<Task> handler, int width = 120) => AddButton(text, x, 78, handler, width);
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
            if (result.ExitCode != 0) throw new InvalidOperationException(string.IsNullOrWhiteSpace(result.StandardError) ? result.StandardOutput : result.StandardError);
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
}
