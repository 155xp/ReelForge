# Facts: demo_doubling_duck

Every number the video shows or says, the real-world value with its source, and the second it becomes true. No
story line or HUD label may appear before its fact is true. The build prints the same times (`build/build.log`,
the `[grow]` line) and writes them to `build/series.json` → `events`, so re-check them there after any change.

**Rule of the episode:** height H(t) = 6 in × 2^(t / 2), doubling every 2 s from t = 0: 6 in at 0 s, 1 ft at 2 s,
and 2^31 ft = 2,147,483,648 ft (654,553 km) at exactly 64.0 s, the moment the int32 counter (max 2,147,483,647)
overflows to −2,147,483,648. Time to reach a height h: t = 2 × log2(h / 0.1524 m).

## Numbers and sources (checked: October 2026)

| Thing | Value used | Source | True at (s) |
|---|---|---|---|
| Start size | 6 in (0.1524 m) tall | The scene's duck (a large bath duck; classic ones are 3.5-4 in, so no line claims a typical size) | 0.00 |
| Fire hydrant | 0.76 m (30 in) | The hydrant on the curb beside it (`worlds/street.py`); US dry-barrel hydrants stand about 2.5-3 ft above grade (manufacturers' spec sheets, e.g. Mueller Super Centurion) | 4.64 |
| You | 1.76 m, standing on a 0.15 m curb (1.91 m) | The person filming on the curb; average US adult man 1.75 m (CDC NHANES 2015-2018) | 7.30 |
| Car | SUV 4.8 m long, 1.9 m wide, 1.78 m tall | The SUV parked beside it; midsize SUVs are 4.6-5.0 m long (e.g. Toyota RAV4 4.6 m) | 9.95 |
| City bus | 12.2 m (40 ft) long, 3.35 m tall | The bus at its stop; 40 ft is the standard US transit bus length (FTA / APTA) | 12.64 |
| Main Street | 21 m between building fronts (2 travel lanes, 2 parking lanes, 4.5 m sidewalks) | The scene's street; the duck is 0.834 × its height wide, so wider from H = 25.2 m | 14.74 |
| Church steeple | 50 m to the cross | The church on the corner (`worlds/street.py`); tall New England steeples run 30-66 m (Park Street Church, Boston: 66 m) | 16.72 |
| Tallest building on Earth | 828 m | Burj Khalifa, CTBUH (Council on Tall Buildings and Urban Habitat) height to architectural top. The scene has a stand-in at true height on the horizon, tagged | 24.82 |
| Clouds | cumulus layer 1,300-1,900 m | The scene's cloud deck; fair-weather cumulus bases are typically 600-2,000 m (UK Met Office / WMO cloud atlas) | 26.12 (base), 27.24 (top) |
| 2 miles | 3,218.7 m | 1 mi = 1,609.344 m (exact, international mile) | 28.73 |
| Mount Everest | 8,848.86 m | 2020 China-Nepal joint survey. A stand-in peak at true height in the scene's range, tagged "EVEREST'S HEIGHT" | 31.65 |
| Airliner cruise | 35,000 ft (10,668 m) | Typical jet cruising altitudes 31,000-42,000 ft (FAA). The plane in the shot flies at 10,668 m | 32.19 |
| Black sky | camera at 70-170 km altitude | Above ~20 km the sky darkens to near-black; by 70 km it is black (NASA). Shown from 36.0 s | 36.0 (shot) |
| Edge of space | 100 km | Kármán line, as used by the FAI | 38.65 |
| Space station's orbit | 420 km | ISS orbits at roughly 400-420 km (NASA). The ring drawn round Earth is at 420 km | 42.79 |
| 1,000 miles | 1,609.3 km | 1 mi = 1,609.344 m | 46.66 |
| Moon's diameter | 3,474.8 km | NASA Moon Fact Sheet. The "MOON, TO SCALE" ghost beside it is 3,474.8 km wide | 48.89 |
| Earth's diameter | 12,742 km (mean), 12,756 km (equatorial) | NASA Earth Fact Sheet; the line waits for the larger value | 52.64 |
| Moon's distance | 384,400 km = 238,855 mi ≈ 239,000 mi | NASA Moon Fact Sheet (mean centre-to-centre). The scene's Moon is at exactly this distance | always |
| 20% of light speed | crown speed v = 1.01 × H × ln 2 / 2 (the crown, the duck's highest point, sits 1.01 × its height from the base point it grows from) ≥ 0.2 c (c = 299,792,458 m/s) | Derived from the rule | 60.13 |
| It hits the Moon | the crown reaches the Moon's near side | Scene geometry (the Moon is placed on the crown's path); the build prints `moon_hit` | 62.38 |
| It smashes the Moon | crown moving at 0.436 c at impact: giving the Moon (7.342 × 10^22 kg) that speed takes (γ − 1)Mc² ≈ 7.3 × 10^38 J, about 6 billion times the Moon's gravitational binding energy (≈ 1.24 × 10^29 J) | Moon mass: NASA fact sheet; binding energy: standard 3GM²/5R estimate | 62.38 |
| Overflow | int32 max 2,147,483,647, wraps to −2,147,483,648 | Two's-complement 32-bit integer; 2^31 ft is reached at exactly 64.0 s | 64.00 |

## Every line, checked at its start time

| Line | Starts (s) | Value then | Check |
|---|---|---|---|
| Your rubber duck doubles in size every 2 seconds. | 2.8 | 0.40 m (1 ft 4 in) | the rule; the HUD shows 1 FT at 2.0 s |
| Taller than a fire hydrant. | 5.1 | 0.90 m | > 0.76 m (from 4.64 s); hydrant tagged |
| Now it's taller than you. | 7.4 | 2.0 m | > 1.91 m incl. the curb (from 7.30 s); you tagged |
| Bigger than a car. | 10.1 | 5.05 m tall, 6.1 m long | > the SUV's 4.8 m length (from 9.95 s); car tagged |
| Bigger than a bus. | 12.8 | 12.9 m tall, 15.5 m long | > 12.2 m (from 12.64 s); bus tagged |
| Wider than Main Street. | 15.0 | 27.6 m tall, 23.0 m wide | > 21 m (from 14.74 s) |
| Taller than the church steeple. | 16.9 | 53.3 m | > 50 m (from 16.72 s); steeple tagged, it goes over at 17.6 s |
| Buildings can't stop it. | 18.6 | 96 m | buildings tipping and breaking on screen since 12.3 s |
| It's flattening Main Street. | 21.0 | 221 m | Main Street's buildings on screen going down round it |
| Taller than the tallest building on Earth. | 24.9 | 853 m | > 828 m (from 24.82 s); stand-in tagged 828 M |
| Its head is in the clouds. | 27.0 | 1,766 m | the head is inside the 1,300-1,900 m cloud layer (26.12-27.24 s) |
| It's now 2 miles tall. | 29.0 | 3,531 m | > 3,219 m (from 28.73 s); HUD sub reads 2 mi |
| Taller than Mount Everest. | 31.8 | 9,319 m | > 8,849 m (from 31.65 s); peak tagged |
| Planes have to fly around it. | 33.6 | 17,390 m | > 10,668 m cruise (from 32.19 s); airliner tagged, banking past it |
| Up there, the sky is black. | 36.3 | 44 km | camera at 70+ km, black sky on screen |
| Its head just reached space. | 38.8 | 105 km | > 100 km (from 38.65 s) |
| Taller than the space station's orbit. | 42.9 | 437 km | > 420 km (from 42.79 s); orbit ring tagged |
| It's over 1,000 miles tall. | 46.8 | 1,687 km | > 1,609 km (from 46.66 s); HUD sub reads 1,048 mi |
| Bigger than the Moon. | 49.0 | 3,616 km | > 3,474.8 km (from 48.89 s); Moon to scale beside it, tagged |
| Now it's bigger than Earth. | 52.8 | 13,495 km | > 12,756 km (from 52.64 s); it sits on the Earth, tagged |
| Earth is a ball under its feet. | 55.0 | 28,900 km | Earth on screen under its base |
| The Moon is 239,000 miles away. | 57.0 | 57,900 km | 384,400 km = 238,855 mi; the Moon tagged 384,400 KM AWAY |
| Its head is moving at 20% of light speed. | 60.3 | crown at 0.212 c | ≥ 0.2 c (from 60.13 s) |
| It just smashed the Moon. | 62.45 | crown at 0.44 c | impact at 62.38 s, the Moon shatters on screen |
| Integer overflow. | 64.0 | 2^31 ft | the counter wraps to −2,147,483,648 at 64.0 s |

HUD: "RUBBER DUCK" with the height in inches (0-2 s), then in feet; sub-lines "DOUBLES EVERY 2 SECONDS" (2-26.8 s),
"{miles} TALL" from 26.8 s (1 mile at 26.75 s), "{n} EARTHS TALL" from 52.64 s, "MOON: DESTROYED" from 62.38 s,
"MAX 2,147,483,647" from 63.3 s, "-2,147,483,648 FT / INTEGER OVERFLOW" in red from 64.0 s.
