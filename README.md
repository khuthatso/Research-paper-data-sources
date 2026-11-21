# Estimating Processor Cache Sizes from Memory Latency Using Pointer Chasing in C#

Reproducibility package for a research paper written for the **Student Research Challenge**,
*Architecture of Computers* course, Vistula University, 2026/27.

- **Author:** [your name]
- **Student ID:** [your student ID]

## What this study does

Processors keep small, fast memories (L1, L2, L3 caches) between the CPU and main memory (RAM).
This project measures memory latency with a **pointer-chasing benchmark written in C#**: a random
cycle through a block of memory is followed with dependent reads, so the processor cannot guess
the next address and hide the latency. Repeating the test for larger blocks (4 KB to 256 MB)
produces a latency curve whose steps indicate the cache boundaries. The steps are then compared
with the cache sizes published by the manufacturer.

**Research question:** How accurately can the L1, L2 and L3 cache sizes of a modern processor be
recovered from pointer-chasing latency measurements written in C#, and how do they compare with the
manufacturer's published sizes?

## Repository contents

```
.
├── src/CacheLatency/        C# benchmark (Program.cs, CacheLatency.csproj)
├── data/                    Raw measurements: run1.csv, run2.csv, run3.csv
├── analysis/analyze.py      Python script: statistics, step detection, figure
├── results/                 Output of analyze.py (tables, summary.txt, figure)
├── requirements.txt         Python dependencies
└── README.md
```

## Test system

| Component | Specification |
|---|---|
| Computer | HP Pavilion Laptop 15-eh1xxx |
| Processor | AMD Ryzen 7 5700U (Zen 2), 8 cores / 16 logical processors |
| Published caches | 32 KB L1 data per core, 512 KB L2 per core, 8 MB L3 shared |
| Memory | 8 GB (7.33 GB usable), 3,200 MT/s |
| Operating system | Windows 11, version 26H2 (build 10.0.26300) |
| Runtime | .NET 10.0.8 (SDK 10.0.300) |

## Measurement sessions

All three sessions used the same program and parameters. They differ only in the power condition
of the laptop:

| File | Condition |
|---|---|
| `data/run1.csv` | Laptop unplugged (battery power) |
| `data/run2.csv` | [fill in: for example, plugged in, power mode ...] |
| `data/run3.csv` | [fill in: same as run 2] |

## How to run the benchmark (C#)

Requirements: Windows, .NET SDK 10.

```
cd src/CacheLatency
dotnet run -c Release
```

Always use the **Release** configuration and run from a plain terminal (not a debugger); the
program prints a warning otherwise. For comparable results, close other applications and do not
use the laptop during the run. The program writes `latency_raw.csv` to the current folder.
Rename it (for example `run1.csv`) before the next session, because it is overwritten each time.

### Parameters (fixed in `Program.cs`)

| Parameter | Value |
|---|---|
| Memory per node | 64 bytes (one cache line) |
| Working-set sizes | 4 KB to 256 MB, 33 sizes (powers of two and 1.5x midpoints) |
| Dependent reads per timed run | 10,000,000 |
| Warm-up | at least 1,000,000 reads, or twice the number of cache lines if larger |
| Timed runs per size | 7 |
| Random seed | 12345 (single-cycle permutation, Sattolo's algorithm) |
| Process settings | pinned to logical processor 2, high priority |
| Timer | `System.Diagnostics.Stopwatch` |

### Data format

Each CSV has 231 rows (33 sizes x 7 runs) and three columns:
`size_bytes`, `run` (1 to 7) and `ns_per_access` (nanoseconds per dependent read).

## How to run the analysis (Python)

Requirements: Python 3.10 or newer.

```
pip install -r requirements.txt
python analysis/analyze.py
```

Run from the repository root. The script reads `data/run1.csv`, `data/run2.csv` and
`data/run3.csv` and writes to `results/`:

| File | Content |
|---|---|
| `per_size_summary.csv` | Median, minimum, maximum and relative spread per size and session; run 2 vs run 3 difference; run 1 vs run 2/3 ratio |
| `step_detection.csv` | Detected latency steps (brackets) for thresholds 1.5 (main), 1.3 and 2.0 |
| `published_comparison.csv` | Comparison of each bracket with the published cache sizes |
| `summary.txt` | Key numbers in text form |
| `figure2_latency_vs_size.png` | Latency against working-set size for all three sessions |

### Analysis rules

The rules were fixed before the estimates were calculated and were not changed afterwards:

- A **step** is a ratio of at least 1.5 between the medians of two consecutive sizes. Thresholds of
  1.3 and 2.0 are reported as a sensitivity check.
- If consecutive pairs of sizes both qualify, they count as one transition that starts at the first pair.
- A transition is reported as a **bracket**: the largest size before the step and the next size.
- Repeatability is the relative difference of the run 2 and run 3 medians, |a - b| / mean(a, b).

## Limitations

- Results describe one laptop and cannot be generalized to other processors.
- Array bounds checking, the use of 4 KB memory pages and variation in processor clock speed are part
  of every measurement. The clock speed was not recorded.
- The latencies depend on the power state of the laptop; run 1 (unplugged) differs systematically
  from the other sessions.
- The working-set sizes form a grid, so a cache boundary can only be located within a bracket.

## Use of generative AI

Claude (Anthropic) was used to help design the benchmark and the analysis script, to explain concepts
and to edit text. The author tested the code, ran all measurements on their own laptop and checked the
results and sources. [Review this paragraph so it matches exactly what you did.]

## Reference values

Published cache sizes of the AMD Ryzen 7 5700U: [add the link to AMD's product page and the access date].
