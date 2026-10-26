import { Renderable, RGBA, type OptimizedBuffer, type RenderContext, type RenderableOptions } from "@opentui/core"
import { ANIMATIONS, CHARS, FRAMES, MASCOT_HEIGHT, MASCOT_WIDTH, PALETTE, ROWS, type MascotAnimation } from "./reelforge-frames"

export { ANIMATIONS, type MascotAnimation } from "./reelforge-frames"

/** Every animation name, in the order the GIFs are listed. */
export const MASCOT_ANIMATIONS = Object.keys(ANIMATIONS) as MascotAnimation[]

export type MascotFit = "canvas" | "animation"

export interface MascotOptions extends RenderableOptions<MascotRenderable> {
  /** Animation to show. Default "idle". */
  animation?: MascotAnimation
  /** Start playing immediately. Default true. */
  playing?: boolean
  /** Playback rate: 2 is twice as fast. Default 1. */
  speed?: number
  /** Repeat forever. When false the last frame is held and onComplete fires. Default true. */
  loop?: boolean
  /**
   * "canvas" (default): every animation is the same size (43x18 cells at scale 1),
   * so switching animations never moves anything around.
   * "animation": shrink to what the current animation draws (the idle pose is 35x11).
   */
  fit?: MascotFit
  /** 1 (default): one pixel per column, two per row, drawn with ▀ ▄. 2: every pixel is two columns by one row. */
  scale?: 1 | 2
  /** Called when a non-looping animation reaches its last frame. */
  onComplete?: (animation: MascotAnimation) => void
}

const FULL = { x: 0, y: 0, width: MASCOT_WIDTH, height: MASCOT_HEIGHT }

// Decode the frames once: one palette index per pixel, 0 meaning transparent.
const PIXELS = FRAMES.map((rowIds) => {
  const px = new Uint8Array(MASCOT_WIDTH * MASCOT_HEIGHT)
  rowIds.forEach((id, y) => {
    const row = ROWS[id]!
    for (let x = 0; x < MASCOT_WIDTH; x++) {
      if (row[x] !== ".") px[y * MASCOT_WIDTH + x] = CHARS.indexOf(row[x]!) + 1
    }
  })
  return px
})
const COLORS = [RGBA.fromValues(0, 0, 0, 0), ...PALETTE.map((hex) => RGBA.fromHex(hex))]
const CLEAR = COLORS[0]!

function cellSize(animation: MascotAnimation, fit: MascotFit, scale: 1 | 2) {
  const b = fit === "animation" ? ANIMATIONS[animation].bounds : FULL
  return scale === 2 ? { width: b.width * 2, height: b.height } : { width: b.width, height: Math.ceil(b.height / 2) }
}

/**
 * The ReelForge anvil, animated with half-block characters, so it works in any
 * truecolor terminal without image protocols. Transparent pixels keep whatever
 * is behind the mascot.
 *
 *   const mascot = new MascotRenderable(renderer, { animation: "forge" })
 *   renderer.root.add(mascot)
 *   await mascot.play("success", { loop: false })
 *   mascot.play("idle")
 *
 * Setters ignore repeated values and treat null as the default, so the class
 * can be registered with @opentui/react or @opentui/solid via extend().
 */
export class MascotRenderable extends Renderable {
  onComplete: ((animation: MascotAnimation) => void) | null
  private _animation: MascotAnimation
  private _paused: boolean
  private _done = false
  private _speed: number
  private _loop: boolean
  private _fit: MascotFit
  private _scale: 1 | 2
  private frame = 0
  private elapsed = 0
  private resumed = false
  private settle: (() => void) | null = null

  constructor(ctx: RenderContext, options: MascotOptions = {}) {
    const animation = options.animation ?? "idle"
    const fit = options.fit ?? "canvas"
    const scale = options.scale ?? 1
    super(ctx, { ...options, ...cellSize(animation, fit, scale), live: false })
    this._animation = animation
    this._fit = fit
    this._scale = scale
    this._speed = options.speed ?? 1
    this._loop = options.loop ?? true
    this._paused = !(options.playing ?? true)
    this.onComplete = options.onComplete ?? null
    this.updateLive()
  }

  get animation(): MascotAnimation {
    return this._animation
  }

  /** Switch to another animation, starting at its first frame. */
  set animation(value: MascotAnimation | null | undefined) {
    const next = value ?? "idle"
    if (next === this._animation) return
    this._animation = next
    this.restart()
  }

  /** False while paused, and after a non-looping animation has finished. */
  get playing(): boolean {
    return !this._paused && !this._done
  }

  /** Setting true on a finished animation replays it. */
  set playing(value: boolean | null | undefined) {
    this._paused = !(value ?? true)
    if (!this._paused && this._done) this.restart()
    else this.updateLive()
  }

