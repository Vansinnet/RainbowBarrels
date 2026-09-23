using RainbowBarrels.Installer;
using System.Text;
using System.Text.Json;

if (args.Length is not (2 or 4) || args[0] != "--package" ||
    (args.Length == 4 && args[2] != "--game"))
    throw new ArgumentException("Usage: dotnet run --project installer/RainbowBarrels.Installer.Tests -- --package <active-mod-root> [--game <installed-stock-root>]");
var sourcePackage = Path.GetFullPath(args[1]);
var temp = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
    "Temp", "opencode", "rb-installer-fixtures-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(temp);
try
{
    TestInstallRepairUninstall(sourcePackage, temp);
    TestAtomicRollback(sourcePackage, temp);
    TestTamperedInput(sourcePackage, temp);
    TestInterruptedUninstall(sourcePackage, temp);
    if (args.Length == 4) TestStockDecoder(args[3], sourcePackage);
    Console.WriteLine("PASS: install, repair, surgical uninstall, unknown-input rejection, and install/uninstall rollback in disposable synthetic stock fixtures.");
}
finally { if (Directory.Exists(temp)) Directory.Delete(temp, true); }

static void Check(bool condition, string message)
{
    if (!condition) throw new Exception("FAIL: " + message);
}

static (string Root, string Package, string State, Manifest Manifest, byte[][] Stock) Fixture(
    string input, string temp, string name)
{
    var root = Path.Combine(temp, name, "game");
    var package = Path.Combine(temp, name, "package");
    var state = Path.Combine(temp, name, "state");
    Directory.CreateDirectory(root);
    Directory.CreateDirectory(package);
    foreach (var file in Directory.EnumerateFiles(Path.Combine(input, "payload"), "*", SearchOption.AllDirectories))
    {
        var destination = Path.Combine(package, "payload", Path.GetRelativePath(Path.Combine(input, "payload"), file));
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        File.Copy(file, destination);
    }
    var manifest = Safe.Read<Manifest>(Path.Combine(package, "payload", "manifest.json"));
    foreach (var recipe in manifest.ModFiles)
    {
        var dest = Safe.PathUnder(package, recipe.Payload);
        Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
        File.Copy(Safe.PathUnder(input, recipe.Payload["RainbowBarrels/".Length..]), dest);
    }
    var stock = new byte[manifest.Bundles.Count][];
    for (var i = 0; i < manifest.Bundles.Count; i++)
    {
        var recipe = manifest.Bundles[i];
        var (index, record) = StockRecord(i);
        stock[i] = MakeBundle(index, record);
        recipe.StockCount = 1;
        recipe.StockSize = stock[i].Length;
        recipe.StockSha256 = Safe.Hash(stock[i]);
        recipe.StockIndexSha256 = Safe.Hash(index);
        recipe.StockLogicalSha256 = Safe.Hash(record);
        var insert = File.ReadAllBytes(Safe.PathUnder(package, recipe.Payload));
        var output = MakeBundle(index.Concat(insert.AsSpan(0, recipe.AppendedIndexSize).ToArray()).ToArray(),
            record.Concat(insert.AsSpan(recipe.AppendedIndexSize).ToArray()).ToArray());
        recipe.OutputSize = output.Length;
        recipe.OutputSha256 = Safe.Hash(output);
        var target = Safe.PathUnder(root, recipe.Target);
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        File.WriteAllBytes(target, stock[i]);
    }
    Directory.CreateDirectory(Safe.PathUnder(root, "mods"));
    File.WriteAllText(Safe.PathUnder(root, "mods/mod_load_order.txt"), "dmf\nRainbowFlame\n", new UTF8Encoding(false));
    Safe.Write(Path.Combine(package, "payload", "manifest.json"), manifest);
    return (root, package, state, manifest, stock);
}

