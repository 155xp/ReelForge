"""Proven short-form formats onboarding offers, each with its beats, ending and starter ideas.

Numbers in `proof` come from a scan of the what-if / simulation niche on TikTok in October 2026. Formats move
fast: the AI is told to re-check what is working before it picks subjects.
"""

from __future__ import annotations

FORMATS: dict[str, dict] = {
    "doubling": {
        "label": "What if X doubled every 2 seconds?",
        "short": "Doubling",
        "series": "Doubling",
        "premise": ("Something everyday doubles every 2 seconds (speed, size, height, money, followers...). The "
                    "number climbs past real, checkable milestones until it breaks the world."),
        "twist": ("The counter reaches 2,147,483,647, overflows to -2,147,483,648 (a real integer-overflow bug), "
                  "the world glitches, and the video rewinds into its own first frame so it loops forever."),
        "ending": "overflow_rewind",
        "hud": True,
        "loop": True,
        "length": "61-75 s",
        "proof": ("Doubling series took off in October 2026: a car speed-doubling video hit 3.5M views and a copy "
                  "from an 895-follower account hit 440K within two days, so the format carries new accounts."),
        "beats": [
            ("0-2 s", "Hook: the title question over a normal scene that is already moving; the counter is on screen."),
            ("2-15 s", "The rule starts. Small, relatable milestones (walking pace, a bike, a bus...)."),
            ("15-35 s", "It gets dangerous: records broken, buildings, the sound barrier, the clouds."),
            ("35-55 s", "Planet scale: space, the Moon, the Earth from far away. The biggest spectacle builds."),
            ("55-64 s", "Beyond reality: the speed of light, the Sun, the galaxy. The counter nears its limit."),
            ("64 s", "Overflow: 2,147,483,647 -> -2,147,483,648, red glitch, everything breaks."),
            ("64-67 s", "Rewind into the first frame with FOLLOW FOR MORE over it; the video loops."),
        ],
        "examples": [
            "What if your coffee doubled in size every 2 seconds?",
            "What if every jump went twice as high?",
            "What if your phone's battery doubled every second?",
        ],
        "subjects": ["a jump's height", "a snowball rolling downhill", "an ant colony", "a sound's loudness",
                     "a domino's size", "a pizza's size", "a paper fold's thickness", "a raindrop's size"],
        "tags": ["whatif", "physics", "space", "simulation"],
        "built_in": True,
    },
    "disappear": {
        "label": "What if X disappeared for 5 seconds?",
        "short": "Disappear for 5 seconds",
        "series": "Gone for 5 Seconds",
        "premise": ("One thing we take for granted (friction, oxygen, the Moon, electrons, plastic...) vanishes for "
                    "a few seconds. The consequences cascade in slow motion, then it comes back, or doesn't."),
        "twist": "A countdown runs on screen; the last second shows the one consequence nobody expected.",
        "ending": "countdown_payoff",
        "hud": True,
        "loop": False,
        "length": "61-80 s",
        "proof": ("The single biggest hits of the niche in October 2026 (16.5M and 12.4M views). Popular subjects "
                  "are now saturated, so pick fresh ones and make them more visual than the rest."),
        "beats": [
            ("0-3 s", "Hook: the question over an ordinary scene; the timer reads 5.0."),
            ("3-10 s", "Put the viewer in the scene: where you are, what's around you."),
            ("10-50 s", "It vanishes. Each line is a worse, real consequence, shown on screen."),
            ("50-70 s", "The biggest consequence: planet scale or deeply personal."),
            ("70-80 s", "It returns (or doesn't), and an end card with one real fact."),
        ],
        "examples": ["What if friction disappeared for 5 seconds?", "What if the Moon disappeared for 5 seconds?"],
        "subjects": ["friction", "the Moon", "Earth's magnetic field", "all the bridges", "colour", "the internet"],
        "tags": ["whatif", "science", "simulation", "physics"],
        "built_in": False,
    },
    "disaster_pov": {
        "label": "What if <disaster> hit your city? (POV)",
        "short": "Disaster POV",
        "series": "POV",
        "premise": ("A fixed 'you are here' viewpoint (balcony, rooftop, car seat). A disaster approaches; a ticking "
                    "on-screen number counts toward it while short second-person lines tell the story."),
        "twist": "The counter's label becomes <THREAT> / HERE at the climax, then an end card with one true fact.",
        "ending": "end_card_fact",
        "hud": True,
        "loop": False,
        "length": "75-80 s",
        "proof": ("Planet-scale questions everyone has wondered about did 10-30M views for the format's originators "
                  "in October 2026; local disasters 2-3M; repeats and pure fiction fell off hard."),
        "beats": [
            ("0-5 s", "Title card over a calm, populated scene; the counter already shows the key number."),
            ("5-13 s", "Put 'you' in the scene with 2-3 short lines."),
            ("13-20 s", "The trigger: the event starts and the number begins to move."),
            ("20-55 s", "Escalation: a new line every 3-6 s, each one worse; the light and colour shift."),
            ("55-70 s", "The threat arrives: the label switches to <THREAT> / HERE; the camera is hit."),
            ("70-80 s", "Fade to black, then an end card: the question and one real fact."),
        ],
        "examples": ["What if the Earth stopped spinning?", "What if a tsunami hit your city?"],
        "subjects": ["a solar flare", "a supervolcano", "a rogue black hole", "the Moon getting closer"],
        "tags": ["whatif", "pov", "space", "disaster"],
        "built_in": True,
    },
    "everyone": {
        "label": "What if everyone on Earth did X at once?",
        "short": "Everyone at once",
        "series": "Everyone At Once",
        "premise": ("All 8 billion people do one thing at the same moment (jump, clap, flush, look up...). The "
                    "scale climbs from one street to the whole planet with real numbers."),
        "twist": "The final shot pulls back to the whole planet, and a counter totals the effect.",
        "ending": "end_card_fact",
        "hud": True,
        "loop": False,
        "length": "61-75 s",
        "proof": "Audience-request driven; 0.3-2M views per video in October 2026, with strong comments.",
        "beats": [
            ("0-3 s", "Hook: the question, one person about to do it."),
            ("3-20 s", "A street, a city, a country join in; the counter shows how many."),
            ("20-55 s", "Real, measurable consequences, each one bigger."),
            ("55-75 s", "The whole planet; the surprising true answer; end card."),
        ],
        "examples": ["What if everyone on Earth jumped at once?", "What if everyone flushed at the same time?"],
        "subjects": ["jumped at once", "screamed at once", "turned on a light", "looked at the Moon"],
        "tags": ["whatif", "science", "earth", "simulation"],
        "built_in": True,
    },
    "reality_bug": {
        "label": "What if reality had a bug? (one game setting broken)",
        "short": "Reality bugs",
        "series": "Reality Bugs",
        "premise": ("The real world, but one game-engine setting is wrong: render distance, collision off, 5 FPS, "
                    "gravity off, lag, out of memory. It escalates until the bug reaches you."),
        "twist": "A debug-console counter (monospace, like a dev console) ticks in chapters; the last value is YOU.",
        "ending": "end_card_fact",
        "hud": True,
        "loop": False,
        "length": "61-80 s",
        "proof": "Taps the gaming audience the what-if simulation niche already reaches; fewer copycats so far.",
        "beats": [
            ("0-3 s", "Hook: the question over an ordinary street; the debug counter is on."),
            ("3-15 s", "The setting starts to slip: small, uncanny glitches."),
            ("15-55 s", "It spreads: pop-in, missing textures, clipping, frame drops, each bigger."),
            ("55-70 s", "It reaches you: the counter's last value is YOU, hard glitch cut."),
            ("70-80 s", "End card: the question and one real fact."),
        ],
        "examples": ["What if reality had a render distance?", "What if the world dropped to 5 FPS?"],
        "subjects": ["collision detection failing", "5 FPS", "gravity turned off for 10 seconds", "lag"],
        "tags": ["whatif", "gaming", "glitch", "simulation"],
        "built_in": False,
    },
    "custom": {
        "label": "My own format (describe it)",
        "short": "Custom",
        "series": "",
        "premise": "",
        "twist": "",
        "ending": "custom",
        "hud": True,
        "loop": False,
        "length": "61-75 s",
        "proof": "",
        "beats": [
            ("0-2 s", "Hook: the question or promise lands immediately over something already moving."),
            ("2-50 s", "Escalation: something new every 2-3 s, each beat bigger than the last."),
            ("last 20 s", "The most spectacular part, then the payoff and the follow ending."),
        ],
        "examples": [],
        "subjects": [],
        "tags": ["fyp"],
        "built_in": False,
    },
}

ENDINGS = {
    "overflow_rewind": "Counter overflow (2,147,483,647 -> -2,147,483,648), glitch, then a rewind into the first frame "
                       "(`rewind` + `loop_to_start`) so the video loops seamlessly.",
    "countdown_payoff": "The countdown hits zero on the biggest consequence, then a short end card with one real fact.",
    "end_card_fact": "Fade to black, then an end card with the question and one real fact (`blackout` + `end_card`).",
    "custom": "As described in the format notes.",
}

STYLES = {
    "cinematic": "Cinematic 3D: realistic light, rich colour, depth, haze only where it helps",
    "lowpoly": "Stylized low-poly game look: clean shapes, bold colour, readable at a glance",
    "neon": "Neon night: dark scenes, glowing signs and screens, high contrast",
    "minimal": "Clean minimal: simple shapes on calm backgrounds, one strong accent colour",
    "custom": "My own look (describe it)",
}

TONES = ["awe", "suspense", "funny", "satisfying", "educational", "eerie", "hype"]
