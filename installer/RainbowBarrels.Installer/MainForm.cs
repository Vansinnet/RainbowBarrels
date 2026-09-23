namespace RainbowBarrels.Installer;

internal sealed class MainForm : Form
{
    private readonly TextBox folder = new() { Dock = DockStyle.Fill };
    private readonly Button browse = new() { Text = "Browse...", AutoSize = true };
    private readonly Button install = new() { Text = "Install", AutoSize = true };
    private readonly Button repair = new() { Text = "Repair", AutoSize = true };
    private readonly Button uninstall = new() { Text = "Uninstall", AutoSize = true };
    private readonly Label status = new() { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft };
    private readonly InstallerEngine engine;

    public MainForm()
    {
        Text = "RainbowBarrels Installer — 0.1.0-rc.1";
        MinimumSize = new Size(710, 285);
        Size = new Size(790, 310);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 10);
        engine = new InstallerEngine(AppContext.BaseDirectory);
        var heading = new Label
        {
            Text = "RainbowBarrels", Font = new Font(Font.FontFamily, 22, FontStyle.Bold), AutoSize = true
        };
        var description = new Label
        {
            Text = "Release candidate for Steam build 24735202 / Darktide 1.3.770.210. " +
                   "Requires DML and DMF. Darktide must be closed. " +
                   "Install reconstructs two game bundles from verified stock files and installs " +
                   "1,098 custom material streams with exact backups and rollback.",
            AutoSize = true, MaximumSize = new Size(725, 0)
        };
        var picker = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 2 };
        picker.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        picker.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        picker.Controls.Add(folder, 0, 0);
        picker.Controls.Add(browse, 1, 0);
        var actions = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true };
        actions.Controls.AddRange([install, repair, uninstall]);
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(24), RowCount = 5 };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.Controls.Add(heading);
        layout.Controls.Add(description);
        layout.Controls.Add(picker);
        layout.Controls.Add(actions);
        layout.Controls.Add(status);
        Controls.Add(layout);
        browse.Click += (_, _) => PickFolder();
        install.Click += async (_, _) => await Run(ActionKind.Install);
        repair.Click += async (_, _) => await Run(ActionKind.Repair);
        uninstall.Click += async (_, _) => await Run(ActionKind.Uninstall);
        folder.Text = GameDiscovery.FindRoots().FirstOrDefault() ?? "";
        status.Text = folder.Text.Length == 0 ? "Select the Warhammer 40,000 DARKTIDE folder." :
            "Ready. No game files are changed before an action is selected.";
    }

    private void PickFolder()
    {
        using var picker = new FolderBrowserDialog { Description = "Select the Darktide game folder" };
        if (picker.ShowDialog(this) == DialogResult.OK) folder.Text = picker.SelectedPath;
    }

    private async Task Run(ActionKind action)
    {
        Busy(true);
        status.Text = $"{action} in progress. Verifying all inputs and outputs...";
        try
        {
            var result = await Task.Run(() => engine.Execute(folder.Text, action));
            status.Text = result;
            MessageBox.Show(this, result, "RainbowBarrels", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception exception)
        {
            status.Text = exception.Message;
            MessageBox.Show(this, exception.Message, "RainbowBarrels stopped safely",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { Busy(false); }
    }

    private void Busy(bool busy)
    {
        folder.Enabled = browse.Enabled = install.Enabled = repair.Enabled = uninstall.Enabled = !busy;
        UseWaitCursor = busy;
    }
}
