using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text.Json;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using System.Threading;

namespace avalonia_ui;

public partial class MainWindow : Window
{
    private Process? _backendProcess;
    private Process? _apiProcess;
    private string _prevBackendHost = "127.0.0.1";
    private string _prevApiHost = "127.0.0.1";
    private bool _recording = false;
    private System.Threading.CancellationTokenSource? _recordCts;
    private DateTime _recordStart;
    // Advanced settings (parity with Tkinter GUI)
    private string _warmupFile = string.Empty;
    private bool _confidenceValidation = false;
    private bool _punctuationSplit = false;
    private double _minChunkSize = 0.5;
    private string _language = "auto";
    private string _task = "transcribe";
    private string _backend = "simulstreaming";
    private double _vacChunkSize = 0.04;
    private string _bufferTrimming = "segment";
    private double _bufferTrimmingSec = 15.0;
    private string _logLevel = "DEBUG";
    private string _sslCertFile = string.Empty;
    private string _sslKeyFile = string.Empty;
    private int _frameThreshold = 25;
    private string _diarizationBackend = "sortformer";
    private string _segmentationModel = "pyannote/segmentation-3.0";
    private string _embeddingModel = "pyannote/embedding";
    private string _vadCertFile = string.Empty; // env SSL_CERT_FILE override
    private bool _hfLoggedIn = false;

    public MainWindow()
    {
        InitializeComponent();
        Opened += OnOpened;
        Closing += async (_, __) => await SaveSettings();
        AllowExternal.IsCheckedChanged += (_, __) => ToggleAllowExternal(AllowExternal.IsChecked == true);
        BackendHost.TextChanged += (_, __) => UpdateEndpoints();
        BackendPort.TextChanged += (_, __) => UpdateEndpoints();
        ApiHost.TextChanged += (_, __) => UpdateEndpoints();
        ApiPort.TextChanged += (_, __) => UpdateEndpoints();
        _ = LoadSettings();
    }

    private async void OnOpened(object? sender, EventArgs e)
    {
        UpdateEndpoints();
        if (AutoStart.IsChecked == true)
            await StartServer();
    }

