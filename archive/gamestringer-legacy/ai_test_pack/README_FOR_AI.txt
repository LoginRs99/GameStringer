=== GameStringer Pipeline Summary ===
Last modified: August 07, 2026
Purpose: Extract translatable text from Unity games (Mono & IL2CPP)

=== Current Filter Philosophy ===

    Tier 1: Keep strings with spaces + 3+ letters, accented chars, or punctuation
    Tier 2: Keep single words only if TitleCase, ALL CAPS UI, or whitelisted
    Tier 3: Reject camelCase with code suffixes (handler, callback, manager, etc.)

=== Modules ===

    unity_mono.py: Asset extraction (MonoBehaviour, TextAsset)
    dll_scanner.py: Managed assembly string extraction (Mono) / IL2CppDumper fallback (IL2CPP)
    custom_table_extractor.py: Length-prefixed binary string scanning
    xliff_cleaner.py: Deduplication + noise filtering

=== Known Limitations ===

    IL2CPP games may still have metadata noise if filters are too loose
    Custom binary formats (Altar.Localization.StringTable) require custom_table_extractor
    Some edge-case text may be in runtime-loaded CSVs not scanned

=== Test Samples in this folder ===
1. children_of_morta_sample.txt — Children of Morta (Mono, Unity 2019/2021)
2. shoppe_keep_sample.txt — Shoppe Keep (Mono, Unity 5.3)
3. sunderfolk_sample.txt — Sunderfolk (IL2CPP, Unity 2022/2023)
4. cursebreaker_sample.txt — Cursebreaker (Mono, Unity 2021.3)
5. citizen_sleeper_sample.txt — Citizen Sleeper (Mono, Ink engine narrative text)

=== Suggested Review Tasks for Next AI ===

    Review the sample .txt files — are there obvious false positives (code, noise) that should be filtered?
    Review the sample .txt files — are there obvious false negatives (missing real text) visible in the game but not in the sample?
    Suggest improvements to the 3-tier filter logic in il2cpp_hybrid.py and dll_scanner.py
    Suggest additional per-game config options if needed
