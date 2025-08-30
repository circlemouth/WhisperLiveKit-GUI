using Avalonia.Headless.XUnit;
using Xunit;

namespace avalonia_ui.Tests;

public class LicenseWindowTests
{
    [AvaloniaFact]
    public void LicenseWindow_Should_Instantiate()
    {
        var window = new LicenseWindow();
        Assert.NotNull(window);
    }
}
