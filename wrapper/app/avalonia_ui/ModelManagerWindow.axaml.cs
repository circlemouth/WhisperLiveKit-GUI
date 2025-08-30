using System;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Input;
using Avalonia.Controls;

namespace avalonia_ui;

public class ModelItem
{
    public string Name { get; set; } = "";
    public string Usage { get; set; } = "";
    public string Status { get; set; } = "";
    public string ActionText { get; set; } = "";
    public ICommand ActionCommand { get; set; } = default!;
}

public class DelegateCommand : ICommand
{
    private readonly Func<object?, Task> _execAsync;
    public event EventHandler? CanExecuteChanged;
    public DelegateCommand(Func<object?, Task> execAsync) { _execAsync = execAsync; }
    public bool CanExecute(object? parameter) => true;
    public async void Execute(object? parameter) { await _execAsync(parameter); }
}

public partial class ModelManagerWindow : Window
{
    public ObservableCollection<ModelItem> Items { get; } = new();
    private readonly string _cacheDir;
    private readonly Avalonia.Controls.DataGrid _grid;

    public ModelManagerWindow()
    {
        InitializeComponent();
        _cacheDir = new MainWindow().GetPythonUserCacheDir();
        _grid = this.FindControl<Avalonia.Controls.DataGrid>("ModelsGrid");
        _grid.ItemsSource = Items;
        _ = LoadAsync();
    }

    private async Task LoadAsync()
    {
        var list = await MainWindow.LoadWhisperModels();
        var models = new System.Collections.Generic.List<(string name, string usage)>();
        foreach (var m in list) models.Add((m, "Whisper"));
        models.Add(("pyannote/segmentation-3.0", "Segmentation"));
        models.Add(("pyannote/segmentation", "Segmentation"));
        models.Add(("pyannote/embedding", "Embedding"));
        models.Add(("speechbrain/spkrec-ecapa-voxceleb", "Embedding"));
        models.Add(("snakers4/silero-vad", "VAD"));

        Items.Clear();
        foreach (var entry in models)
        {
            var name = entry.name;
            var usage = entry.usage;
            var downloaded = await IsDownloaded(name);
            var item = new ModelItem
            {
                Name = name,
                Usage = usage,
                Status = downloaded ? "downloaded" : "missing"
            };
            item.ActionText = downloaded ? "Delete" : "Download";
            item.ActionCommand = new DelegateCommand(async _ =>
            {
                if (item.ActionText == "Delete")
                {
                    await Delete(name);
                    item.Status = "missing";
                    item.ActionText = "Download";
                }
                else
                {
                    await Download(name);
                    item.Status = "downloaded";
                    item.ActionText = "Delete";
                }
                _grid.ItemsSource = null; _grid.ItemsSource = Items;
            });
            Items.Add(item);
        }
    }

    private async Task<bool> IsDownloaded(string name)
    {
        var psi = MakeCliPsi("is_downloaded", name);
        try
        {
            using var p = Process.Start(psi);
            if (p == null) return false;
            var s = await p.StandardOutput.ReadToEndAsync();
            p.WaitForExit();
            return s.Trim() == "1";
        }
        catch { return false; }
    }

    private async Task Download(string name)
    {
        var psi = MakeCliPsi("download", name);
        try { using var p = Process.Start(psi); if (p != null) await p.WaitForExitAsync(); } catch { }
    }

    private async Task Delete(string name)
    {
        var psi = MakeCliPsi("delete", name);
        try { using var p = Process.Start(psi); if (p != null) await p.WaitForExitAsync(); } catch { }
    }

    private ProcessStartInfo MakeCliPsi(string cmd, string name)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "python",
            UseShellExecute = false,
            RedirectStandardOutput = true
        };
        psi.ArgumentList.Add("-m");
        psi.ArgumentList.Add("wrapper.cli.model_manager_cli");
        psi.ArgumentList.Add(cmd);
        if (!string.IsNullOrWhiteSpace(name)) psi.ArgumentList.Add(name);
        psi.Environment["WRAPPER_CACHE_DIR"] = _cacheDir;
        return psi;
    }
}
