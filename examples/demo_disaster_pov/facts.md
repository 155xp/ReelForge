# Facts: demo_disaster_pov

Every number the video shows or says, the real-world value with its source, and the second it becomes true. No
story line or HUD label may appear before its fact is true.

**Rule of the episode:** a stony asteroid about 100 m across (density ~3,000 kg/m³) enters at 18 km/s on a shallow
13.6° path, starts to glow 100 km up and explodes 7.5 km up, 23 km (over the ground) from your balcony: 24.2 km in a
straight line, 15.0 miles. Its energy, ½mv² = ½ × 1.57 × 10⁹ kg × (18 km/s)², is 2.5 × 10¹⁷ J = 61 megatons of TNT.
The blast wave's speed at slant range R is U = c₀ √(1 + 6/7 · Δp/p₀) (Rankine-Hugoniot, γ = 1.4, c₀ = 343 m/s), with
the free-air overpressure Δp from the Kinney-Graham fit for 61 Mt. Integrating dR/U over the 24.2 km gives the arrival
**46.7 s after the burst** (a sound wave alone would take 70.5 s). All of it is computed by
`pipeline/blender/effects/approach.py` (meteor) and printed in the build log:
`times appear 0.00, flash 21.80, quake 32.38, mountains 59.15, downtown 62.56, arrive 68.50`.

## Numbers and sources (checked: October 2026)

| Thing | Value used | Source | True at (s) |
|---|---|---|---|
| Meteor altitude (HUD) | 62.1 mi at 0 s, 4.9 mi at 21.7 s (100 km → 7.5 km along the straight path) | the scenario; bright fireballs start to glow ~100 km up (NASA Meteor FAQ, science.nasa.gov) | 0-21.8 |
| Meteor speed (HUD) | 40,265 mph = 18 km/s | asteroids hit the air at 11-72 km/s, typically ~17-20 km/s (NASA CNEOS fireball data, cneos.jpl.nasa.gov/fireballs); Chelyabinsk 19 km/s (Popova et al. 2013, *Science* 342) | 0-21.8 |
| "Barely moving" | it crosses 1.3° of sky in its first 15.7 s (0.6° during the line); a typical meteor crosses tens of degrees in a second or two | geometry: an object on a near-collision course keeps nearly the same bearing (constant bearing, decreasing range) | 0-19.4 |
| Brighter than the Sun | the meteor's light outshines the sun lamp from ~20 s; the street lights up from in front | Chelyabinsk's 20 m asteroid peaked at ~30× the Sun's brightness (Brown et al. 2013, *Nature* 503) | 20.3 |
| Airburst | explodes 7.5 km up, before reaching the ground | Tunguska's object burst 5-10 km up (Boslough & Crawford 2008, *Int. J. Impact Eng.* 35; NASA "The Tunguska Impact—100 Years Later", 2008) | 21.8 |
| Energy | 61 Mt | ½mv² for 100 m, 3,000 kg/m³, 18 km/s | 21.8 |
| Fires from the flash | 25-250 cal/cm² at 24.2 km (3-30 % of the energy as light, before the air absorbs some) | dry wood, paper and fabric ignite at ~5-20 cal/cm² in a megaton-scale pulse (Glasstone & Dolan, *The Effects of Nuclear Weapons*, 1977, ch. 7) | 22.45 (first fire) |
| People run, cars brake | people stop to look at 9 s, run from 24-27 s; traffic brakes to a stop at 23-26 s | the scenario | 24 |
| Silence | no sound from the explosion reaches you before 68.5 s: the blast is the first thing you hear | sound travels at 343 m/s; the shock front is never slower | 21.8-68.5 |
| Ground shakes first | the blast reaches ground zero at 28.5 s; seismic P waves cross the 23 km of rock at ~6 km/s: 32.4 s. Lamps and trees rock for a few seconds | P-wave speed in the crust ~6 km/s (USGS); Tunguska registered on seismographs as far as Irkutsk | 32.38 |
| Transformers blowing | blue-white flashes on rooftops at 33.9-54.1 s | fires and ground shaking short out power equipment (common in disasters); shown, not claimed in a line | 33.9 |
| Blast wave distance (HUD) | 15.0 mi at 21.8 s, falling to 0 at 68.5 s (slant distance still to travel) | Kinney & Graham, *Explosive Shocks in Air* (2nd ed., 1985), with U(R) above | 21.8-68.5 |
| Blast wave speed (HUD) | 1,013 → 961 mph during "about 1,000 mph" (36.4-39.8 s); 831 mph when it hits you | same | 36.4 |
| Overpressure at you | ~3.0 psi free-air; reflected along the ground (Mach stem) roughly 5-6 psi | Kinney-Graham; Glasstone & Dolan ch. 3 (Mach reflection) | 68.5 |
| Windows burst | window glass fails at ~0.5-1 psi, so every window near you goes as the front reaches it (67.6-68.5 s) | Glasstone & Dolan ch. 5; FEMA blast damage tables | 67.6 |
| Buildings collapse, you are thrown | at ~5 psi most residential buildings collapse; winds behind a 3-5 psi front are ~100-160 mph, enough to throw a person | Glasstone & Dolan, Table 3.07 and ch. 5, 12 | 59 onward (first hit), 68.5 |
| The dust wall | a bank of dust rides ~100 m (0.3 s) behind the shock, lifted by that wind; 1.3 km tall, so it shows over the mountains from ~56 s | modelled; the shock itself is invisible, the dust marks it | 56.4 |
| Mushroom cloud | rises from 7.5 km to 13 km in 46 s, still rising at 44-47 s | modelled on the rise of megaton-scale fireballs (~100 m/s, Glasstone & Dolan ch. 2) | 43.7 |
| Downtown hit | the towers are reached at 62.6 s (median), gone into the dust by 63.4 s (checked in stills) | the scenario | 63.4 |
| End-card fact | 30 June 1908: an airburst over the Podkamennaya Tunguska river, Siberia, flattened ~80 million trees over ~2,150 km² | NASA (2008, above); *Britannica*, "Tunguska event" | end card |

