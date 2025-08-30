using System.Globalization;
using System.Threading.Tasks;
using Avalonia.Controls;

namespace avalonia_ui;

public partial class VadSettingsWindow : Window
{
    public VadSettingsWindow()
    {
        InitializeComponent();
    }

    public VadSettingsWindow(double vacChunk)
    {
        InitializeComponent();
        VacChunk.Text = vacChunk.ToString(CultureInfo.InvariantCulture);
    }

    private async void OnOk(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        double.TryParse(VacChunk.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var vac);
        Close((true, vac));
        await Task.CompletedTask;
    }
}