static (byte[] Index, byte[] Record) StockRecord(int slot)
{
    using var index = new MemoryStream();
    using var pointer = new BinaryWriter(index);
    using var record = new MemoryStream();
    using var writer = new BinaryWriter(record);
    var ext = 0xaaaabbcc00000001UL + (ulong)slot;
    var name = 0xddddeeee00000001UL + (ulong)slot;
    pointer.Write(ext); pointer.Write(name); pointer.Write(0);
    writer.Write(ext); writer.Write(name); writer.Write(1); writer.Write(0);
    writer.Write(0); writer.Write((byte)0); writer.Write(4); writer.Write((byte)1); writer.Write(0);
    writer.Write(0xfeedf00d);
    return (index.ToArray(), record.ToArray());
}

static byte[] MakeBundle(byte[] index, byte[] logical)
{
    const int chunk = 0x80000;
    var chunks = (logical.Length + chunk - 1) / chunk;
    using var result = new MemoryStream();
    using var writer = new BinaryWriter(result);
    writer.Write(new byte[] { 8, 0, 0, 240, 3, 0, 0, 0 });
    writer.Write(index.Length / 20);
    writer.Write(new byte[256]);
    writer.Write(index);
    writer.Write(chunks);
    for (var i = 0; i < chunks; i++) writer.Write(chunk);
    while (result.Position % 16 != 0) writer.Write((byte)0);
    writer.Write(logical.Length); writer.Write(0);
    var expanded = new byte[chunks * chunk];
    logical.CopyTo(expanded, 0);
    for (var i = 0; i < chunks; i++)
    {
        writer.Write(chunk);
        while (result.Position % 16 != 0) writer.Write((byte)0);
        writer.Write(expanded, i * chunk, chunk);
    }
    return result.ToArray();
}

static void TestInstallRepairUninstall(string input, string temp)
{
    var (root, package, state, manifest, stock) = Fixture(input, temp, "lifecycle");
    var engine = new InstallerEngine(package, state, new OfflineGuard());
    Check(engine.Execute(root, ActionKind.Install, false).Contains("installed"), "normal install");
    Check(manifest.Bundles.Select(recipe => Safe.Hash(Safe.PathUnder(root, recipe.Target)))
              .SequenceEqual(manifest.Bundles.Select(recipe => recipe.OutputSha256)), "bundle reconstruction against independent fixture output");
    Check(manifest.Streams.All(recipe => Safe.Hash(Safe.PathUnder(root, recipe.Target)) == recipe.Sha256),
        "all 1098 custom streams installed");
    Check(File.ReadAllText(Safe.PathUnder(root, "mods/mod_load_order.txt")).Contains("RainbowBarrels\n"),
        "load-order activation");
    Check(File.Exists(Path.Combine(state, "receipt.json")), "install ownership receipt");
    var missing = Safe.PathUnder(root, manifest.Streams[500].Target);
    File.Delete(missing);
    Check(engine.Execute(root, ActionKind.Repair, false).Contains("repaired"), "repair missing owned stream");
    Check(Safe.Hash(missing) == manifest.Streams[500].Sha256, "repair authenticates restored stream");
    var overwritten = Safe.PathUnder(root, manifest.Bundles[0].Target);
    File.WriteAllBytes(overwritten, stock[0]);
    Check(engine.Execute(root, ActionKind.Repair, false).Contains("repaired"), "repair exact Steam-restored stock bundle");
    Check(Safe.Hash(overwritten) == manifest.Bundles[0].OutputSha256, "reconstructed bundle matches tested output");
    var loadOrder = Safe.PathUnder(root, "mods/mod_load_order.txt");
    File.AppendAllText(loadOrder, "VortexOtherMod\n");
    Check(engine.Execute(root, ActionKind.Uninstall, false).Contains("removed"), "uninstall");
    Check(manifest.Bundles.Select((recipe, index) => File.ReadAllBytes(Safe.PathUnder(root, recipe.Target))
              .SequenceEqual(stock[index])).All(equal => equal), "stock bundle rollback");
    Check(manifest.Streams.All(recipe => !File.Exists(Safe.PathUnder(root, recipe.Target))) &&
          manifest.ModFiles.All(recipe => !File.Exists(Safe.PathUnder(root, recipe.Target))),
        "only owned additions removed");
    Check(File.ReadAllText(loadOrder) == "dmf\nRainbowFlame\nVortexOtherMod\n", "unrelated load order preserved");
}

