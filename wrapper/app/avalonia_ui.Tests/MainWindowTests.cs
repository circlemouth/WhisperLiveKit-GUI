using Avalonia;
using Avalonia.Headless;
using Xunit;

namespace avalonia_ui.Tests;

public class MainWindowTests
{
    [Fact]
    public void MainWindow_Should_Instantiate()
    {
        var app = AppBuilder.Configure<App>()
            .UseHeadless(new AvaloniaHeadlessPlatformOptions())
            .SetupWithoutStarting();
        var window = new MainWindow();
        Assert.NotNull(window);
    }
}
