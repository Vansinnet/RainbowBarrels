using System.Buffers.Binary;
using System.Runtime.InteropServices;

namespace RainbowBarrels.Installer;

internal static class BundleCodec
{
    private const int Chunk = 0x80000;
    private const int Header = 268;
    private static readonly byte[] Magic = [8, 0, 0, 240, 3, 0, 0, 0];

    public static byte[] Reconstruct(byte[] stock, byte[] insert, BundleRecipe recipe, string gameRoot,
        string expectedOodleSha)
    {
        if (stock.Length != recipe.StockSize || Safe.Hash(stock) != recipe.StockSha256 ||
            stock.Length >= 64 * 1024 * 1024 || !stock.AsSpan(0, 8).SequenceEqual(Magic))
            throw new InvalidDataException("Unexpected stock game bundle: " + recipe.Target);
        if (Safe.Hash(insert) != recipe.PayloadSha256 || insert.Length != recipe.PayloadSize ||
            recipe.AppendedIndexSize != checked(recipe.AppendedCount * 20) || insert.Length < recipe.AppendedIndexSize)
            throw new InvalidDataException("Invalid or unauthenticated custom bundle records");
        if (Read32(stock, 8) != recipe.StockCount || recipe.StockCount < 1 || recipe.StockCount > 2048 ||
            stock.Length < Header + recipe.StockCount * 20 + 4)
            throw new InvalidDataException("Unsupported stock bundle index");
        var stockIndex = stock.AsSpan(Header, recipe.StockCount * 20);
        if (Safe.Hash(stockIndex.ToArray()) != recipe.StockIndexSha256)
            throw new InvalidDataException("Stock resource-index identity changed");
        var addedIndex = insert.AsSpan(0, recipe.AppendedIndexSize);
        var count = checked(recipe.StockCount + recipe.AppendedCount);
        if (count > 2048) throw new InvalidDataException("Expanded bundle exceeds validated resource bound");
        var identities = new HashSet<(ulong, ulong)>();
        AddIdentities(stockIndex, identities);
        AddIdentities(addedIndex, identities);
        var logical = DecodeStock(stock, recipe.StockCount, gameRoot, expectedOodleSha);
        if (Safe.Hash(logical) != recipe.StockLogicalSha256)
            throw new InvalidDataException("Reconstructed stock logical records differ from sealed candidate");
        var added = insert.AsSpan(recipe.AppendedIndexSize);
        CheckAddedRecords(added, addedIndex, recipe.AppendedCount);
        using var output = new MemoryStream();
        using var writer = new BinaryWriter(output);
        writer.Write(Magic);
        writer.Write(count);
        writer.Write(stock, 12, 256);
        writer.Write(stockIndex);
        writer.Write(addedIndex);
        var length = checked(logical.Length + added.Length);
        var chunks = checked((length + Chunk - 1) / Chunk);
        if (chunks is < 1 or > 64) throw new InvalidDataException("Expanded bundle exceeds chunk bound");
        writer.Write(chunks);
        for (var index = 0; index < chunks; index++) writer.Write(Chunk);
        Align(writer);
        writer.Write(length);
        writer.Write(0);
        var bytes = new byte[chunks * Chunk];
        logical.CopyTo(bytes, 0);
        added.CopyTo(bytes.AsSpan(logical.Length));
        for (var index = 0; index < chunks; index++)
        {
            writer.Write(Chunk);
            Align(writer);
            writer.Write(bytes, index * Chunk, Chunk);
        }
        var result = output.ToArray();
        if (result.Length != recipe.OutputSize || Safe.Hash(result) != recipe.OutputSha256)
            throw new InvalidDataException("Expanded bundle does not match the release's tested output");
        return result;
    }

    private static void AddIdentities(ReadOnlySpan<byte> rows, HashSet<(ulong, ulong)> result)
    {
        for (var offset = 0; offset < rows.Length; offset += 20)
        {
            var extension = BinaryPrimitives.ReadUInt64LittleEndian(rows[offset..]);
            var name = BinaryPrimitives.ReadUInt64LittleEndian(rows[(offset + 8)..]);
            if (!result.Add((extension, name))) throw new InvalidDataException("Duplicate bundle identity");
        }
    }