## Every line, checked at its start time

| Line | Starts (s) | Value then | Check |
|---|---|---|---|
| You're on your balcony. It's a normal afternoon. | 4.9 | you look down at the avenue: railing, mug, traffic and people moving, sun 22° up | ✓ visible |
| There's a new star in the sky. In daylight. | 8.6 | you look up at it: a glaring point over the mountains (it has been there since frame 1) | ✓ visible |
| It's barely moving. It's just getting bigger. | 12.3 | 0.6° of motion during the line, the camera zooms in on it; its glow grows | ✓ |
| That means it's heading this way. | 16.0 | its track is 10° off your line of sight and ends 23 km away | ✓ |
| Now it's brighter than the Sun. | 20.3 | flare at 20.4 s; its light outshines the sun lamp; the street lights up | ✓ visible |
| It exploded in the sky before it could land. | 22.6 | you look back after the flash: fireball 4.7 mi up (the HUD read 4.9 mi at 21.7 s) | ✓ visible |
| The heat from the flash started fires. | 26.1 | you turn left to a burning building nearby; 7 fires lit by 26.1 s | ✓ visible |
| People are running. You haven't heard it yet. | 29.8 | people running along the pavements since 24-27 s; HUD "HITS IN 38.7 s" | ✓ visible |
| The ground shook first. The blast is still miles away. | 32.6 | the camera shakes from 32.38 s, lamps rock; HUD 9.0 mi | ✓ visible |
| It's moving at about 1,000 miles per hour. | 36.4 | HUD 1,013 → 961 MPH | ✓ on the HUD |
| Now there are fires everywhere. | 40.2 | you turn right: fires on that side too; sparks on the roofs | ✓ visible |
| The cloud is still rising. | 43.7 | cloud top 11.9 → 12.2 km, rising | ✓ visible |
| Every car on the street has stopped. | 47.0 | you look down: the traffic braked to a stop at 23-26 s | ✓ visible |
| It's about 4 miles away. You still can't see it. | 50.4 | HUD 4.3 → 3.6 mi; the dust is still behind the mountains (stills at 49, 51, 53 s) | ✓ |
| Then the horizon turns brown. | 53.6 | the first billows show behind the mountains (stills 53.5-55 s) | ✓ visible |
| There it is. That wall of dust is the blast wave. | 56.4 | the dust bank over the mountains (stills 56-59 s); HUD 2.8 mi | ✓ visible |
| It's swallowing the city. | 59.8 | the bank crosses the far city (stills 59-63 s) | ✓ visible |
| Downtown is gone. | 63.4 | you look at downtown: hit at 62.6 s, gone into the dust (stills 63-64.2 s) | ✓ visible |
| Here it comes. | 65.9 | HUD 0.6 mi → 0.3 mi | ✓ visible |
| The windows are bursting. | 67.5 | the near buildings' windows burst outward floor by floor at 67.6-68.5 s | ✓ visible |
| HUD "BLAST WAVE / HERE" | 68.5 | arrival 68.50 s: you are thrown back, debris and glass fly past, the dust takes everything (68.8 s) | ✓ |
