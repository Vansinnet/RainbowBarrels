using System.Runtime.CompilerServices;

[assembly: InternalsVisibleTo("RainbowBarrels.Installer.Tests")]

namespace RainbowBarrels.Installer;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}
