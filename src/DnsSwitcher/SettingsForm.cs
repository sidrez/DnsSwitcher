using System.Diagnostics;

namespace DnsSwitcher;

public sealed class SettingsForm : Form
{
    private readonly AppConfiguration _config;
    private readonly TextBox _python = new();
    private readonly TextBox _interface = new();
    private readonly Dictionary<DnsProvider, (TextBox Ipv4, TextBox Ipv6, TextBox Doh)> _fields = [];

    public SettingsForm(AppConfiguration config)
    {
        _config = config; Text = "Настройки DnsSwitcher"; ClientSize = new Size(750, 535); FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; BackColor = Color.FromArgb(30, 30, 30); ForeColor = Color.Gainsboro; StartPosition = FormStartPosition.CenterParent;
        AddField("Python", _python, config.PythonPath, 20); AddField("Интерфейс", _interface, config.InterfaceName, 55);
        var y = 100;
        foreach (var provider in config.Providers)
        {
            Controls.Add(new Label { Text = provider.Name, ForeColor = Color.LightGreen, Location = new Point(20, y), AutoSize = true }); y += 25;
            var v4 = AddField("IPv4", null, string.Join(',', provider.Ipv4), y); y += 30;
            var v6 = AddField("IPv6", null, string.Join(',', provider.Ipv6), y); y += 30;
            var doh = AddField("DoH", null, provider.Doh, y);
            AddOpenSiteButton(provider, y);
            y += 35; _fields[provider] = (v4, v6, doh);
        }
        var check = new Button { Text = "Проверить актуальность IP", Location = new Point(20, 480), Size = new Size(220, 32) }; check.Click += async (_, _) => await CheckAsync(); Controls.Add(check);
        var save = new Button { Text = "Сохранить", DialogResult = DialogResult.OK, Location = new Point(550, 480), Size = new Size(85, 32) }; save.Click += (_, _) => Save(); Controls.Add(save);
        var cancel = new Button { Text = "Отмена", DialogResult = DialogResult.Cancel, Location = new Point(645, 480), Size = new Size(85, 32) }; Controls.Add(cancel); AcceptButton = save; CancelButton = cancel;
    }
    private TextBox AddField(string label, TextBox? target, string value, int y)
    {
        Controls.Add(new Label { Text = label, Location = new Point(20, y + 5), AutoSize = true }); var box = target ?? new TextBox(); box.Text = value; box.Location = new Point(100, y); box.Size = new Size(510, 23); Controls.Add(box); return box;
    }
    private void AddOpenSiteButton(DnsProvider provider, int y)
    {
        var button = new Button { Text = "Открыть сайт", Location = new Point(620, y - 1), Size = new Size(110, 25) };
        button.Click += (_, _) => Process.Start(new ProcessStartInfo(provider.CheckUrl) { UseShellExecute = true });
        Controls.Add(button);
    }
    private void Save()
    {
        ApplyFieldsToConfiguration();
        ConfigurationStore.Save(_config);
    }

    private void ApplyFieldsToConfiguration()
    {
        _config.PythonPath = _python.Text.Trim(); _config.InterfaceName = _interface.Text.Trim();
        foreach (var (provider, fields) in _fields) { provider.Ipv4 = Split(fields.Ipv4.Text); provider.Ipv6 = Split(fields.Ipv6.Text); provider.Doh = fields.Doh.Text.Trim(); }
    }
    private async Task CheckAsync()
    {
        try
        {
            ApplyFieldsToConfiguration();
            foreach (var provider in _config.Providers)
            {
                var found = await ProviderCheckService.FindIpv4Async(provider);
                if (!provider.Ipv4.SequenceEqual(found) && MessageBox.Show(this, $"{provider.Name}\nЛокально: {string.Join(", ", provider.Ipv4)}\nНа сайте: {string.Join(", ", found)}\n\nОбновить IPv4?", "Обновление DNS", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes) { provider.Ipv4 = found; _fields[provider].Ipv4.Text = string.Join(',', found); }
            }
            MessageBox.Show(this, "Проверка завершена.", "DnsSwitcher");
        }
        catch (Exception ex) { MessageBox.Show(this, ex.Message, "Не удалось проверить IP", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private static List<string> Split(string value) => value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
}
