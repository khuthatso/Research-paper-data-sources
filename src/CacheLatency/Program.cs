using System.Diagnostics;
using System.Globalization;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;

namespace CacheLatency;

/// <summary>
/// Pointer-chasing memory-latency benchmark.
/// For each working-set size it builds one random cycle through the array
/// (one node per 64-byte cache line) and times a long chain of dependent reads,
/// so the CPU cannot guess the next address and hide the latency.
/// Output: latency_raw.csv (every timed run) + a summary on the console.
/// </summary>
internal static class Program
{
    private const int NodeBytes = 64;                       // one node per cache line (64 B on this CPU)
    private const int IntsPerNode = NodeBytes / sizeof(int); // 16 ints = 64 bytes
    private const long Steps = 10_000_000;                  // dependent reads per timed run
    private const int Repeats = 7;                          // timed runs per working-set size
    private const int Seed = 12345;                         // fixed seed => same access order every run
    private const int MinPow = 12;                          // 2^12 = 4 KB
    private const int MaxPow = 28;                          // 2^28 = 256 MB
    private const int LogicalCpu = 2;                       // pin to logical processor 2

    private static long _sink;                              // consumes results so the JIT cannot remove the loop

    private static void Main()
    {
        // Polish regional settings use a decimal comma, which would break the CSV file.
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

        PrintEnvironment();

        using Process proc = Process.GetCurrentProcess();
        proc.ProcessorAffinity = (IntPtr)(1L << LogicalCpu);
        proc.PriorityClass = ProcessPriorityClass.High;
        Thread.CurrentThread.Priority = ThreadPriority.Highest;

        long[] sizes = BuildSizes();
        var csv = new StringBuilder("size_bytes,run,ns_per_access\n");

        Console.WriteLine();
        Console.WriteLine($"{"size",12} {"median_ns",10} {"min_ns",10} {"max_ns",10}");

        foreach (long sizeBytes in sizes)
        {
            int nodes = (int)(sizeBytes / NodeBytes);
            int[] a = BuildCycle(nodes);

            GC.Collect();
            GC.WaitForPendingFinalizers();

            // Warm-up: JIT is already forced optimized; this pulls the data into the caches.
            _sink += Chase(a, 0, Math.Max(2L * nodes, 1_000_000));

            double[] ns = new double[Repeats];
            int start = 0;
            for (int r = 0; r < Repeats; r++)
            {
                long t0 = Stopwatch.GetTimestamp();
                start = Chase(a, start, Steps);
                long t1 = Stopwatch.GetTimestamp();

                _sink += start;
                ns[r] = (t1 - t0) * 1e9 / Stopwatch.Frequency / Steps;
                csv.Append(sizeBytes).Append(',').Append(r + 1).Append(',')
                   .Append(ns[r].ToString("F4")).Append('\n');
            }

            double[] sorted = (double[])ns.Clone();
            Array.Sort(sorted);
            double median = sorted[Repeats / 2];
            Console.WriteLine($"{FormatSize(sizeBytes),12} {median,10:F3} {sorted[0],10:F3} {sorted[^1],10:F3}");
        }

        string path = Path.Combine(Directory.GetCurrentDirectory(), "latency_raw.csv");
        File.WriteAllText(path, csv.ToString());
        Console.WriteLine();
        Console.WriteLine($"Raw data written to: {path}");
        Console.WriteLine($"(sink = {_sink}; printed only so the work cannot be optimized away)");
    }

    /// <summary>Follows the chain 'steps' times. Each read depends on the previous one.</summary>
    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.AggressiveOptimization)]
    private static int Chase(int[] a, int start, long steps)
    {
        int p = start;
        for (long i = 0; i < steps; i++)
        {
            p = a[p];
        }
        return p;
    }

    /// <summary>
    /// Builds an int[] where element (k * 16) holds the index of the next node (also a multiple of 16).
    /// Sattolo's algorithm guarantees ONE cycle through all nodes, in random order.
    /// </summary>
    private static int[] BuildCycle(int nodes)
    {
        int[] order = new int[nodes];
        for (int i = 0; i < nodes; i++) order[i] = i;

        var rng = new Random(Seed);
        for (int i = nodes - 1; i > 0; i--)
        {
            int j = rng.Next(i);                 // 0 .. i-1  (never i, which is what makes it a single cycle)
            (order[i], order[j]) = (order[j], order[i]);
        }

        int[] a = new int[nodes * IntsPerNode];
        for (int i = 0; i < nodes; i++)
        {
            a[i * IntsPerNode] = order[i] * IntsPerNode;
        }
        return a;
    }

    /// <summary>Working-set sizes: 2^e and 1.5 x 2^e from 4 KB to 256 MB.</summary>
    private static long[] BuildSizes()
    {
        var list = new List<long>();
        for (int e = MinPow; e <= MaxPow; e++)
        {
            long p2 = 1L << e;
            list.Add(p2);
            if (e < MaxPow) list.Add(p2 + p2 / 2);
        }
        return list.ToArray();
    }

    private static string FormatSize(long bytes) =>
        bytes >= 1L << 20 ? $"{bytes / (double)(1L << 20):0.##} MB" : $"{bytes / 1024.0:0.##} KB";

    private static void PrintEnvironment()
    {
        Console.WriteLine($"Runtime        : {RuntimeInformation.FrameworkDescription}");
        Console.WriteLine($"OS             : {RuntimeInformation.OSDescription}");
        Console.WriteLine($"Processor count: {Environment.ProcessorCount} logical");
        Console.WriteLine($"64-bit process : {Environment.Is64BitProcess}");
#if DEBUG
        Console.WriteLine("Build          : DEBUG  <-- WARNING: results are NOT valid. Run: dotnet run -c Release");
#else
        Console.WriteLine("Build          : Release");
#endif
        if (Debugger.IsAttached)
            Console.WriteLine("WARNING: a debugger is attached. Run from a plain terminal instead.");
    }
}
