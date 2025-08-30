using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Avalonia.Controls;

namespace avalonia_ui;

public partial class LicenseWindow : Window
{
    private readonly List<LicenseInfo> _licenses = new();

    public LicenseWindow()
    {
        InitializeComponent();
        LoadLicenses();
    }

    private void LoadLicenses()
    {
        try
        {
            var path = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "licenses.json"));
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            foreach (var elem in doc.RootElement.EnumerateArray())
            {
                var name = elem.GetProperty("name").GetString() ?? string.Empty;
                var version = elem.GetProperty("version").GetString() ?? string.Empty;
                var lic = elem.GetProperty("license").GetString() ?? string.Empty;
                var text = elem.GetProperty("license_text").GetString() ?? string.Empty;
                _licenses.Add(new LicenseInfo(name, version, lic, text));
            }
            PackageCombo.ItemsSource = _licenses;
            if (_licenses.Count > 0)
                PackageCombo.SelectedIndex = 0;
        }
        catch
        {
            // ignore
        }
    }

    private void OnSelect(object? sender, SelectionChangedEventArgs e)
    {
        if (PackageCombo.SelectedItem is LicenseInfo info)
            LicenseText.Text = info.LicenseText;
    }

    private record LicenseInfo(string Name, string Version, string License, string LicenseText)
    {
        public override string ToString() => $"{Name} {Version} ({License})";
    }
}
