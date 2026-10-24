# Facts: demo_everyone_jumps

Every number the video shows or says, the real-world value with its source, and the second it becomes true. No
story line or HUD label may appear before its fact is true. The build prints the key moments (`build/build.log`,
the `[everyone]` lines) and writes them to `build/series.json` (`times`, `events`), so re-check them there after
any change.

**Rule of the episode:** everyone joins scale by scale (you, the square, the city, the country, the planet), then
all 8,300,678,395 people jump at once: lift-off at 26.9 s, a 0.44 m jump (0.60 s in the air), slowed to a near-freeze
in the air, touching down at 47.5 s. Pushing off moves the Earth the other way by
Δx = (people's mass ÷ Earth's mass) × jump height (the centre of mass of Earth plus people never moves), and landing
moves it back.

## Numbers and sources (checked: October 2026)

| Thing | Value used | Source | True at (s) |
|---|---|---|---|
| World population | 8,300,678,395 (8.3 billion) | UN DESA, World Population Prospects 2024, medium variant, 1 July 2026 (8,300,678,395; also listed by populationpyramid.net/world/2026) | always (the counter reaches it at 23.0) |
| The square | 25,235 people (2.2 per m², a dense standing crowd) plus 67,327 on the ring road and avenues | Exact instance counts from the build (`[plaza]` line in build.log); the counter is the number on screen | counted as they appear, 5.0-12.4 |
| The city | 2,113,705 people (counter value at 15.0 s, square and streets included) | Paris's population, INSEE 2022 census (2,113,705; 105 km²). The demo city is drawn Paris-sized (5.8 km radius) at Paris's spot on the globe, and is not named | 11.6-15.0 |
| The country | 66,400,000 | Metropolitan France, INSEE, 1 Jan 2025 (66.4 million of France's 68.6 million). The gold front spreads to 418 km, a circle the area of metropolitan France (~550,000 km²) | 15.5-19.0 |
| Average body mass, everyone | 50 kg | Adults average 62 kg (Walpole et al. 2012, "The weight of nations", BMC Public Health 12:439); about a quarter of people are children under 15 (UN WPP 2024) at roughly 20-25 kg, so ~52 kg overall; 50 kg rounds down. Cross-check: Bar-On, Phillips & Milo 2018 (PNAS) put human biomass at ~0.06 Gt of carbon, about 0.4 Gt wet mass | 31.0 |
| Weight in the air | 8,300,678,395 × 50 kg = 4.15 × 10¹¹ kg = 415 million tonnes ("about 400 million") | Derived | 31.0 |
| Jump | 0.44 m rise of the body, 0.60 s in the air | Projectile motion: airtime = 2√(2h/g) = 2√(0.88/9.81) = 0.60 s. A good standing jump; most people manage 0.3-0.5 m (0.49-0.64 s), so "half a second" holds | 26.9 (lift-off) |
| Earth's mass | 5.972 × 10²⁴ kg | NASA Earth Fact Sheet | 43.4 |
| Earth moves at most | 4.15 × 10¹¹ × 0.44 ÷ 5.972 × 10²⁴ = 3.06 × 10⁻¹⁴ m (HUD 0.000000000000030-031 m) | Momentum conservation (centre of mass fixed). "At most": spread round the globe, people push in different directions and partly cancel, so the real figure is smaller still | 35.0 (counts up to it by 38.4) |
| Width of an atom | ~1 × 10⁻¹⁰ m (hydrogen: 2 × Bohr radius = 1.06 × 10⁻¹⁰ m) | CODATA Bohr radius 5.29 × 10⁻¹¹ m. The push is ~3,500 times smaller | 39.3 |
| Earth vs everyone | 5.972 × 10²⁴ ÷ 4.15 × 10¹¹ = 1.44 × 10¹³ ("14 trillion times heavier") | Derived | 43.5 |
| Earth moves back | net change 0 m once everyone lands | Momentum conservation: with the people back on the ground, Earth is back where it was | 47.5 (landing) |
| End-card fact | the solid Earth rises and falls by up to about 20 cm, about twice a day | OpenStax Astronomy 2e, §4.6 "Ocean Tides and the Moon": "the tidal distortion of the solid Earth amounts—at its greatest—to only about 20 centimeters"; the dominant body tides are semi-diurnal | end card, 63.5 |

## Every line, checked at its start time

| Line | Starts (s) | On screen then | Check |
|---|---|---|---|
| It starts with you. | 3.1 | You alone in the empty square, bouncing; counter 1 "JUST YOU" | true (first person joins at 5.0) |
| Then everyone around you. | 5.1 | People appear round you; counter 6 → 9,292 | true |
| Then the whole square. | 8.1 | High shot, the square filling; counter 10,928 → 55,926 at 10.6 | true |
| Then the whole city. | 11.7 | Climb over the city; the streets fill out from the square, a gold wave at the front; counter 79,143 → 2,113,705 at 15.0 | true (fill starts 11.6) |
| Then the whole country. | 15.5 | From 160 km up, gold spreads from the city across the country; counter → 66,400,000 at 19.0 | true |
| Then all 8.3 billion people on Earth. | 19.3 | From orbit, gold spreads over the continents where people live; counter → 8,300,678,395 at 23.0 | true (the UN figure) |
| On three, everyone jumps. | 23.5 | Countdown on the HUD: 3 (23.6), 2 (24.8), 1 (26.0), JUMP! (26.9) | true |
| For half a second, nobody touches the ground. | 27.3 | Everyone in the air (slow motion); HUD "PEOPLE IN THE AIR 8,300,678,395", time in the air 0.20 s | true: all lifted off by 27.3; airtime 0.60 s |
| Together, you weigh about 400 million tonnes. | 31.1 | Crane over the frozen, airborne crowd; HUD "415,000,000 t" | true |
| Pushing off, you shove the planet the other way. | 35.1 | The Earth; HUD "EARTH MOVES AT MOST" counting up | true (Newton's third law) |
| It moves less than the width of an atom. | 39.3 | Your feet in the air over the stones; HUD 0.000000000000030 m vs "ONE ATOM: 0.0000000001 m" | true |
| Earth is 14 trillion times heavier than all of you. | 43.5 | The whole Earth; HUD "14 TRILLION : 1" | true |
| Then everyone lands at once. | 46.9 | The square; touchdown at 47.5 (impact, shake, flash); HUD in the air → 0 | true |
| And the planet moves right back. | 50.1 | The Earth; HUD "EARTH'S NET MOVE 0 m" | true (after 47.5) |
| Everyone is right back where they started. | 53.5 | Pull-up from you, cheering, to the city from 30 km | true (a straight-up jump lands where it took off) |
| And so is the Earth. | 58.5 | Pull-back from orbit to the whole planet; HUD "TOTAL EFFECT ON EARTH 0 m" | true |
