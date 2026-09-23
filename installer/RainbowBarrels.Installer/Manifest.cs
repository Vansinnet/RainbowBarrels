using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RainbowBarrels.Installer;

internal sealed class Manifest
{
    public int Format { get; set; }
    public string Product { get; set; } = "";
    public string Version { get; set; } = "";
    public string SteamAppId { get; set; } = "";
    public string SteamBuild { get; set; } = "";
    public string ExeVersion { get; set; } = "";
    public string OodleSha256 { get; set; } = "";
    public List<BundleRecipe> Bundles { get; set; } = [];
    public List<FileRecipe> Streams { get; set; } = [];
    public List<FileRecipe> ModFiles { get; set; } = [];
}

internal sealed class BundleRecipe
{
    public string Id { get; set; } = "";
    public string Target { get; set; } = "";
    public long StockSize { get; set; }
    public string StockSha256 { get; set; } = "";
    public int StockCount { get; set; }
    public string StockIndexSha256 { get; set; } = "";
    public string StockLogicalSha256 { get; set; } = "";
    public long OutputSize { get; set; }
    public string OutputSha256 { get; set; } = "";
    public int AppendedCount { get; set; }
    public int AppendedIndexSize { get; set; }
    public string Payload { get; set; } = "";
    public long PayloadSize { get; set; }
    public string PayloadSha256 { get; set; } = "";
}

internal sealed class FileRecipe
{
    public string Target { get; set; } = "";
    public string Payload { get; set; } = "";
    public long Size { get; set; }
    public string Sha256 { get; set; } = "";
}

internal sealed class Receipt
{
    public string Product { get; set; } = "RainbowBarrels";
    public string Version { get; set; } = "";
    public string GameRoot { get; set; } = "";
    public string Session { get; set; } = "";
    public List<OwnedFile> Files { get; set; } = [];
}

internal sealed class OwnedFile
{
    public string Target { get; set; } = "";
    public string Sha256 { get; set; } = "";
    public long Size { get; set; }
    public bool Replacement { get; set; }
    public string? StockSha256 { get; set; }
    public long StockSize { get; set; }
}

internal sealed class Journal
{
    public string GameRoot { get; set; } = "";
    public string Action { get; set; } = "";
    public string State { get; set; } = "prepared";
    public string Session { get; set; } = "";
    public string? ReceiptBeforeSha256 { get; set; }
    public List<JournalFile> Files { get; set; } = [];
}

internal sealed class JournalFile
{
    public string Target { get; set; } = "";
    public string Before { get; set; } = "absent";
    public string After { get; set; } = "absent";
    public string? Backup { get; set; }
}

internal static class Safe
{
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) }
    };

    public static string Hash(byte[] data) => Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();

    public static string Hash(string file)
    {
        using var source = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read);
        return Convert.ToHexString(SHA256.HashData(source)).ToLowerInvariant();
    }

    public static void Require(string file, long size, string hash, string label)
    {
        if (!File.Exists(file) || File.GetAttributes(file).HasFlag(FileAttributes.ReparsePoint) ||
            new FileInfo(file).Length != size || !Hash(file).Equals(hash, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"{label} is missing or has unexpected bytes: {file}");
    }

    public static string PathUnder(string root, string relative)
    {
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative) || relative.Contains(':') ||
            relative.Contains('\\') || relative.Split('/').Any(part => part is "" or "." or ".."))
            throw new InvalidDataException($"Unsafe relative path: {relative}");
        root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var target = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!target.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"Path escapes its root: {relative}");
        return target;
    }

    public static void NoReparse(string root, string target)
    {
        var top = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        for (var path = target; path.Length >= top.Length; path = Path.GetDirectoryName(path) ?? "")
        {
            if ((File.Exists(path) || Directory.Exists(path)) &&
                File.GetAttributes(path).HasFlag(FileAttributes.ReparsePoint))
                throw new InvalidDataException("Reparse-point target is not supported: " + path);
            if (path.Equals(top, StringComparison.OrdinalIgnoreCase)) return;
        }
        throw new InvalidDataException("Managed path is outside the game root");
    }

    public static T Read<T>(string file) where T : class =>
        JsonSerializer.Deserialize<T>(File.ReadAllText(file), Json) ?? throw new InvalidDataException("Invalid JSON: " + file);

    public static void Write<T>(string file, T value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        var temp = file + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            var bytes = System.Text.Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value, Json) + "\n");
            using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                       4096, FileOptions.WriteThrough))
            {
                stream.Write(bytes);
                stream.Flush(true);
            }
            File.Move(temp, file, true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }

    public static void WriteFile(string file, byte[] bytes)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        using (var stream = new FileStream(file, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                   1024 * 1024, FileOptions.WriteThrough))
        {
            stream.Write(bytes);
            stream.Flush(true);
        }
        if (Hash(file) != Hash(bytes)) throw new IOException("Staged file readback failed: " + file);
    }

    public static void Replace(string file, byte[] bytes)
    {
        var staged = file + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            WriteFile(staged, bytes);
            File.Move(staged, file, true);
            if (Hash(file) != Hash(bytes)) throw new IOException("File readback failed: " + file);
        }
        finally { if (File.Exists(staged)) File.Delete(staged); }
    }
}
