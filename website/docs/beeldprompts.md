# Beeldprompts en assetregister — Depiqo website V4

De website heeft 17 fotoplekken. Zolang er geen beeld is, toont de site een lichte placeholder. Zet je een beeld in `assets/img/` met de juiste bestandsnaam, dan gebruikt de build het automatisch, met de juiste afmetingen en lazy loading.

## Werkwijze

1. Plak eerst de **stijlprompt** in ChatGPT (beeldgeneratie) of Midjourney, daarna per beeld de **beeldprompt**.
2. Genereer 3 à 4 varianten per plek en kies de meest natuurlijke. Let vooral op handen, gezichten, tekst op de achtergrond en vreemde objecten.
3. Sla het gekozen beeld op als `assets/img/<slot>.jpg` (of `.webp`), minimaal in de aangegeven pixelmaat. Comprimeer tot onder de 250 kB (bijvoorbeeld met Squoosh, kwaliteit 75–80).
4. Draai `python3 src/build.py` en `python3 src/build.py preview`.
5. Vul het assetregister onderaan in: bron, datum, gebruiksrecht.

Controleer bij de gekozen tool of je de beelden commercieel mag gebruiken. Gebruik geen beelden van herkenbare echte personen, geen logo's en geen bestaande gebouwen met naam.

## Stijlprompt (eerst plakken)

```
You are creating a consistent set of editorial lifestyle photographs for a European fintech brand about rental deposits.
Style for every image:
- Natural daylight, soft and warm, as in a premium European interior or lifestyle magazine. Slightly warm white balance.
- Real, ordinary people aged 22 to 60, diverse but natural, dressed casually or business casual. Candid moments, not posing, not looking into the camera.
- Realistic, modern but lived-in Dutch and Belgian city homes and offices: canal houses, brick apartment buildings, Antwerp or Ghent townhouses, wooden floors, white walls, plants, linen, oak.
- Colour palette: warm off-white, sand, light oak, with small accents of deep navy and teal green. No saturated colours.
- Composition: simple, calm, plenty of negative space on one side for overlaid interface cards. Shallow depth of field.
- Photographic realism: 35mm or 50mm lens look, subtle film grain, no HDR, no glossy CGI look.
Avoid: stock-photo smiles, handshakes in meeting rooms, piles of money, coins, crypto symbols, luxury villas, American suburbs, perfect showroom interiors, text, logos, watermarks, signs with words, distorted hands or faces.
```

## Beeldprompts

| Slot (bestandsnaam) | Waar | Verhouding | Minimale maat |
|---|---|---|---|
| hero-nieuwe-woning | Homepage hero | 4:5 staand | 1200 × 1500 |
| aud-huurder | Homepage, kaart huurders | 4:3 | 1200 × 900 |
| aud-verhuurder | Homepage, kaart verhuurders | 4:3 | 1200 × 900 |
| aud-makelaar | Homepage, kaart makelaars | 4:3 | 1200 × 900 |
| aud-beheerder | Homepage, kaart beheerders | 4:3 | 1200 × 900 |
| huurder-woonkamer | Homepage, sectie huurders | 4:5 staand | 1200 × 1500 |
| team-overleg | Homepage demo en pilotpagina | 3:2 | 1500 × 1000 |
| hoe-huurder-verhuurder | Hoe het werkt | 4:3 | 1600 × 1200 |
| huurder-verhuisdozen | Huurders | 4:3 | 1600 × 1200 |
| verhuurder-inspectie | Verhuurders | 4:3 | 1600 × 1200 |
| makelaar-sleutels | Makelaars / Immokantoren | 4:3 | 1600 × 1200 |
| beheerder-laptop | Vastgoedbeheerders | 4:3 | 1600 × 1200 |
| institutioneel-gebouw | Woningcorporaties / Institutionele verhuurders | 4:3 | 1600 × 1200 |
| bank-overleg | Banken | 4:3 | 1600 × 1200 |
| verzekeraar-gesprek | Verzekeraars | 4:3 | 1600 × 1200 |
| beleggen-telefoon | Beleggingsplatformen | 4:3 | 1600 × 1200 |
| software-team | Software en API | 4:3 | 1600 × 1200 |

Laat bij de staande beelden (hero, huurder-woonkamer) de **linkeronderhoek rustig**: daar komt een walletkaart overheen. Bij de hero ook de **rechterbovenhoek**.

### hero-nieuwe-woning — 4:5
```
A young couple in their late twenties standing in the doorway of their new rental apartment in an Amsterdam canal house, the woman holding a set of keys, both looking into the bright empty living room with tall windows and wooden floor, a few moving boxes on the floor. Warm morning light. Calm, hopeful moment. Keep the lower-left and upper-right areas visually quiet. Vertical 4:5.
```

### aud-huurder — 4:3
```
A young woman carrying a cardboard moving box into a bright, small apartment with white walls and oak floor, seen slightly from the side, plants on the windowsill, daylight. Candid, relaxed. 4:3.
```

### aud-verhuurder — 4:3
```
A woman in her fifties sitting at a wooden dining table in a renovated Ghent townhouse, reading through a few printed documents with a pen, a laptop closed beside her, a cup of tea, soft window light. Thoughtful, in control. 4:3.
```

