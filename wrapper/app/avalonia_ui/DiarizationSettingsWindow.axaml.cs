using System.Linq;
using System.Threading.Tasks;
using Avalonia.Controls;

namespace avalonia_ui;

public partial class DiarizationSettingsWindow : Window
{
    public DiarizationSettingsWindow()
    {
        InitializeComponent();
        Backend.SelectedIndex = 0;
    }

    public DiarizationSettingsWindow(string backend, string segmentation, string embedding)
    {
        InitializeComponent();
        var items = (Backend.Items as System.Collections.IEnumerable)!;
        int idx = 0, i = 0;
        foreach (var it in items) { if ((it as ComboBoxItem)!.Content?.ToString() == backend) { idx = i; break; } i++; }
        Backend.SelectedIndex = idx;
        Segmentation.Text = segmentation;
        Embedding.Text = embedding;
    }

    private async void OnOk(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        var backend = (Backend.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "sortformer";
        Close((true, backend, Segmentation.Text ?? string.Empty, Embedding.Text ?? string.Empty));
        await Task.CompletedTask;
    }
}
