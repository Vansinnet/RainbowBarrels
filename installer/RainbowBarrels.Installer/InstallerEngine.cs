using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace RainbowBarrels.Installer;

internal enum ActionKind { Install, Repair, Uninstall }

internal interface IGameGuard { void RequireClosed(); }

internal sealed class GameGuard : IGameGuard
{
    public void RequireClosed()
    {
        var processes = Process.GetProcessesByName("Darktide");
        try { if (processes.Length != 0) throw new InvalidOperationException("Close Darktide before changing game files."); }
        finally { foreach (var process in processes) process.Dispose(); }
    }
}

internal static class GameDiscovery
{
    public static IEnumerable<string> FindRoots()
    {
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
        {
            using var hive = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view);
            using var key = hive.OpenSubKey(@"SOFTWARE\Valve\Steam");
            if (key?.GetValue("InstallPath") is not string steam) continue;
            var libraries = new List<string> { steam };
            var folders = Path.Combine(steam, "steamapps", "libraryfolders.vdf");
            if (File.Exists(folders))
                libraries.AddRange(Regex.Matches(File.ReadAllText(folders), "\"path\"\\s+\"([^\"]+)\"")
                    .Select(match => match.Groups[1].Value.Replace("\\\\", "\\")));
            foreach (var library in libraries)
            {
                var root = Path.Combine(library, "steamapps", "common", "Warhammer 40,000 DARKTIDE");
                if (File.Exists(Path.Combine(root, "binaries", "Darktide.exe"))) paths.Add(root);
            }
        }
        return paths;
    }

    public static void Verify(string root, Manifest manifest)
    {
        var exe = Safe.PathUnder(root, "binaries/Darktide.exe");
        Safe.NoReparse(root, exe);
        if (!File.Exists(exe) || FileVersionInfo.GetVersionInfo(exe).FileVersion != manifest.ExeVersion)
            throw new InvalidDataException("Only Darktide executable " + manifest.ExeVersion + " is supported.");
        var apps = Directory.GetParent(root)?.Parent?.FullName;
        var app = apps is null ? "" : Path.Combine(apps, "appmanifest_" + manifest.SteamAppId + ".acf");
        if (!File.Exists(app) || Regex.Match(File.ReadAllText(app), "\"buildid\"\\s+\"([^\"]+)\"").Groups[1].Value != manifest.SteamBuild)
            throw new InvalidDataException("Only Darktide Steam build " + manifest.SteamBuild + " is supported.");
        var loader = Safe.PathUnder(root, "binaries/mod_loader");
        if (!File.Exists(Safe.PathUnder(root, "mods/dmf/dmf.mod")) ||
            (!Directory.Exists(loader) && !File.Exists(loader)))
            throw new InvalidDataException("Install DML and DMF before RainbowBarrels.");
    }
}

internal sealed class InstallerEngine
{
    private readonly string package;
    private readonly string state;
    private readonly IGameGuard guard;
    private readonly System.Action<int>? beforeWrite;
    private readonly string receiptPath;
    private readonly string journals;

