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
    "Vizuális Regény / Felnőtt (NSFW & Romantika / Eroge)": (
        "# Language style guide\n\n"
        "## Tone & Register\n"
        "Érzelmes, közvetlen, érzéki és lezser vizuális regény hangvétel. "
        "A karakterek természetes élőbeszédben, kötetlenül tegeződnek egymással (informal).\n\n"
        "## NSFW & Erotikus nyelvezet\n"
        "Természetes, vonzó és élvezhető magyar erotikus szókincs. Kerüld a rideg orvosi/anatómiai latin szakszavakat, "
        "de a feleslegesen durva, alpári trágárságot is, hacsak a karakter személyisége vagy a szituáció kifejezetten nem azt kívánja. "
        "A forrás explicitási szintjét és szenvedélyét hűen, cenzúra és prűd tompítás nélkül kell leképezni magyarra.\n\n"
        "## Onomatopoeia & Hangutánzók\n"
        "A sóhajok, nyögések és indulatszavak (pl. Ah..., Ngh..., Mmm..., Haah..., Eek!) érzelmi pontozása (...), "
        "felkiáltójelei és elnyújtott magánhangzói pontosan megőrzendők. "
        "A csillagozott zörejek/cselekvések (pl. *gulp*, *pant*, *sigh*) kontextushoz illeszkedően cselekvésleíró formában adandók vissza "
        "(pl. *Nyel egyet*, *Liheg*, *Sóhajt*).\n\n"
        "## Punctuation & Rhythm\n"
        "Rövid, lüktető, dramaturgiai hatású mondatok. A gondolatjelek, három pontok és drámai szünetek szigorúan megőrzendők.\n"
    ),
    "Szoftver UI / Asztali alkalmazás": (
        "# Language style guide\n\n"
        "## Tone\n"
        "Professzionális, letisztult, közvetlen szoftveres felhasználói felület. Tömör és pontos megfogalmazások.\n\n"
        "## UI Actions & Buttons\n"
        "Gombok és menüparancsok esetén a magyar szoftveres standard a főnévi igenév / rövid főnévi alak "
        "(pl. Mentés, Megnyitás, Törlés, Bezárás, Mégse, Alkalmaz).\n\n"
        "## Terminology & Hotkeys\n"
        "A szabványos szoftveres terminológia használandó (File -> Fájl, Edit -> Szerkesztés, View -> Nézet, Settings/Preferences -> Beállítások). "
        "A billentyűparancsok (Ctrl+..., Alt+...) és a menü gyorsbillentyű-jelölők (&) megtartandók.\n\n"
        "## Punctuation\n"
        "Címkék, gombok és menüpontok végén nincs pont. Párbeszédpanelek kérdéseinél kérdőjel használandó.\n"
    ),
    "Szoftver Műszaki / Dokumentáció": (
        "# Language style guide\n\n"
        "## Tone\n"
        "Szakszerű, precíz, egyértelmű műszaki leírás. Kerüld a pongyola megfogalmazást.\n\n"
        "## Terminology\n"
        "Konzisztens műszaki és fejlesztői szakkifejezések. A beágyazott kódok, API hivatkozások és paraméterek érintetlenül hagyandók.\n\n"
        "## Structure\n"
        "Világos lépések és utasítások. E/2 vagy általános cselekvő forma (pl. \"Kattintson az X gombra\" vagy \"Kattints az X gombra\").\n"
    ),
    "Szoftver Eszköz / CLI & Fejlesztői": (
        "# Language style guide\n\n"
        "## Tone\n"
        "Tömör parancssori és diagnosztikai stílus. Hibakódok és technikai jelölők pontos megtartása.\n\n"
        "## Terminology\n"
        "Parancssori argumentumok, kapcsolók (--flag, -f) és környezeti változók soha nem fordítandók.\n\n"
        "## Logs & Errors\n"
        "A hibaüzenetek pontosak, a diagnosztikát segítők legyenek.\n"
    ),
}

DEFAULT_LANG_STYLE_HEADER = "# Language style guide\n"