    internal static byte[] DecodeStock(byte[] stock, int resourceCount, string gameRoot, string oodleSha)
    {
        var cursor = checked(Header + resourceCount * 20);
        var chunks = Read32(stock, cursor);
        cursor += 4;
        if (chunks is < 1 or > 64 || stock.Length - cursor < chunks * 4)
            throw new InvalidDataException("Stock bundle chunk table");
        var sizes = new int[chunks];
        for (var i = 0; i < chunks; i++, cursor += 4)
        {
            sizes[i] = Read32(stock, cursor);
            if (sizes[i] is < 1 or > Chunk) throw new InvalidDataException("Stock bundle chunk size");
        }
        cursor = (cursor + 15) & ~15;
        var length = Read32(stock, cursor);
        if (Read32(stock, cursor + 4) != 0 || length <= 0 || length > chunks * Chunk ||
            (length + Chunk - 1) / Chunk != chunks)
            throw new InvalidDataException("Stock bundle logical length");
        cursor += 8;
        using var decoder = sizes.Any(size => size != Chunk) ? new Oodle(gameRoot, oodleSha) : null;
        var logical = new byte[chunks * Chunk];
        for (var i = 0; i < chunks; i++)
        {
            if (Read32(stock, cursor) != sizes[i]) throw new InvalidDataException("Stock chunk envelope");
            cursor = (cursor + 4 + 15) & ~15;
            if (stock.Length - cursor < sizes[i]) throw new InvalidDataException("Truncated stock chunk");
            if (sizes[i] == Chunk)
                Buffer.BlockCopy(stock, cursor, logical, i * Chunk, Chunk);
            else
                decoder!.Decompress(stock.AsSpan(cursor, sizes[i]).ToArray(), logical, i * Chunk);
            cursor += sizes[i];
        }
        if (cursor != stock.Length || logical.AsSpan(length).IndexOfAnyExcept((byte)0) >= 0)
            throw new InvalidDataException("Stock bundle trailing data or nonzero padding");
        return logical.AsSpan(0, length).ToArray();
    }

    private static void CheckAddedRecords(ReadOnlySpan<byte> raw, ReadOnlySpan<byte> index, int count)
    {
        var cursor = 0;
        for (var i = 0; i < count; i++)
        {
            if (raw.Length - cursor < 24) throw new InvalidDataException("Short custom record header");
            var entry = index.Slice(i * 20, 20);
            if (BinaryPrimitives.ReadUInt64LittleEndian(raw[cursor..]) != BinaryPrimitives.ReadUInt64LittleEndian(entry) ||
                BinaryPrimitives.ReadUInt64LittleEndian(raw[(cursor + 8)..]) != BinaryPrimitives.ReadUInt64LittleEndian(entry[8..]))
                throw new InvalidDataException("Custom record/index identity mismatch");
            var variants = BinaryPrimitives.ReadInt32LittleEndian(raw[(cursor + 16)..]);
            if (variants is < 1 or > 64 || Read32(raw, cursor + 20) != 0)
                throw new InvalidDataException("Unsupported custom record variants");
            cursor += 24;
            var body = 0;
            for (var v = 0; v < variants; v++)
            {
                if (raw.Length - cursor < 14) throw new InvalidDataException("Short custom resource descriptor");
                if (raw[cursor + 4] is not (0 or 1) || raw[cursor + 9] != 1)
                    throw new InvalidDataException("Unsupported custom resource mode");
                body = checked(body + Read32(raw, cursor + 5) + Read32(raw, cursor + 10));
                cursor += 14;
            }
            if (raw.Length - cursor < body) throw new InvalidDataException("Truncated custom resource body");
            cursor += body;
        }
        if (cursor != raw.Length) throw new InvalidDataException("Unconsumed custom resource payload");
    }

    private static int Read32(ReadOnlySpan<byte> raw, int offset)
    {
        if (offset < 0 || raw.Length - offset < 4) throw new InvalidDataException("Bundle field bounds");
        return BinaryPrimitives.ReadInt32LittleEndian(raw[offset..]);
    }

    private static void Align(BinaryWriter writer)
    {
        while (writer.BaseStream.Position % 16 != 0) writer.Write((byte)0);
    }

    private sealed unsafe class Oodle : IDisposable
    {
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate ulong ScratchSize(int compressor, long length);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate ulong Decompressor(nint source, ulong sourceLength, nint target, ulong targetLength,
            int fuzzSafe, int crc, int verbosity, nint dictionary, ulong dictionaryLength, nint callback,
            nint callbackUser, nint scratch, ulong scratchLength, int threadPhase);

        private readonly nint library;
        private readonly Decompressor decompress;
        private readonly byte[] scratch;

        public Oodle(string gameRoot, string expectedSha)
        {
            var file = Safe.PathUnder(gameRoot, "binaries/oo2core_9_win64.dll");
            Safe.NoReparse(gameRoot, file);
            Safe.Require(file, new FileInfo(file).Length, expectedSha, "game's Oodle decoder");
            library = NativeLibrary.Load(file);
            var memory = Marshal.GetDelegateForFunctionPointer<ScratchSize>(
                NativeLibrary.GetExport(library, "OodleLZDecoder_MemorySizeNeeded"));
            var size = memory(-1, -1);
            if (size is < 1 or > 16 * 1024 * 1024)
                throw new InvalidDataException("Unsupported game decoder scratch size");
            scratch = new byte[(int)size];
            decompress = Marshal.GetDelegateForFunctionPointer<Decompressor>(
                NativeLibrary.GetExport(library, "OodleLZ_Decompress"));
        }

        public void Decompress(byte[] compressed, byte[] destination, int offset)
        {
            fixed (byte* source = compressed, output = &destination[offset], memory = scratch)
            {
                var actual = decompress((nint)source, (ulong)compressed.Length, (nint)output, Chunk,
                    1, 0, 3, 0, 0, 0, 0, (nint)memory, (ulong)scratch.Length, 3);
                if (actual != Chunk) throw new InvalidDataException("Game decoder rejected stock chunk");
            }
        }

        public void Dispose() => NativeLibrary.Free(library);
    }
}