  get speed(): number {
    return this._speed
  }

  set speed(value: number | null | undefined) {
    this._speed = Math.max(0, value ?? 1)
  }

  get loop(): boolean {
    return this._loop
  }

  set loop(value: boolean | null | undefined) {
    this._loop = value ?? true
  }

  get fit(): MascotFit {
    return this._fit
  }

  set fit(value: MascotFit | null | undefined) {
    const next = value ?? "canvas"
    if (next === this._fit) return
    this._fit = next
    this.resize()
  }

  get scale(): 1 | 2 {
    return this._scale
  }

  set scale(value: 1 | 2 | null | undefined) {
    const next = value ?? 1
    if (next === this._scale) return
    this._scale = next
    this.resize()
  }

  /** Index of the frame on screen within the current animation. */
  get frameIndex(): number {
    return this.frame
  }

  /**
   * Play an animation from its first frame. Resolves when a non-looping
   * animation finishes, or when another animation replaces this one.
   */
  play(animation: MascotAnimation = this._animation, options: { loop?: boolean } = {}): Promise<void> {
    this._animation = animation
    this._loop = options.loop ?? true
    this._paused = false
    const done = new Promise<void>((resolve) => {
      this.restart()
      this.settle = resolve
    })
    return done
  }

  /** Hold the current frame. */
  pause(): void {
    this.playing = false
  }

  /** Continue from the current frame. */
  resume(): void {
    this.playing = true
  }

  private restart() {
    const settle = this.settle
    this.settle = null
    this._done = false
    this.frame = 0
    this.elapsed = 0
    this.resize()
    settle?.()
  }

  private finish() {
    this._done = true
    this.elapsed = 0
    this.updateLive()
    const settle = this.settle
    this.settle = null
    settle?.()
    this.onComplete?.(this._animation)
  }

  private resize() {
    const size = cellSize(this._animation, this._fit, this._scale)
    this.width = size.width
    this.height = size.height
    this.updateLive()
  }

  private updateLive() {
    // Only keep the renderer's frame loop running while there is something to animate.
    const playing = this.playing
    if (playing && !this.live) this.resumed = true
    this.live = playing
    this.requestRender()
  }

  private advance(ms: number) {
    const anim = ANIMATIONS[this._animation]
    this.elapsed += ms
    if (this._loop) {
      const total = anim.durations.reduce((a, b) => a + b, 0)
      if (this.elapsed > total) this.elapsed %= total
    }
    while (this.elapsed >= anim.durations[this.frame]!) {
      if (this.frame + 1 < anim.frames.length) {
        this.elapsed -= anim.durations[this.frame]!
        this.frame++
      } else if (this._loop) {
        this.elapsed -= anim.durations[this.frame]!
        this.frame = 0
      } else {
        this.finish()
        break
      }
    }
  }

  protected override renderSelf(buffer: OptimizedBuffer, deltaTime: number): void {
    if (this.playing) {
      // The first frame after starting or resuming carries the time spent stopped; skip it.
      this.advance(this.resumed ? 0 : deltaTime * this._speed)
      this.resumed = false
    }

    const anim = ANIMATIONS[this._animation]
    const px = PIXELS[anim.frames[this.frame]!]!
    const b = this._fit === "animation" ? anim.bounds : FULL
    const left = this.x
    const top = this.y

    if (this._scale === 2) {
      for (let y = 0; y < b.height; y++) {
        for (let x = 0; x < b.width; x++) {
          const c = px[(b.y + y) * MASCOT_WIDTH + b.x + x]!
          if (c) buffer.fillRect(left + x * 2, top + y, 2, 1, COLORS[c]!)
        }
      }
      return
    }

    // Two pixels per cell: the upper one is the foreground of ▀, the lower one its background.
    for (let row = 0; row * 2 < b.height; row++) {
      const y = b.y + row * 2
      const hasLower = row * 2 + 1 < b.height
      for (let x = 0; x < b.width; x++) {
        const i = y * MASCOT_WIDTH + b.x + x
        const upper = px[i]!
        const lower = hasLower ? px[i + MASCOT_WIDTH]! : 0
        if (upper && lower) buffer.setCell(left + x, top + row, "▀", COLORS[upper]!, COLORS[lower]!)
        else if (upper) buffer.setCellWithAlphaBlending(left + x, top + row, "▀", COLORS[upper]!, CLEAR)
        else if (lower) buffer.setCellWithAlphaBlending(left + x, top + row, "▄", COLORS[lower]!, CLEAR)
      }
    }
  }

  protected override destroySelf(): void {
    const settle = this.settle
    this.settle = null
    settle?.()
    super.destroySelf()
  }
}
