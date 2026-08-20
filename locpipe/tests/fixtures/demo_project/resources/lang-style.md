# Language style guide (Hungarian)

## Register — see character-voices.md for full detail
Default by category, unless a specific rule below or a character-voice entry overrides it:
- **UI / tutorial / system messages** → formal, neutral address (magázás — "Ön", "kérjük", imperative forms like "Válasszon", "Erősítse meg"). No character is "speaking" these; treat them like the game software addressing the player directly, not a companion character.
- **Dialogue** (any line with a `speaker`) → informal (tegezés) by default. See character-voices.md for per-character overrides — a given NPC may always speak formally (nobility, an antagonist keeping deliberate distance, a system/AI voiced as a person) regardless of this default.
- **Developer/debug text** → no register. Not player-facing; translate for legibility only, don't apply a persona.

Never mix magázás and tegezés forms within a single line — check subject/verb/pronoun agreement for whichever register actually applies to that line.

## Gender neutrality
Hungarian has no grammatical gender: "ő" covers he/she/it, and adjectives/verbs never agree with a referent's gender the way German (er/sie), English (he/she), or French (il/elle) do.

If the source contains gender-slot markup ({ms|...}{fs|...} or similar), the default is to put the SAME Hungarian text in both slots. There's nothing for Hungarian to grammatically distinguish here — a gendered pronoun/adjective agreement in the source has no Hungarian equivalent to carry it.

Exception: if the two slots' source text differs for a genuinely semantic reason — not grammatical agreement, but actual different content (a kinship term like "his brother" vs. "her sister," or a line that names the referent by a gendered noun) — translate each slot's actual content correctly, which may legitimately produce different Hungarian text. Test: would a competent human translator, told nothing about "gender agreement" and just asked to translate each slot's literal content, produce different Hungarian? If yes, differ them. If the only reason they differ in the source is grammatical agreement with no semantic content difference, collapse them to identical Hungarian.

Example — pure grammatical agreement, Hungarian identical in both slots:
- Source: "You found {ms|his}{fs|her} sword."
- Hungarian (both slots): "Megtaláltad a kardját."

Example — genuine semantic content difference, Hungarian may legitimately differ:
- Source: "Talk to {ms|him, your brother}{fs|her, your sister}."
- Hungarian ms: "Beszélj vele, a bátyáddal."
- Hungarian fs: "Beszélj vele, a nővéreddel."

## Natural word order & focus
Hungarian marks emphasis and new information with word order (topic-focus structure), not just intonation the way English does or verb-second position the way German does. The FOCUS element — whatever is being emphasized, contrasted, or is the answer to an implicit question — goes immediately before the finite verb. A verb with a detachable preverb (igekötő: meg-, el-, ki-, be-, fel-, etc.) has that preverb split off and move after the verb whenever something else occupies focus position; it stays attached, verb-initial, only in neutral, all-new-information sentences.

Don't default to mirroring the source's word order. Identify what's actually being emphasized and restructure around it.

Example — neutral statement, preverb attached:
- Source: "Peter closed the door."
- Hungarian: "Péter bezárta az ajtót."

Example — focus on WHO did it (contrastive — it was Peter, not someone else), preverb detaches:
- Source/context: answering "who closed the door?"
- Hungarian: "Péter zárta be az ajtót."

This matters most in dialogue answering a question, reacting to something, or making a correction — a literal source-order translation often produces grammatically valid but oddly-emphasized Hungarian that doesn't read like a natural reply.

## Agglutination & stem alternation
Hungarian marks grammatical relations (case, possession, plurality, and more) with suffixes chained onto a word's stem, not separate words or prepositions the way German/English mostly do. Vowel harmony determines which variant of a suffix to use — this should come naturally as a fluent Hungarian generator; the point here is about the STEM, not suffix choice.

Most Hungarian words simply take a suffix appended to an unchanged stem. But some common, everyday words change stem shape under certain suffixes — this is correct Hungarian grammar, not an error, and a correctly-inflected stem-alternating form should never be "corrected" back toward the dictionary-form stem:

- ló (horse) → lovak (plural), lovat (accusative) — not "lók"/"lót"
- kéz (hand) → kezek (plural), kezet (accusative) — the long é shortens to e before these suffixes

Practical implication for glossary terms specifically: if a glossary entry is an ordinary Hungarian word (rather than an invented proper noun) and the grammatically correct form in context is a stem-alternating one, use that correct form even though it won't contain the glossary's dictionary-form entry as a literal substring. Grammatical correctness takes priority over exact-substring preservation here — this is also why glossary.md's protected-term checking (glossary_terms.py) is deliberately scoped to invented/proper-noun-style terms that don't undergo this kind of alternation, not to ordinary vocabulary.
