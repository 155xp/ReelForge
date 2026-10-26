// The mascot in an @opentui/react app:  bun react-example.tsx
// tsconfig.json needs "jsx": "react-jsx" and "jsxImportSource": "@opentui/react".
import { createCliRenderer } from "@opentui/core"
import { createRoot, extend, useKeyboard, useRenderer } from "@opentui/react"
import { useState } from "react"
import { MascotRenderable, type MascotAnimation } from "./reelforge-mascot"

declare module "@opentui/react" {
  interface OpenTUIComponents {
    reelforgeMascot: typeof MascotRenderable
  }
}

extend({ reelforgeMascot: MascotRenderable })

export function App() {
  const renderer = useRenderer()
  const [animation, setAnimation] = useState<MascotAnimation>("idle")

  useKeyboard((key) => {
    if (key.name === "r") setAnimation("forge")
    else if (key.name === "d") setAnimation("success")
    else if (key.name === "e") setAnimation("error")
    else if (key.name === "q") {
      renderer.destroy()
      process.exit(0)
    }
  })

  return (
    <box style={{ width: "100%", height: "100%", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      {/* success plays once, then onComplete drops back to idle */}
      <reelforgeMascot
        animation={animation}
        loop={animation !== "success"}
        onComplete={() => setAnimation("idle")}
      />
      <text fg="#8d8892">r render · d done · e error · q quit</text>
    </box>
  )
}

if (import.meta.main) {
  const renderer = await createCliRenderer({ exitOnCtrlC: true })
  createRoot(renderer).render(<App />)
}