    public InstallerEngine(string packageRoot, string? stateRoot = null, IGameGuard? gameGuard = null,
        System.Action<int>? beforeWrite = null)
    {
        package = Path.GetFullPath(packageRoot);
        state = Path.GetFullPath(stateRoot ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RainbowBarrels"));
        guard = gameGuard ?? new GameGuard();
        this.beforeWrite = beforeWrite;
        receiptPath = Path.Combine(state, "receipt.json");
        journals = Path.Combine(state, "journals");
    }

    public Manifest LoadManifest()
    {
        var manifest = Safe.Read<Manifest>(Safe.PathUnder(package, "payload/manifest.json"));
        if (manifest.Format != 1 || manifest.Product != "RainbowBarrels" || manifest.Version != "0.1.0-rc.1" ||
            manifest.Bundles.Count != 2 || manifest.Streams.Count != 1098 || manifest.ModFiles.Count != 4)
            throw new InvalidDataException("Wrong RainbowBarrels release payload.");
        var unique = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var recipe in manifest.Bundles)
        {
            if (!Regex.IsMatch(recipe.Target, "^bundle/[a-f0-9]{16}$") ||
                !recipe.Payload.StartsWith("payload/inserts/", StringComparison.Ordinal) ||
                recipe.StockCount is < 1 or > 2048 || recipe.AppendedCount is < 1 or > 2048 ||
                recipe.OutputSize is < 1 or > 64 * 1024 * 1024 || !unique.Add(recipe.Target))
                throw new InvalidDataException("Unsafe bundle recipe: " + recipe.Target);
            Safe.PathUnder(package, recipe.Payload);
        }
        foreach (var recipe in manifest.Streams.Concat(manifest.ModFiles))
        {
            if ((!Regex.IsMatch(recipe.Target, "^bundle/data/rb/[a-f0-9]{16}$") &&
                 !recipe.Target.StartsWith("mods/RainbowBarrels/", StringComparison.Ordinal)) ||
                recipe.Size < 1 || recipe.Size > 2 * 1024 * 1024 || !unique.Add(recipe.Target))
                throw new InvalidDataException("Unsafe file recipe: " + recipe.Target);
            Safe.PathUnder(package, recipe.Payload);
        }
        foreach (var recipe in manifest.ModFiles)
            if (!recipe.Payload.Equals(recipe.Target[5..], StringComparison.Ordinal) ||
                !recipe.Target.StartsWith("mods/RainbowBarrels/", StringComparison.Ordinal))
                throw new InvalidDataException("Mod payload path must resolve inside RainbowBarrels/.");
        if (unique.Count != 1104) throw new InvalidDataException("Incomplete release file list.");
        return manifest;
    }

