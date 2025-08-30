using System;
using System.Globalization;
using System.Threading.Tasks;
using Avalonia.Controls;
using Avalonia.Platform.Storage;

namespace avalonia_ui;

public partial class AdvancedSettingsWindow : Window
{
    public AdvancedSettingsWindow()
    {
        InitializeComponent();
    }
    public record Data(
        string WarmupFile,
        bool ConfidenceValidation,
        bool PunctuationSplit,
        double MinChunkSize,
        string Language,
        string Task,
        string Backend,
        string BufferTrimming,
        double BufferTrimmingSec,
        string LogLevel,
        string SslCertFile,
        string SslKeyFile,
        int FrameThreshold,
        string VadCertFile
    );

    public AdvancedSettingsWindow(
        string warmupFile, bool confidenceValidation, bool punctuationSplit,
        double minChunkSize, string language, string task, string backend,
        string bufferTrimming, double bufferTrimmingSec, string logLevel,
        string sslCertFile, string sslKeyFile, int frameThreshold, string vadCertFile)
    {
        InitializeComponent();
        WarmupFile.Text = warmupFile;
        ConfidenceValidation.IsChecked = confidenceValidation;
        PunctuationSplit.IsChecked = punctuationSplit;
        MinChunkSize.Text = minChunkSize.ToString(CultureInfo.InvariantCulture);
        Language.Text = language;
        TaskBox.Text = task;
        Backend.Text = backend;
        BufferTrimming.Text = bufferTrimming;
        BufferTrimmingSec.Text = bufferTrimmingSec.ToString(CultureInfo.InvariantCulture);
        LogLevel.Text = logLevel;
        SslCertFile.Text = sslCertFile;
        SslKeyFile.Text = sslKeyFile;
        FrameThreshold.Text = frameThreshold.ToString();
        VadCertFile.Text = vadCertFile;
    }

    private async void OnOk(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        double.TryParse(MinChunkSize.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var minChunk);
        double.TryParse(BufferTrimmingSec.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var bufSec);
        int.TryParse(FrameThreshold.Text, out var frame);
        var data = new Data(
            WarmupFile.Text ?? string.Empty,
            ConfidenceValidation.IsChecked == true,
            PunctuationSplit.IsChecked == true,
            minChunk,
            Language.Text ?? string.Empty,
            TaskBox.Text ?? string.Empty,
            Backend.Text ?? string.Empty,
            BufferTrimming.Text ?? string.Empty,
            bufSec,
            LogLevel.Text ?? string.Empty,
            SslCertFile.Text ?? string.Empty,
            SslKeyFile.Text ?? string.Empty,
            frame,
            VadCertFile.Text ?? string.Empty
        );
        Close((true, data));
        await Task.CompletedTask;
    }

    private async void OnBrowseWarmup(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions());
        if (files.Count > 0) WarmupFile.Text = files[0].Path.LocalPath;
    }
    private async void OnBrowseCert(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions());
        if (files.Count > 0) SslCertFile.Text = files[0].Path.LocalPath;
    }
    private async void OnBrowseKey(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions());
        if (files.Count > 0) SslKeyFile.Text = files[0].Path.LocalPath;
    }
    private async void OnBrowseVadCert(object? sender, Avalonia.Interactivity.RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions());
        if (files.Count > 0) VadCertFile.Text = files[0].Path.LocalPath;
    }
}

