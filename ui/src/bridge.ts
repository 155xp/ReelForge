// The window's link to its Python side (studio/bridge.py): a child process that answers calls and sends what to show,
// one line of JSON each way. The newest of each event is kept (a "view"), so a component reads the view it draws.

import { existsSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { useSyncExternalStore } from "react"

export const ROOT = process.env.REELFORGE_ROOT || resolve(dirname(import.meta.dir), "..")

/** The kit's Python: the one the launcher ran with, else .venv's, else whatever "python" is. */
export function pythonPath(): string {
  if (process.env.REELFORGE_PYTHON) return process.env.REELFORGE_PYTHON
  for (const p of [join(ROOT, ".venv", "Scripts", "python.exe"), join(ROOT, ".venv", "bin", "python")])
    if (existsSync(p)) return p
  return process.platform === "win32" ? "python" : "python3"
}

type Listener = () => void
type Handler = (data: any) => void

export interface BridgeOptions {
  python?: string
  env?: Record<string, string>
  log?: string
}

export class Bridge {
  private proc: ReturnType<typeof Bun.spawn> | null = null
  private next = 1
  private pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>()
  private views = new Map<string, unknown>()
  private listeners = new Set<Listener>()
  private handlers = new Map<string, Set<Handler>>()
  exited: Promise<number> = Promise.resolve(0)
  closed = false
  /** Why the Python side stopped, when it stopped by itself. */
  failure: string | null = null

  constructor(private opts: BridgeOptions = {}) {}

  /** Start the Python side and the service named (dashboard or setup); resolves with what it says to start with. */
  async start<T = any>(service: string, options: object): Promise<T> {
    const log = this.opts.log ?? process.env.REELFORGE_LOG ?? ""
    this.proc = Bun.spawn({
      cmd: [this.opts.python ?? pythonPath(), "-m", "studio.bridge"],
      cwd: ROOT,
      env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", REELFORGE_LOG: log, ...this.opts.env },
      stdin: "pipe",
      stdout: "pipe",
      stderr: log ? "ignore" : "pipe",
    })
    const proc = this.proc
    this.exited = proc.exited.then((code) => {
      this.closed = true
      if (!this.failure && this.pending.size) this.failure = `ReelForge's Python side stopped (exit code ${code}).`
      for (const p of this.pending.values()) p.reject(new Error(this.failure ?? "closed"))
      this.pending.clear()
      this.emit("closed", { code })
      return code
    })
    void this.read(proc.stdout as ReadableStream<Uint8Array>)
    if (!log && proc.stderr) void this.keepStderr(proc.stderr as ReadableStream<Uint8Array>)
    return this.call<T>("start", service, options)
  }

  private async read(stream: ReadableStream<Uint8Array>) {
    const decoder = new TextDecoder()
    const reader = stream.getReader()
    let buffer = ""
    while (true) {
      const { value: chunk, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(chunk, { stream: true })
      let nl: number
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim()
        buffer = buffer.slice(nl + 1)
        if (line) this.receive(line)
      }
    }
  }

  private stderrTail: string[] = []

  private async keepStderr(stream: ReadableStream<Uint8Array>) {
    const decoder = new TextDecoder()
    const reader = stream.getReader()
    while (true) {
      const { value: chunk, done } = await reader.read()
      if (done) break
      this.stderrTail.push(...decoder.decode(chunk, { stream: true }).split("\n"))
      this.stderrTail = this.stderrTail.slice(-40)
    }
  }

  /** The last lines the Python side wrote to stderr (when there's no log file). */
  get errors(): string {
    return this.stderrTail.join("\n").trim()
  }

  private receive(line: string) {
    let msg: any
    try {
      msg = JSON.parse(line)
    } catch {
      return
    }
    if (msg.id !== undefined && msg.ev === undefined) {
      const p = this.pending.get(msg.id)
      if (!p) return
      this.pending.delete(msg.id)
      if (msg.e !== undefined) p.reject(new Error(msg.e))
      else p.resolve(msg.r)
      return
    }
    if (msg.ev !== undefined) this.emit(msg.ev, msg.d)
  }

  /** An event from the Python side (or a made-up one, for tests): kept as a view, and handed to its handlers. */
  emit(event: string, data: unknown) {
    this.views.set(event, data)
    for (const h of this.handlers.get(event) ?? []) h(data)
    for (const l of this.listeners) l()
  }

  call<T = any>(method: string, ...args: unknown[]): Promise<T> {
    if (!this.proc || this.closed) return Promise.reject(new Error(this.failure ?? "ReelForge's Python side isn't running"))
    const id = this.next++
    const stdin = this.proc.stdin as import("bun").FileSink
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      stdin.write(JSON.stringify({ id, m: method, a: args }) + "\n")
      stdin.flush()
    })
  }

  /** A call whose answer nobody waits for (a button press): a failure shows up in the log. */
  send(method: string, ...args: unknown[]): void {
    this.call(method, ...args).catch((e) => this.emit("toast", { title: "Something went wrong", body: String(e?.message ?? e), severity: "error", timeout: 8 }))
  }

  on(event: string, fn: Handler): () => void {
    let set = this.handlers.get(event)
    if (!set) this.handlers.set(event, (set = new Set()))
    set.add(fn)
    return () => set!.delete(fn)
  }

  view<T>(name: string): T | undefined {
    return this.views.get(name) as T | undefined
  }

  subscribe = (fn: Listener) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  /** Ask the Python side to stop; resolves with whether it's finishing a stats read first. */
  async stop(): Promise<boolean> {
    if (!this.proc || this.closed) return false
    let busy = false
    try {
      busy = Boolean(await Promise.race([this.call<boolean>("stop"), Bun.sleep(1500).then(() => false)]))
    } catch {
      // gone already
    }
    try {
      ;(this.proc.stdin as import("bun").FileSink).end()
    } catch {
      // closed already
    }
    return busy
  }

  kill() {
    try {
      this.proc?.kill()
    } catch {
      // gone already
    }
  }
}

/** A view the Python side sends (re-rendering the component whenever it changes). */
export function useView<T>(bridge: Bridge, name: string): T | undefined {
  return useSyncExternalStore(bridge.subscribe, () => bridge.view<T>(name))
}