    public string Execute(string gameRoot, ActionKind action, bool checkEnvironment = true)
    {
        gameRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(gameRoot));
        guard.RequireClosed();
        var manifest = LoadManifest();
        if (checkEnvironment) GameDiscovery.Verify(gameRoot, manifest);
        Recover(gameRoot);
        var existing = File.Exists(receiptPath) ? Safe.Read<Receipt>(receiptPath) : null;
        if (existing is not null && (existing.Version != manifest.Version ||
            existing.Product != manifest.Product ||
            !Path.GetFullPath(existing.GameRoot).Equals(gameRoot, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidDataException("An ownership receipt for another game folder or release exists.");
        if (action == ActionKind.Install && existing is not null)
            throw new InvalidOperationException("Already installed; use Repair or Uninstall.");
        if (action != ActionKind.Install && existing is null)
            throw new InvalidOperationException("This installer has no ownership receipt for RainbowBarrels.");
        var expected = manifest.Bundles.Select(b => b.Target).Concat(manifest.Streams.Select(s => s.Target))
            .Concat(manifest.ModFiles.Select(m => m.Target)).ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (existing is not null && (existing.Files.Count != expected.Count ||
            existing.Files.Select(file => file.Target).ToHashSet(StringComparer.OrdinalIgnoreCase).SetEquals(expected) == false))
            throw new InvalidDataException("The ownership receipt does not cover this exact release.");
        var plan = action switch
        {
            ActionKind.Install => PrepareInstall(gameRoot, manifest),
            ActionKind.Repair => PrepareRepair(gameRoot, manifest, existing!),
            ActionKind.Uninstall => PrepareUninstall(gameRoot, manifest, existing!),
            _ => throw new ArgumentOutOfRangeException(nameof(action))
        };
        if (plan.Count == 0) return "All RainbowBarrels files are already correct.";
        return Apply(gameRoot, manifest, existing, plan, action);
    }

    private List<Change> PrepareInstall(string root, Manifest manifest)
    {
        var plan = new List<Change>();
        foreach (var bundle in manifest.Bundles)
        {
            var target = GamePath(root, bundle.Target);
            Safe.Require(target, bundle.StockSize, bundle.StockSha256, "pristine Darktide bundle");
            var payload = Payload(bundle.Payload, bundle.PayloadSize, bundle.PayloadSha256);
            var output = BundleCodec.Reconstruct(File.ReadAllBytes(target), payload, bundle, root, manifest.OodleSha256);
            plan.Add(new Change(bundle.Target, bundle.StockSha256, bundle.OutputSha256, output, true));
        }
        foreach (var row in manifest.Streams.Concat(manifest.ModFiles))
        {
            var target = GamePath(root, row.Target);
            if (File.Exists(target) || Directory.Exists(target))
                throw new InvalidDataException("Refusing to adopt an existing file without a receipt: " + row.Target);
            plan.Add(new Change(row.Target, "absent", row.Sha256, Payload(row.Payload, row.Size, row.Sha256), false));
        }
        AddLoadOrder(root, plan);
        return plan;
    }

    private List<Change> PrepareRepair(string root, Manifest manifest, Receipt receipt)
    {
        var plan = new List<Change>();
        var backups = BackupRoot(receipt.Session);
        foreach (var recipe in manifest.Bundles)
        {
            var owned = receipt.Files.Single(file => file.Target == recipe.Target);
            if (!owned.Replacement || owned.Sha256 != recipe.OutputSha256 || owned.StockSha256 != recipe.StockSha256)
                throw new InvalidDataException("Bundle ownership receipt mismatch");
            var backup = Safe.PathUnder(backups, recipe.Target);
            Safe.Require(backup, recipe.StockSize, recipe.StockSha256, "owned stock bundle backup");
            var target = GamePath(root, recipe.Target);
            if (IsExact(target, recipe.OutputSize, recipe.OutputSha256)) continue;
            Safe.Require(target, recipe.StockSize, recipe.StockSha256, "repairable stock bundle");
            var payload = Payload(recipe.Payload, recipe.PayloadSize, recipe.PayloadSha256);
            var output = BundleCodec.Reconstruct(File.ReadAllBytes(backup), payload, recipe, root, manifest.OodleSha256);
            plan.Add(new Change(recipe.Target, recipe.StockSha256, recipe.OutputSha256, output, true));
        }
        foreach (var recipe in manifest.Streams.Concat(manifest.ModFiles))
        {
            var owned = receipt.Files.Single(file => file.Target == recipe.Target);
            if (owned.Replacement || owned.Sha256 != recipe.Sha256 || owned.Size != recipe.Size)
                throw new InvalidDataException("Added-file receipt mismatch: " + recipe.Target);
            var target = GamePath(root, recipe.Target);
            if (IsExact(target, recipe.Size, recipe.Sha256)) continue;
            if (File.Exists(target)) throw new InvalidDataException("Refusing to overwrite unknown repair target: " + recipe.Target);
            plan.Add(new Change(recipe.Target, "absent", recipe.Sha256,
                Payload(recipe.Payload, recipe.Size, recipe.Sha256), false));
        }
        AddLoadOrder(root, plan);
        return plan;
    }

    private List<Change> PrepareUninstall(string root, Manifest manifest, Receipt receipt)
    {
        var plan = new List<Change>();
        var backups = BackupRoot(receipt.Session);
        foreach (var recipe in manifest.Bundles)
        {
            var owned = receipt.Files.Single(file => file.Target == recipe.Target);
            if (!owned.Replacement || owned.Sha256 != recipe.OutputSha256 || owned.StockSha256 != recipe.StockSha256)
                throw new InvalidDataException("Bundle ownership receipt mismatch");
            var target = GamePath(root, recipe.Target);
            Safe.Require(target, recipe.OutputSize, recipe.OutputSha256, "owned bundle");
            var old = Safe.PathUnder(backups, recipe.Target);
            Safe.Require(old, recipe.StockSize, recipe.StockSha256, "owned stock backup");
            plan.Add(new Change(recipe.Target, recipe.OutputSha256, recipe.StockSha256, File.ReadAllBytes(old), true));
        }
        foreach (var recipe in manifest.Streams.Concat(manifest.ModFiles))
        {
            var owned = receipt.Files.Single(file => file.Target == recipe.Target);
            if (owned.Replacement || owned.Sha256 != recipe.Sha256 || owned.Size != recipe.Size)
                throw new InvalidDataException("Added-file receipt mismatch: " + recipe.Target);
            var target = GamePath(root, recipe.Target);
            Safe.Require(target, recipe.Size, recipe.Sha256, "owned added file");
            plan.Add(new Change(recipe.Target, recipe.Sha256, "absent", null, false));
        }
        var order = Safe.PathUnder(root, "mods/mod_load_order.txt");
        Safe.NoReparse(root, order);
        var bytes = File.ReadAllBytes(order);
        var updated = LoadOrder(bytes, false);
        if (!bytes.SequenceEqual(updated))
            plan.Add(new Change("mods/mod_load_order.txt", Safe.Hash(bytes), Safe.Hash(updated), updated, true));
        return plan;
    }

    private static readonly UTF8Encoding Utf8 = new(false, true);

    private static byte[] LoadOrder(byte[] current, bool add)
    {
        var text = Utf8.GetString(current);
        if (add)
        {
            if (Regex.IsMatch(text, @"(?im)^RainbowBarrels\r?$")) return current;
            var newline = text.Contains("\r\n", StringComparison.Ordinal) ? "\r\n" : "\n";
            return Utf8.GetBytes(text + (text.Length == 0 || text.EndsWith('\n') ? "" : newline) + "RainbowBarrels" + newline);
        }
        return Utf8.GetBytes(Regex.Replace(text, @"(?im)^RainbowBarrels(?:\r?\n|$)", ""));
    }

    private static void AddLoadOrder(string root, List<Change> plan)
    {
        var order = Safe.PathUnder(root, "mods/mod_load_order.txt");
        Safe.NoReparse(root, order);
        if (!File.Exists(order)) throw new InvalidDataException("DMF mod_load_order.txt is missing");
        var bytes = File.ReadAllBytes(order);
        var changed = LoadOrder(bytes, true);
        if (!bytes.SequenceEqual(changed))
            plan.Add(new Change("mods/mod_load_order.txt", Safe.Hash(bytes), Safe.Hash(changed), changed, true));
    }

    private string Apply(string root, Manifest manifest, Receipt? previous, List<Change> plan, ActionKind action)
    {
        var session = DateTime.UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" + Guid.NewGuid().ToString("N");
        var backupRoot = BackupRoot(session);
        Directory.CreateDirectory(backupRoot);
        var journal = new Journal { GameRoot = root, Session = session, Action = action.ToString() };
        var journalPath = Path.Combine(journals, session + ".json");
        if (action == ActionKind.Uninstall)
        {
            var beforeReceipt = File.ReadAllBytes(receiptPath);
            journal.ReceiptBeforeSha256 = Safe.Hash(beforeReceipt);
            Safe.WriteFile(Safe.PathUnder(backupRoot, "previous.receipt.json"), beforeReceipt);
        }
        foreach (var change in plan)
        {
            var target = GamePath(root, change.Target);
            string? backup = null;
            if (change.Before != "absent")
            {
                backup = Safe.PathUnder(backupRoot, change.Target);
                Safe.WriteFile(backup, File.ReadAllBytes(target));
                Safe.Require(backup, new FileInfo(target).Length, change.Before, "owned rollback source");
            }
            journal.Files.Add(new JournalFile { Target = change.Target, Before = change.Before,
                                                After = change.After, Backup = backup });
        }
        Safe.Write(journalPath, journal);
        var writes = 0;
        try
        {
            foreach (var change in plan)
            {
                guard.RequireClosed();
                beforeWrite?.Invoke(++writes);
                var target = GamePath(root, change.Target);
                if (change.Before == "absent" && File.Exists(target))
                    throw new InvalidDataException("A new file appeared during installation: " + change.Target);
                if (change.Before != "absent" && (!File.Exists(target) || Safe.Hash(target) != change.Before))
                    throw new InvalidDataException("A game file changed during installation: " + change.Target);
                if (change.After == "absent") File.Delete(target);
                else Safe.Replace(target, change.Content!);
                if (!IsState(target, change.After))
                    throw new IOException("Installed file readback failed: " + change.Target);
            }
            if (action == ActionKind.Uninstall) File.Delete(receiptPath);
            else if (action == ActionKind.Install)
            {
                var receipt = new Receipt { Product = manifest.Product, Version = manifest.Version,
                                            GameRoot = root, Session = session };
                receipt.Files.AddRange(manifest.Bundles.Select(bundle => new OwnedFile
                {
                    Target = bundle.Target, Size = bundle.OutputSize, Sha256 = bundle.OutputSha256,
                    Replacement = true, StockSize = bundle.StockSize, StockSha256 = bundle.StockSha256
                }));
                receipt.Files.AddRange(manifest.Streams.Concat(manifest.ModFiles).Select(file => new OwnedFile
                { Target = file.Target, Size = file.Size, Sha256 = file.Sha256 }));
                Safe.Write(receiptPath, receipt);
            }
            journal.State = "committed";
            Safe.Write(journalPath, journal);
            if (action == ActionKind.Uninstall) RemoveEmptyOwnedFolders(root);
            return action switch
            {
                ActionKind.Uninstall => "RainbowBarrels removed; exact stock bundles restored.",
                ActionKind.Repair => "RainbowBarrels repaired; missing files reconstructed.",
                _ => "RainbowBarrels installed. Open Mod Options to choose separate barrel hues."
            };
        }
        catch
        {
            Rollback(journal, journalPath);
            RestoreReceipt(journal);
            if (action == ActionKind.Install && File.Exists(receiptPath)) File.Delete(receiptPath);
            throw;
        }
    }

    private void Recover(string root)
    {
        if (!Directory.Exists(journals)) return;
        foreach (var path in Directory.GetFiles(journals, "*.json"))
        {
            var journal = Safe.Read<Journal>(path);
            if (journal.State is "committed" or "rolled_back") continue;
            if (!Path.GetFullPath(journal.GameRoot).Equals(root, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Pending install journal belongs to a different game folder.");
            Rollback(journal, path);
            RestoreReceipt(journal);
        }
    }

    private void RestoreReceipt(Journal journal)
    {
        if (journal.Action != ActionKind.Uninstall.ToString() || journal.ReceiptBeforeSha256 is null) return;
        var backup = Safe.PathUnder(BackupRoot(journal.Session), "previous.receipt.json");
        if (!File.Exists(backup) || Safe.Hash(backup) != journal.ReceiptBeforeSha256)
            throw new InvalidDataException("Uninstall receipt rollback copy changed.");
        if (File.Exists(receiptPath))
        {
            if (Safe.Hash(receiptPath) != journal.ReceiptBeforeSha256)
                throw new InvalidDataException("Uninstall ownership receipt was modified by another process.");
            return;
        }
        Safe.Replace(receiptPath, File.ReadAllBytes(backup));
    }

    private static void Rollback(Journal journal, string journalPath)
    {
        foreach (var entry in journal.Files.AsEnumerable().Reverse())
        {
            var target = Safe.PathUnder(journal.GameRoot, entry.Target);
            Safe.NoReparse(journal.GameRoot, target);
            if (IsState(target, entry.Before)) continue;
            if (!IsState(target, entry.After))
                throw new InvalidDataException("Cannot restore a file changed by another process: " + entry.Target);
            if (entry.Before == "absent") File.Delete(target);
            else
            {
                if (entry.Backup is null || !File.Exists(entry.Backup) || Safe.Hash(entry.Backup) != entry.Before)
                    throw new InvalidDataException("Missing exact rollback backup: " + entry.Target);
                Safe.Replace(target, File.ReadAllBytes(entry.Backup));
            }
        }
        journal.State = "rolled_back";
        Safe.Write(journalPath, journal);
        RemoveEmptyOwnedFolders(journal.GameRoot);
    }

    private static void RemoveEmptyOwnedFolders(string root)
    {
        foreach (var relative in new[] { "mods/RainbowBarrels/scripts/mods/RainbowBarrels",
                     "mods/RainbowBarrels/scripts/mods", "mods/RainbowBarrels/scripts", "mods/RainbowBarrels" })
        {
            var folder = Safe.PathUnder(root, relative);
            Safe.NoReparse(root, folder);
            if (Directory.Exists(folder) && !Directory.EnumerateFileSystemEntries(folder).Any())
                Directory.Delete(folder);
        }
    }

    private string GamePath(string root, string relative)
    {
        var path = Safe.PathUnder(root, relative);
        Safe.NoReparse(root, path);
        return path;
    }

    private byte[] Payload(string relative, long size, string digest)
    {
        var path = Safe.PathUnder(package, relative);
        Safe.NoReparse(package, path);
        Safe.Require(path, size, digest, "installer payload");
        return File.ReadAllBytes(path);
    }

    private string BackupRoot(string session) => Safe.PathUnder(state, "backups/" + session);

    private static bool IsExact(string path, long size, string hash) =>
        File.Exists(path) && new FileInfo(path).Length == size && Safe.Hash(path) == hash;

    private static bool IsState(string path, string sha) => sha == "absent" ? !File.Exists(path) && !Directory.Exists(path) :
        File.Exists(path) && Safe.Hash(path) == sha;

    private sealed record Change(string Target, string Before, string After, byte[]? Content, bool Replacement);
}
