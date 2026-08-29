"""Language style presets for Hungarian game localization."""

from __future__ import annotations

LANG_STYLE_PRESETS: dict[str, str] = {
    "Modern, laza (kortárs akció/kaland)": (
        "# Language style guide\n\n"
        "## Tone\n"
        "Modern, laza hangvétel. Rövid, pergő mondatok, minimális formalitás.\n\n"
        "## Loanwords\n"
        "Bevett angol gaming-szleng megtartható ott, ahol a magyar játékos közösség is így használja "
        "(pl. loot, buff, boss, spawn) — ne magyarosíts erőltetetten, ha a közösségi szóhasználat az angolt őrizte meg.\n\n"
        "## Punctuation & rhythm\n"
        "Rövid mondatok, kevés alárendelés. Felkiáltójel csak ott, ahol a forrás is hangsúlyos/sürgető.\n"
    ),
    "Fantasy/archaikus (RPG, epikus fantasy)": (
        "# Language style guide\n\n"
        "## Tone\n"
        "Választékosabb, kissé emelkedett stílus, a műfaj epikus hangvételéhez illeszkedve.\n\n"
        "## Loanwords\n"
        "Terminológia inkább magyarosítva, ha van rá természetes magyar szó "
        "(pl. \"zsákmány\" a \"loot\" helyett, \"küldetés\" a \"quest\" helyett) — angol szó csak ott maradjon, "
        "ahol nincs jó magyar megfelelő, vagy a glosszárium kifejezetten így rögzíti.\n\n"
        "## Punctuation & rhythm\n"
        "Hosszabb, irodalmibb mondatszerkezet megengedett. Kerüld a túl modern, köznyelvi fordulatokat.\n"
    ),
    "Semleges/technikai (szimulátor, stratégia, UI-nehéz)": (
        "# Language style guide\n\n"
        "## Tone\n"
        "Tömör, pontos, semleges hangvétel. Az egyértelműség elsőbbséget élvez a hangulati díszítéssel szemben.\n\n"
        "## Loanwords\n"
        "Bevett szakzsargon/technikai terminológia megtartható, ha az a magyar szakmai/játékos közösségben is így elterjedt.\n\n"
        "## Punctuation & rhythm\n"
        "Rövid, világos mondatok. Kerüld a felesleges jelzőket és a díszítő körülírást — "
        "UI-szövegnél a tömörség fontosabb a stílusnál.\n"
    ),
    "Humoros/ironikus (comedy/paródia)": (
        "# Language style guide\n\n"
        "## Tone\n"
        "Szabadabb fordítói mozgástér — a poén/hangulat megőrzése fontosabb a szó szerinti hűségnél.\n\n"
        "## Loanwords\n"
        "Nincs kötött szabály — azt a formát válaszd (angol vagy magyar), amelyik jobban \"poénkodik\" az adott kontextusban.\n\n"
        "## Punctuation & rhythm\n"
        "Magyar idiómák és szófordulatok becsempészése megengedett, ha megőrzi az eredeti komikus szándékot. "
        "Ha egy szó szerinti fordítás elveszítené a poént, inkább lokalizálj egy hasonló magyar fordulattal, mint hogy szó szerint fordíts.\n"
    ),
    "Érzelmes / Életszagú (narratív / slice-of-life)": (
        "# Language style guide\n\n"
        "## Tone\n"
        "Mélyen emberi, meghitt, természetes és életszerű hétköznapi stílus (slice-of-life). "
        "Kerüld a merev, rideg hivatalosságot, de a túlzó, modoros szlenget is — a hangsúly a hiteles érzelmeken és a természetes beszélt nyelven van.\n\n"
        "## Loanwords\n"
        "Természetes, modern hétköznapi magyar szóhasználat. Idegen kifejezések csak ott maradjanak, ahol a mai beszélt nyelvben is teljesen megszokottak.\n\n"
        "## Punctuation & rhythm\n"
        "Természetes élőbeszéd ritmusa. Rövidebb, gördülékeny mondatok, emberi párbeszédek.\n"
    ),
}

DEFAULT_LANG_STYLE_HEADER = "# Language style guide\n"