static void TestAtomicRollback(string input, string temp)
{
    var (root, package, state, manifest, stock) = Fixture(input, temp, "rollback");
    var engine = new InstallerEngine(package, state, new OfflineGuard(), write =>
    {
        if (write == 5) throw new InvalidOperationException("Simulated interrupted install");
    });
    try { engine.Execute(root, ActionKind.Install, false); throw new Exception("Expected interrupted install"); }
    catch (InvalidOperationException e) when (e.Message == "Simulated interrupted install") { }
    Check(manifest.Bundles.Select((recipe, index) => File.ReadAllBytes(Safe.PathUnder(root, recipe.Target))
              .SequenceEqual(stock[index])).All(equal => equal), "both stock bundles restored on fault");
    Check(manifest.Streams.All(recipe => !File.Exists(Safe.PathUnder(root, recipe.Target))) &&
          !File.Exists(Path.Combine(state, "receipt.json")), "partial files and false ownership removed");
}

static void TestTamperedInput(string input, string temp)
{
    var (root, package, state, manifest, _) = Fixture(input, temp, "tamper");
    var bundle = Safe.PathUnder(root, manifest.Bundles[0].Target);
    var bytes = File.ReadAllBytes(bundle);
    bytes[^1] ^= 1;
    File.WriteAllBytes(bundle, bytes);
    var engine = new InstallerEngine(package, state, new OfflineGuard());
    try { engine.Execute(root, ActionKind.Install, false); throw new Exception("Expected input rejection"); }
    catch (InvalidDataException) { }
    Check(!File.Exists(Path.Combine(state, "receipt.json")) &&
          manifest.Streams.All(recipe => !File.Exists(Safe.PathUnder(root, recipe.Target))),
          "tampered stock rejected before mutation");
}

static void TestInterruptedUninstall(string input, string temp)
{
    var (root, package, state, manifest, _) = Fixture(input, temp, "uninstall-fault");
    new InstallerEngine(package, state, new OfflineGuard()).Execute(root, ActionKind.Install, false);
    var interrupted = new InstallerEngine(package, state, new OfflineGuard(), write =>
    {
        if (write == 5) throw new InvalidOperationException("Simulated interrupted uninstall");
    });
    try { interrupted.Execute(root, ActionKind.Uninstall, false); throw new Exception("Expected interrupted uninstall"); }
    catch (InvalidOperationException e) when (e.Message == "Simulated interrupted uninstall") { }
    Check(File.Exists(Path.Combine(state, "receipt.json")), "ownership receipt survives uninstall rollback");
    Check(manifest.Bundles.All(recipe => Safe.Hash(Safe.PathUnder(root, recipe.Target)) == recipe.OutputSha256),
        "installed bundles restored on uninstall fault");
    Check(manifest.Streams.All(recipe => Safe.Hash(Safe.PathUnder(root, recipe.Target)) == recipe.Sha256),
        "deleted streams restored on uninstall fault");
    Check(new InstallerEngine(package, state, new OfflineGuard()).Execute(root, ActionKind.Uninstall, false).Contains("removed"),
        "uninstall succeeds after rollback");
}

static void TestStockDecoder(string game, string input)
{
    const string stockSha = "86d24e1dd5796d4cbc2dee764b1860b2b327c21dfbad5e4f45083d1c9c045fa9";
    const string logicalSha = "2b62660ea883e910edecb87afdce595605ea62ecc8caf6a3b43eb9b4aa3d810b";
    var bundle = Safe.PathUnder(game, "bundle/d2b0b18252164f5b");
    Safe.Require(bundle, new FileInfo(bundle).Length, stockSha, "pristine Oodle decoder control");
    var manifest = Safe.Read<Manifest>(Safe.PathUnder(input, "payload/manifest.json"));
    var logical = BundleCodec.DecodeStock(File.ReadAllBytes(bundle), 28, game, manifest.OodleSha256);
    Check(Safe.Hash(logical) == logicalSha && logical.Length == 163671,
          "native game decoder matches independent Python stock record readback");
    Console.WriteLine("PASS: native Oodle decode on SHA-pinned, unrelated pristine game stock bundle (read-only).");
}

internal sealed class OfflineGuard : IGameGuard
{
    public void RequireClosed() { }
}