    private async Task LoadSettings()
    {
        var file = await GetConfigFilePath();
        try
        {
            if (File.Exists(file))
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(file));
                var root = doc.RootElement;
                BackendHost.Text = root.GetString("backend_host", "127.0.0.1");
                BackendPort.Text = root.GetInt("backend_port", FindFreePort()).ToString();
                ApiHost.Text = root.GetString("api_host", "127.0.0.1");
                ApiPort.Text = root.GetInt("api_port", FindFreePort(int.Parse(BackendPort.Text))).ToString();
                AutoStart.IsChecked = root.GetBool("auto_start", true);
                AllowExternal.IsChecked = root.GetBool("allow_external", false);
                UseVac.IsChecked = root.GetBool("use_vac", false);
                Diarization.IsChecked = root.GetBool("diarization", false);
                var models = await LoadWhisperModels();
                ModelCombo.ItemsSource = models;
                var model = root.GetString("model", models.Count > 0 ? models[0] : "");
                ModelCombo.SelectedItem = model;
                // Advanced
                _warmupFile = root.GetString("warmup_file", _warmupFile);
                _confidenceValidation = root.GetBool("confidence_validation", _confidenceValidation);
                _punctuationSplit = root.GetBool("punctuation_split", _punctuationSplit);
                _minChunkSize = root.GetDouble("min_chunk_size", _minChunkSize);
                _language = root.GetString("language", _language);
                _task = root.GetString("task", _task);
                _backend = root.GetString("backend", _backend);
                _vacChunkSize = root.GetDouble("vac_chunk_size", _vacChunkSize);
                _bufferTrimming = root.GetString("buffer_trimming", _bufferTrimming);
                _bufferTrimmingSec = root.GetDouble("buffer_trimming_sec", _bufferTrimmingSec);
                _logLevel = root.GetString("log_level", _logLevel);
                _sslCertFile = root.GetString("ssl_certfile", _sslCertFile);
                _sslKeyFile = root.GetString("ssl_keyfile", _sslKeyFile);
                _frameThreshold = root.GetInt("frame_threshold", _frameThreshold);
                _diarizationBackend = root.GetString("diarization_backend", _diarizationBackend);
                _segmentationModel = root.GetString("segmentation_model", _segmentationModel);
                _embeddingModel = root.GetString("embedding_model", _embeddingModel);
                _vadCertFile = root.GetString("vad_certfile", _vadCertFile);
            }
            else
            {
                BackendHost.Text = "127.0.0.1";
                BackendPort.Text = FindFreePort().ToString();
                ApiHost.Text = "127.0.0.1";
                ApiPort.Text = FindFreePort(int.Parse(BackendPort.Text)).ToString();
                var models = await LoadWhisperModels();
                ModelCombo.ItemsSource = models;
                ModelCombo.SelectedIndex = 0;
                AutoStart.IsChecked = true;
            }
        }
        catch
        {
            // ignore malformed config
        }
        await CheckHfLoginState();
    }

    private async Task SaveSettings()
    {
        var file = await GetConfigFilePath();
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(file)!);
            var obj = new Dictionary<string, object?>
            {
                ["backend_host"] = BackendHost.Text,
                ["backend_port"] = int.TryParse(BackendPort.Text, out var bp) ? bp : 0,
                ["api_host"] = ApiHost.Text,
                ["api_port"] = int.TryParse(ApiPort.Text, out var ap) ? ap : 0,
                ["auto_start"] = AutoStart.IsChecked == true,
                ["allow_external"] = AllowExternal.IsChecked == true,
                ["model"] = ModelCombo.SelectedItem?.ToString() ?? "",
                ["use_vac"] = UseVac.IsChecked == true,
                ["diarization"] = Diarization.IsChecked == true,
                // Advanced
                ["warmup_file"] = _warmupFile,
                ["confidence_validation"] = _confidenceValidation,
                ["punctuation_split"] = _punctuationSplit,
                ["min_chunk_size"] = _minChunkSize,
                ["language"] = _language,
                ["task"] = _task,
                ["backend"] = _backend,
                ["vac_chunk_size"] = _vacChunkSize,
                ["buffer_trimming"] = _bufferTrimming,
                ["buffer_trimming_sec"] = _bufferTrimmingSec,
                ["log_level"] = _logLevel,
                ["ssl_certfile"] = _sslCertFile,
                ["ssl_keyfile"] = _sslKeyFile,
                ["frame_threshold"] = _frameThreshold,
                ["diarization_backend"] = _diarizationBackend,
                ["segmentation_model"] = _segmentationModel,
                ["embedding_model"] = _embeddingModel,
                ["vad_certfile"] = _vadCertFile
            };
            File.WriteAllText(file, JsonSerializer.Serialize(obj, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch
        {
            // ignore
        }
    }

    private void ToggleAllowExternal(bool enabled)
    {
        if (enabled)
        {
            _prevBackendHost = BackendHost.Text ?? "127.0.0.1";
            _prevApiHost = ApiHost.Text ?? "127.0.0.1";
            BackendHost.Text = "0.0.0.0";
            ApiHost.Text = "0.0.0.0";
        }
        else
        {
            BackendHost.Text = _prevBackendHost;
            ApiHost.Text = _prevApiHost;
        }
        UpdateEndpoints();
    }

    private void UpdateEndpoints()
    {
        var bHost = BackendHost.Text ?? "127.0.0.1";
        var bPort = BackendPort.Text ?? "";
        var aHost = ApiHost.Text ?? "127.0.0.1";
        var aPort = ApiPort.Text ?? "";
        var dispB = DisplayHost(bHost);
        var dispA = DisplayHost(aHost);
        WebEndpoint.Text = $"http://{dispB}:{bPort}";
        WsEndpoint.Text = $"ws://{dispB}:{bPort}/asr";
        ApiEndpoint.Text = $"http://{dispA}:{aPort}/v1/audio/transcriptions";
        OpenWebButton.IsEnabled = true;
    }

    private static string DisplayHost(string host)
    {
        if (host == "0.0.0.0")
        {
            try
            {
                foreach (var ni in System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (ni.OperationalStatus != System.Net.NetworkInformation.OperationalStatus.Up) continue;
                    var ipProps = ni.GetIPProperties();
                    foreach (var ua in ipProps.UnicastAddresses)
                    {
                        if (ua.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork && !System.Net.IPAddress.IsLoopback(ua.Address))
                        {
                            return ua.Address.ToString();
                        }
                    }
                }
            }
            catch { }
            return "127.0.0.1";
        }
        return host;
    }

    private Task StartServer()
    {
        if ((_backendProcess != null && !_backendProcess.HasExited) || (_apiProcess != null && !_apiProcess.HasExited))
            return Task.CompletedTask;

        StartButton.IsEnabled = false;
        StopButton.IsEnabled = true;
        // Common env (cache dirs)
        var env = GetBaseEnvWithCaches();

        // Launch backend
        var backend = new ProcessStartInfo
        {
            FileName = "python",
            UseShellExecute = false
        };
        backend.ArgumentList.Add("-m");
        backend.ArgumentList.Add("whisperlivekit.basic_server");
        backend.ArgumentList.Add("--host");
        backend.ArgumentList.Add(BackendHost.Text ?? "127.0.0.1");
        backend.ArgumentList.Add("--port");
        backend.ArgumentList.Add(BackendPort.Text ?? "0");

        // Model directory if available
        var model = ModelCombo.SelectedItem?.ToString();
        if (!string.IsNullOrWhiteSpace(model))
        {
            var path = ResolveModelPath(model!);
            if (!string.IsNullOrWhiteSpace(path))
            {
                backend.ArgumentList.Add("--model_dir");
                backend.ArgumentList.Add(path!);
            }
        }

        if (Diarization.IsChecked == true)
        {
            backend.ArgumentList.Add("--diarization");
            // detailed options handled in settings dialogs
        }

        if (false && UseVac.IsChecked != true)
        {
            backend.ArgumentList.Add("--no-vac");
        }

        if (!string.IsNullOrWhiteSpace(_vadCertFile)) env["SSL_CERT_FILE"] = _vadCertFile;
        // Append detailed backend options (migrated from Tkinter)
        if (UseVac.IsChecked == true)
        {
            backend.ArgumentList.Add("--vac-chunk-size");
            backend.ArgumentList.Add(_vacChunkSize.ToString(System.Globalization.CultureInfo.InvariantCulture));
        }
        else
        {
            backend.ArgumentList.Add("--no-vac");
        }
        if (!string.IsNullOrWhiteSpace(_warmupFile)) { backend.ArgumentList.Add("--warmup-file"); backend.ArgumentList.Add(_warmupFile); }
        if (_confidenceValidation) backend.ArgumentList.Add("--confidence-validation");
        if (_punctuationSplit) backend.ArgumentList.Add("--punctuation-split");
        backend.ArgumentList.Add("--min-chunk-size"); backend.ArgumentList.Add(_minChunkSize.ToString(System.Globalization.CultureInfo.InvariantCulture));
        backend.ArgumentList.Add("--language"); backend.ArgumentList.Add(_language);
        backend.ArgumentList.Add("--task"); backend.ArgumentList.Add(_task);
        backend.ArgumentList.Add("--backend"); backend.ArgumentList.Add(_backend);
        backend.ArgumentList.Add("--buffer_trimming"); backend.ArgumentList.Add(_bufferTrimming);
        backend.ArgumentList.Add("--buffer_trimming_sec"); backend.ArgumentList.Add(_bufferTrimmingSec.ToString(System.Globalization.CultureInfo.InvariantCulture));
        backend.ArgumentList.Add("--log-level"); backend.ArgumentList.Add(_logLevel);
        if (!string.IsNullOrWhiteSpace(_sslCertFile)) { backend.ArgumentList.Add("--ssl-certfile"); backend.ArgumentList.Add(_sslCertFile); }
        if (!string.IsNullOrWhiteSpace(_sslKeyFile)) { backend.ArgumentList.Add("--ssl-keyfile"); backend.ArgumentList.Add(_sslKeyFile); }
        backend.ArgumentList.Add("--frame-threshold"); backend.ArgumentList.Add(_frameThreshold.ToString());
        if (Diarization.IsChecked == true)
        {
            if (!string.IsNullOrWhiteSpace(_segmentationModel)) { backend.ArgumentList.Add("--segmentation-model"); backend.ArgumentList.Add(_segmentationModel); }
            if (!string.IsNullOrWhiteSpace(_embeddingModel)) { backend.ArgumentList.Add("--embedding-model"); backend.ArgumentList.Add(_embeddingModel); }
            if (!string.IsNullOrWhiteSpace(_diarizationBackend)) { backend.ArgumentList.Add("--diarization-backend"); backend.ArgumentList.Add(_diarizationBackend); }
        }
        ApplyEnv(backend, env);
        _backendProcess = Process.Start(backend);

        // Launch wrapper API (uvicorn)
        var api = new ProcessStartInfo
        {
            FileName = "python",
            UseShellExecute = false
        };
        api.ArgumentList.Add("-m");
        api.ArgumentList.Add("uvicorn");
        api.ArgumentList.Add("wrapper.api.server:app");
        api.ArgumentList.Add("--host");
        api.ArgumentList.Add(ApiHost.Text ?? "127.0.0.1");
        api.ArgumentList.Add("--port");
        api.ArgumentList.Add(ApiPort.Text ?? "0");

        // Bind backend host/port for API via env
        env["WRAPPER_BACKEND_HOST"] = BackendHost.Text ?? "127.0.0.1";
        env["WRAPPER_BACKEND_PORT"] = BackendPort.Text ?? "";
        ApplyEnv(api, env);
        _apiProcess = Process.Start(api);

        UpdateEndpoints();
        return Task.CompletedTask;
    }

    private async void OnStartClick(object? sender, RoutedEventArgs e)
    {
        await StartServer();
    }

    private void OnStopClick(object? sender, RoutedEventArgs e)
    {
        try { if (_apiProcess != null && !_apiProcess.HasExited) { _apiProcess.Kill(); _apiProcess.Dispose(); } } catch { }
        try { if (_backendProcess != null && !_backendProcess.HasExited) { _backendProcess.Kill(); _backendProcess.Dispose(); } } catch { }
        _apiProcess = null;
        _backendProcess = null;
        StartButton.IsEnabled = true;
        StopButton.IsEnabled = false;
    }

    private async Task<string> GetConfigFilePath()
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "python",
                UseShellExecute = false,
                RedirectStandardOutput = true
            };
            psi.ArgumentList.Add("-c");
            psi.ArgumentList.Add("from platformdirs import user_config_path; import sys; sys.stdout.write(str(user_config_path('WhisperLiveKit','wrapper')))");
            using var p = Process.Start(psi);
            if (p == null)
                throw new Exception();
            var output = await p.StandardOutput.ReadToEndAsync();
            p.WaitForExit();
            var dir = output.Trim();
            return Path.Combine(dir, "settings.json");
        }
        catch
        {
            var baseDir = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            return Path.Combine(baseDir, "WhisperLiveKit", "wrapper", "settings.json");
        }
    }

    private static int FindFreePort(int? exclude = null)
    {
        var listener = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        if (exclude.HasValue && port == exclude.Value)
            return FindFreePort(exclude);
        return port;
    }

    public static Task<IList<string>> LoadWhisperModels()
    {
        var list = new List<string>();
        try
        {
            var file = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "available_models.md"));
            if (File.Exists(file))
            {
                bool collecting = false;
                foreach (var line in File.ReadLines(file))
                {
                    var t = line.Trim();
                    if (collecting)
                    {
                        if (string.IsNullOrEmpty(t))
                            break;
                        var parts = t.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                        if (parts.Length > 0)
                            list.Add(parts[0]);
                    }
                    else if (t.StartsWith("## Whisper Models"))
                    {
                        collecting = true;
                    }
                }
            }
        }
        catch
        {
            // ignore
        }
        if (list.Count == 0)
            list.AddRange(new[] { "tiny", "base", "small", "medium", "large-v3" });
        return Task.FromResult<IList<string>>(list);
    }

    private async void OnBrowseSave(object? sender, RoutedEventArgs e)
    {
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions());
        if (file != null)
            SavePath.Text = file.Path.LocalPath;
    }

    private void OnOpenWeb(object? sender, RoutedEventArgs e)
    {
        var url = WebEndpoint.Text;
        if (!string.IsNullOrWhiteSpace(url))
        {
            try { Process.Start(new ProcessStartInfo { FileName = url, UseShellExecute = true }); }
            catch { }
        }
    }

    private void OnCopyWs(object? sender, RoutedEventArgs e)
    {
        var top = TopLevel.GetTopLevel(this);
        top?.Clipboard?.SetTextAsync(WsEndpoint.Text ?? string.Empty);
    }

    private void OnCopyApi(object? sender, RoutedEventArgs e)
    {
        var top = TopLevel.GetTopLevel(this);
        top?.Clipboard?.SetTextAsync(ApiEndpoint.Text ?? string.Empty);
    }

    private void OnManageModels(object? sender, RoutedEventArgs e)
    {
        var w = new ModelManagerWindow();
        w.Show(this);
    }

    private void OnLoginHf(object? sender, RoutedEventArgs e)
    {
        var dlg = new HfLoginWindow();
        dlg.ShowDialog<bool>(this).ContinueWith(async t =>
        {
            var ok = t.Result;
            await Dispatcher.UIThread.InvokeAsync(() => StatusText.Text = ok ? "Hugging Face login succeeded" : "Hugging Face login failed");
            await CheckHfLoginState();
        });
    }

    private async void OnRecordClick(object? sender, RoutedEventArgs e)
    {
        if (_recording)
        {
            _recordCts?.Cancel();
            _recording = false;
            RecordButton.Content = "Start Recording";
            return;
        }

        // Require running backend
        if (_backendProcess == null || _backendProcess.HasExited)
        {
            StatusText.Text = "Start API before recording";
            return;
        }

        _recording = true;
        RecordButton.Content = "Stop Recording";
        TranscriptBox.Text = string.Empty;
        _recordStart = DateTime.UtcNow;
        _recordCts = new System.Threading.CancellationTokenSource();
        _ = RunRecorder(_recordCts.Token);
        await Task.CompletedTask;
    }

    private void OnShowLicense(object? sender, RoutedEventArgs e)
    {
        var path = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "LICENSE"));
        if (File.Exists(path))
        {
            try { Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true }); } catch { }
        }
    }

    private Dictionary<string, string> GetBaseEnvWithCaches()
    {
        var env = new Dictionary<string, string>();
        try
        {
            var dir = GetPythonUserCacheDir();
            var hf = Path.Combine(dir, "hf-cache");
            var th = Path.Combine(dir, "torch-hub");
            Directory.CreateDirectory(hf);
            Directory.CreateDirectory(th);
            env["HUGGINGFACE_HUB_CACHE"] = hf;
            env["HF_HOME"] = hf;
            env["TORCH_HOME"] = th;
        }
        catch { }
        return env;
    }

    private static void ApplyEnv(ProcessStartInfo psi, Dictionary<string, string> env)
    {
        foreach (var kv in env)
        {
            psi.Environment[kv.Key] = kv.Value;
        }
    }

    private async Task CheckHfLoginState()
    {
        _hfLoggedIn = await IsHfLoggedIn();
        await Dispatcher.UIThread.InvokeAsync(() =>
        {
            Diarization.IsEnabled = _hfLoggedIn;
            if (!_hfLoggedIn)
                Diarization.IsChecked = false;
        });
    }

    private async Task<bool> IsHfLoggedIn()
    {
        var cacheDir = GetPythonUserCacheDir();
        var psi = new ProcessStartInfo
        {
            FileName = "python",
            UseShellExecute = false
        };
        psi.ArgumentList.Add("-c");
        psi.ArgumentList.Add("import os,sys;from huggingface_hub import HfApi,HfFolder;" +
            "token=os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACEHUB_API_TOKEN') or os.getenv('HUGGING_FACE_HUB_TOKEN') or HfFolder.get_token();" +
            "api=HfApi();sys.exit(0) if token and api.whoami(token=token) else sys.exit(1)");
        psi.Environment["HF_HOME"] = Path.Combine(cacheDir, "hf-cache");
        psi.Environment["HUGGINGFACE_HUB_CACHE"] = Path.Combine(cacheDir, "hf-cache");
        try
        {
            using var p = Process.Start(psi);
            if (p == null) return false;
            await p.WaitForExitAsync();
            return p.ExitCode == 0;
        }
        catch { return false; }
    }

    public string GetPythonUserCacheDir()
    {
        var psi = new ProcessStartInfo
        {
            FileName = "python",
            UseShellExecute = false,
            RedirectStandardOutput = true
        };
        psi.ArgumentList.Add("-c");
        psi.ArgumentList.Add("from platformdirs import user_cache_path; import sys; sys.stdout.write(str(user_cache_path('WhisperLiveKit','wrapper'))) ");
        try
        {
            using var p = Process.Start(psi);
            if (p == null) return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "WhisperLiveKit", "wrapper");
            var output = p.StandardOutput.ReadToEnd();
            p.WaitForExit();
            return output.Trim();
        }
        catch
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "WhisperLiveKit", "wrapper");
        }
    }

    private string ResolveModelPath(string model)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "python",
            UseShellExecute = false,
            RedirectStandardOutput = true
        };
        psi.ArgumentList.Add("-c");
        var code = "from wrapper.app import model_manager as m; import sys; print(m.get_model_path('" + model.Replace("'", "\'") + "'))";
        psi.ArgumentList.Add(code);
        try
        {
            using var p = Process.Start(psi);
            if (p == null) return string.Empty;
            var output = p.StandardOutput.ReadToEnd();
            p.WaitForExit();
            return output.Trim();
        }
        catch
        {
            return string.Empty;
        }
    }

    private async Task RunRecorder(System.Threading.CancellationToken ct)
    {
        // NAudio capture 16k mono 16-bit PCM
        using var ws = new System.Net.WebSockets.ClientWebSocket();
        var uri = new Uri(WsEndpoint.Text ?? "");
        try
        {
            await ws.ConnectAsync(uri, ct);
        }
        catch
        {
            await Dispatcher.UIThread.InvokeAsync(() => { StatusText.Text = "WebSocket connect failed"; });
            _recording = false;
            await Dispatcher.UIThread.InvokeAsync(() => RecordButton.Content = "Start Recording");
            return;
        }

        var waveIn = new NAudio.Wave.WaveInEvent
        {
            WaveFormat = new NAudio.Wave.WaveFormat(16000, 16, 1),
            BufferMilliseconds = 100
        };

        waveIn.DataAvailable += async (s, a) =>
        {
            // RMS level
            double rms = 0;
            int samples = a.BytesRecorded / 2;
            for (int i = 0; i < a.BytesRecorded; i += 2)
            {
                short val = BitConverter.ToInt16(a.Buffer, i);
                double f = val / 32768.0;
                rms += f * f;
            }
            rms = samples > 0 ? Math.Sqrt(rms / samples) : 0;
            await Dispatcher.UIThread.InvokeAsync(() =>
            {
                RecordLevel.Value = Math.Min(1.0, rms);
                var elapsed = DateTime.UtcNow - _recordStart;
                TimerText.Text = elapsed.ToString("hh':'mm':'ss");
            });

            if (ws.State == System.Net.WebSockets.WebSocketState.Open)
            {
                try
                {
                    await ws.SendAsync(new ArraySegment<byte>(a.Buffer, 0, a.BytesRecorded), System.Net.WebSockets.WebSocketMessageType.Binary, true, ct);
                }
                catch { }
            }
        };

        // Receiver
        var recvTask = Task.Run(async () =>
        {
            var buf = new byte[8192];
            using var ms = new MemoryStream();
            while (!ct.IsCancellationRequested && ws.State == System.Net.WebSockets.WebSocketState.Open)
            {
                ms.SetLength(0);
                System.Net.WebSockets.WebSocketReceiveResult? res;
                do
                {
                    res = await ws.ReceiveAsync(buf, ct);
                    if (res.Count > 0)
                        ms.Write(buf, 0, res.Count);
                } while (!res.EndOfMessage);

                if (res.MessageType == System.Net.WebSockets.WebSocketMessageType.Close) break;
                var text = System.Text.Encoding.UTF8.GetString(ms.ToArray());
                try
                {
                    using var doc = JsonDocument.Parse(text);
                    var root = doc.RootElement;
                    if (root.TryGetProperty("type", out var ty) && ty.GetString() == "ready_to_stop")
                        break;
                    if (root.TryGetProperty("lines", out var lines) && lines.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var l in lines.EnumerateArray())
                        {
                            var t = l.TryGetProperty("text", out var tt) ? tt.GetString() : null;
                            if (!string.IsNullOrWhiteSpace(t))
                            {
                                await Dispatcher.UIThread.InvokeAsync(() =>
                                {
                                    TranscriptBox.Text += t + "\n";
                                });
                            }
                        }
                    }
                    if (root.TryGetProperty("buffer_transcription", out var bt) && bt.ValueKind == JsonValueKind.String)
                    {
                        var t = bt.GetString();
                        if (!string.IsNullOrWhiteSpace(t))
                        {
                            await Dispatcher.UIThread.InvokeAsync(() => { TranscriptBox.Text += t + "\n"; });
                        }
                    }
                    if (root.TryGetProperty("buffer_diarization", out var bd) && bd.ValueKind == JsonValueKind.String)
                    {
                        var t = bd.GetString();
                        if (!string.IsNullOrWhiteSpace(t))
                        {
                            await Dispatcher.UIThread.InvokeAsync(() => { TranscriptBox.Text += t + "\n"; });
                        }
                    }
                }
                catch { }
            }
        }, ct);

        try
        {
            waveIn.StartRecording();
            StatusText.Text = "recording";
            while (!ct.IsCancellationRequested)
            {
                await Task.Delay(100, ct);
            }
        }
        catch { }
        finally
        {
            try { waveIn.StopRecording(); waveIn.Dispose(); } catch { }
            try { await ws.SendAsync(new ArraySegment<byte>(Array.Empty<byte>()), System.Net.WebSockets.WebSocketMessageType.Binary, true, CancellationToken.None); } catch { }
            try { await recvTask; } catch { }
            try { await ws.CloseAsync(System.Net.WebSockets.WebSocketCloseStatus.NormalClosure, "done", CancellationToken.None); } catch { }

            await Dispatcher.UIThread.InvokeAsync(() =>
            {
                StatusText.Text = "stopped";
                RecordLevel.Value = 0;
                RecordButton.Content = "Start Recording";
                _recording = false;
                // optional save
                if (SaveEnabled.IsChecked == true)
                {
                    var path = SavePath.Text;
                    if (!string.IsNullOrWhiteSpace(path))
                    {
                        try { File.WriteAllText(path!, TranscriptBox.Text ?? string.Empty); StatusText.Text = $"saved: {path}"; }
                        catch { StatusText.Text = "save failed"; }
                    }
                }
            });
        }
    }

    private void OnAdvancedSettings(object? sender, RoutedEventArgs e)
    {
        // TODO: implement full dialog parity; placeholder for now
        var dlg = new AdvancedSettingsWindow(_warmupFile, _confidenceValidation, _punctuationSplit, _minChunkSize, _language, _task, _backend, _bufferTrimming, _bufferTrimmingSec, _logLevel, _sslCertFile, _sslKeyFile, _frameThreshold, _vadCertFile);
        dlg.ShowDialog<(bool ok, avalonia_ui.AdvancedSettingsWindow.Data data)>(this).ContinueWith(t => { if (t.IsCompletedSuccessfully && t.Result.ok) { var d = t.Result.data; _warmupFile=d.WarmupFile; _confidenceValidation=d.ConfidenceValidation; _punctuationSplit=d.PunctuationSplit; _minChunkSize=d.MinChunkSize; _language=d.Language; _task=d.Task; _backend=d.Backend; _bufferTrimming=d.BufferTrimming; _bufferTrimmingSec=d.BufferTrimmingSec; _logLevel=d.LogLevel; _sslCertFile=d.SslCertFile; _sslKeyFile=d.SslKeyFile; _frameThreshold=d.FrameThreshold; _vadCertFile=d.VadCertFile; } });
    }

    private void OnVadSettings(object? sender, RoutedEventArgs e)
    {
        var dlg = new VadSettingsWindow(_vacChunkSize);
        dlg.ShowDialog<(bool ok, double vac)>(this).ContinueWith(t => { if (t.IsCompletedSuccessfully && t.Result.ok) { _vacChunkSize = t.Result.vac; } });
    }

    private void OnDiarSettings(object? sender, RoutedEventArgs e)
    {
        var dlg = new DiarizationSettingsWindow(_diarizationBackend, _segmentationModel, _embeddingModel);
        dlg.ShowDialog<(bool ok, string backend, string seg, string emb)>(this).ContinueWith(t => { if (t.IsCompletedSuccessfully && t.Result.ok) { _diarizationBackend=t.Result.backend; _segmentationModel=t.Result.seg; _embeddingModel=t.Result.emb; } });
    }
}

static class JsonExtensions
{
    public static string GetString(this JsonElement elem, string name, string defaultValue)
        => elem.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? defaultValue : defaultValue;

    public static int GetInt(this JsonElement elem, string name, int defaultValue)
        => elem.TryGetProperty(name, out var v) && v.TryGetInt32(out var i) ? i : defaultValue;

    public static bool GetBool(this JsonElement elem, string name, bool defaultValue)
        => elem.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.True ? true : (v.ValueKind == JsonValueKind.False ? false : defaultValue);

    public static double GetDouble(this JsonElement elem, string name, double defaultValue)
        => elem.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out var d) ? d : defaultValue;
}

