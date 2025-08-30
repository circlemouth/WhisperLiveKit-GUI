using System;
using System.Diagnostics;
using System.Threading.Tasks;
using Avalonia.Controls;

namespace avalonia_ui;

public partial class HfLoginWindow : Window
{
    public HfLoginWindow()
    {
        InitializeComponent();
    }

    private async void OnLoginClick(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        var token = TokenBox.Text ?? string.Empty;
        if (string.IsNullOrWhiteSpace(token)) { Close(false); return; }
        var ok = await ValidateAndSave(token);
        Close(ok);
    }

    private async Task<bool> ValidateAndSave(string token)
    {
        var cacheDir = new MainWindow().GetPythonUserCacheDir();
        var psi = new ProcessStartInfo
        {
            FileName = "python",
            UseShellExecute = false
        };
        psi.Environment["HF_HOME"] = System.IO.Path.Combine(cacheDir, "hf-cache");
        psi.Environment["HUGGINGFACE_HUB_CACHE"] = System.IO.Path.Combine(cacheDir, "hf-cache");
        psi.ArgumentList.Add("-c");
        var code = "from huggingface_hub import HfApi,HfFolder; import sys; t=sys.argv[1]; HfApi().whoami(token=t); HfFolder.save_token(t)";
        psi.ArgumentList.Add(code);
        psi.ArgumentList.Add(token);
        try
        {
            using var p = Process.Start(psi);
            if (p == null) return false;
            await p.WaitForExitAsync();
            return p.ExitCode == 0;
        }
        catch { return false; }
    }
}