### aud-makelaar — 4:3
```
A rental agent in business casual handing a key to a new tenant in the stairwell of a Dutch brick apartment building, focus on the hands and the key, faces partly out of frame, warm daylight from a window. 4:3.
```

### aud-beheerder — 4:3
```
A property manager in her forties working on a laptop in a light, modern office with plants and a large window, a second colleague out of focus in the background, natural light, calm and organised. Screen not readable. 4:3.
```

### huurder-woonkamer — 4:5
```
A man in his early thirties sitting relaxed on a linen sofa in a bright living room of a rental apartment, looking at his smartphone with a slight smile, morning light, plants and a few books, oak floor. Screen not visible. Keep the lower-left area visually quiet. Vertical 4:5.
```

### team-overleg — 3:2
```
Two colleagues of a small real-estate office, a woman and a man in their thirties, discussing something on a laptop at a wooden table in a bright office with a view on a European city street, coffee cups, natural light, candid. 3:2.
```

### hoe-huurder-verhuurder — 4:3
```
A tenant and a landlord talking in the kitchen of a renovated apartment, standing at a kitchen island, the landlord holding a tablet, friendly and practical conversation, daylight, Belgian or Dutch interior. 4:3.
```

### huurder-verhuisdozen — 4:3
```
A young couple unpacking moving boxes on the floor of their new rental apartment, sitting among the boxes, laughing, a plant and a lamp still wrapped, large window with soft daylight, white walls. 4:3.
```

### verhuurder-inspectie — 4:3
```
A landlord and a departing tenant walking through an empty, clean apartment during the final inspection, the landlord taking a photo of a wall with a phone, neutral friendly atmosphere, daylight on wooden floor. 4:3.
```

### makelaar-sleutels — 4:3
```
A real-estate agent at the open front door of an Antwerp townhouse handing keys to a young tenant, seen from inside the hallway, warm afternoon light, tiled floor, plants. Faces natural, not looking into camera. 4:3.
```

### beheerder-laptop — 4:3
```
A property manager in his fifties at a standing desk in a light office, reviewing a list on a laptop, reading glasses, a colleague on the phone in the background, plants, soft daylight. Screen not readable. 4:3.
```

### institutioneel-gebouw — 4:3
```
A modern mid-rise residential building with balconies and brick facade in a Dutch or Belgian city, residents on a few balconies, bicycles in front, trees, late afternoon light, realistic architecture, no signage. 4:3.
```

### bank-overleg — 4:3
```
Two financial professionals, a woman and a man in their forties, in a bright modern office meeting space, discussing a printed architecture diagram on the table, laptops open, glass and wood, natural light, calm and serious. No logos. 4:3.
```

### verzekeraar-gesprek — 4:3
```
An advisor and a young client at a round table in a light office, going through a document together, the advisor pointing at a page, friendly and clear, natural daylight, plants. No logos. 4:3.
```

### beleggen-telefoon — 4:3
```
A young tenant at a kitchen table in the morning, holding a smartphone and a cup of coffee, looking at the screen thoughtfully, bright rental apartment, plants, soft light. Screen not visible. 4:3.
```

### software-team — 4:3
```
A small software team of three people collaborating in front of a large monitor showing abstract interface blocks (no readable text), bright office with plants and wood, one person pointing at the screen, casual clothes. 4:3.
```

## Assetregister

Vul in zodra een beeld definitief is. Niet live zetten zolang de kolom "Gebruiksrecht" leeg is.

| Slot | Bestand | Bron (tool, fotograaf of bank) | Datum | Gebruiksrecht / licentie | Alt-tekst gecontroleerd |
|---|---|---|---|---|---|
| hero-nieuwe-woning | assets/img/hero-nieuwe-woning.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| aud-huurder | assets/img/aud-huurder.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| aud-verhuurder | assets/img/aud-verhuurder.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| aud-makelaar | assets/img/aud-makelaar.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| aud-beheerder | assets/img/aud-beheerder.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| huurder-woonkamer | assets/img/huurder-woonkamer.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| team-overleg | assets/img/team-overleg.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| hoe-huurder-verhuurder | assets/img/hoe-huurder-verhuurder.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| huurder-verhuisdozen | assets/img/huurder-verhuisdozen.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| verhuurder-inspectie | assets/img/verhuurder-inspectie.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| makelaar-sleutels | assets/img/makelaar-sleutels.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| beheerder-laptop | assets/img/beheerder-laptop.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| institutioneel-gebouw | assets/img/institutioneel-gebouw.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| bank-overleg | assets/img/bank-overleg.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| verzekeraar-gesprek | assets/img/verzekeraar-gesprek.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| beleggen-telefoon | assets/img/beleggen-telefoon.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |
| software-team | assets/img/software-team.webp | AI-gegenereerd, aangeleverd door Kevin | 19-10-2026 | Te bevestigen: voorwaarden van de gebruikte beeldtool | Ja, aangepast aan het beeld |

De alt-teksten staan in de code bij elke foto (`src/home.py`, `src/audiences.py`, `src/pages.py`). Pas ze aan als het gekozen beeld anders is dan de briefing.
