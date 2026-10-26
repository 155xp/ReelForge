// Preview every animation in your terminal:  bun demo.ts   (add --cycle to step through them on a timer)
// ← → switch · 1-9 jump · space pause · f fit · s scale · q quit
import { BoxRenderable, TextRenderable, createCliRenderer } from "@opentui/core"
import { MASCOT_ANIMATIONS, MascotRenderable } from "./reelforge-mascot"

const renderer = await createCliRenderer({ exitOnCtrlC: true, targetFps: 30 })

const stage = new BoxRenderable(renderer, {
  id: "stage",
  width: "100%",
  height: "100%",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
})
const mascot = new MascotRenderable(renderer, { id: "mascot" })
const label = new TextRenderable(renderer, { id: "label", fg: "#8d8892", marginTop: 1 })
stage.add(mascot)
stage.add(label)
renderer.root.add(stage)

let index = 0

function show(i: number) {
  index = (i + MASCOT_ANIMATIONS.length) % MASCOT_ANIMATIONS.length
  mascot.play(MASCOT_ANIMATIONS[index]!)
  refresh()
}

function refresh() {
  const name = MASCOT_ANIMATIONS[index]
  const state = mascot.playing ? "" : " (paused)"
  label.content =
    `${index + 1}/${MASCOT_ANIMATIONS.length} ${name}${state}   ` +
    `← → switch · space pause · f fit: ${mascot.fit} · s scale: ${mascot.scale} · q quit`
}

renderer.keyInput.on("keypress", (key) => {
  if (key.name === "right") show(index + 1)
  else if (key.name === "left") show(index - 1)
  else if (/^[1-9]$/.test(key.name)) show(Number(key.name) - 1)
  else if (key.name === "space") mascot.playing = !mascot.playing
  else if (key.name === "f") mascot.fit = mascot.fit === "canvas" ? "animation" : "canvas"
  else if (key.name === "s") mascot.scale = mascot.scale === 1 ? 2 : 1
  else if (key.name === "q") {
    renderer.destroy()
    process.exit(0)
  }
  refresh()
})

show(0)
if (process.argv.includes("--cycle")) setInterval(() => show(index + 1), 4000)
