# Choosing the optional headless editor

Researched on 28 October 2026. ReelForge's optional **AgentCut** workflow uses
**HyperFrames 0.8.214**. Blender remains the default for generated 3D scenes.
The goal is an editor a shell-capable agent can operate today, with local rendering,
reusable instructions, real media editing and a straightforward open-source licence.

## Why HyperFrames

[HyperFrames](https://github.com/heygen-com/hyperframes) already ships a versioned
npm CLI, headless rendering, agent skills, and editable HTML compositions. Its
[media contract](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes/references/format.md)
supports footage and images, source trims, playback speed, audio gain and fades,
along with text and seekable animation. Its
[existing-video guide](https://github.com/heygen-com/hyperframes/blob/main/docs/prompting/editing-existing-videos.mdx)
and [CLI skill](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes-cli/SKILL.md)
cover changing an existing edit, including timeline operations, snapshots and undo.
This covers both footage edits and graphic explainers alongside Blender's scenes.

The project uses [Apache-2.0](https://github.com/heygen-com/hyperframes/blob/main/LICENSE).
Local rendering needs Node.js 22+, ffmpeg/ffprobe and a headless Chrome binary;
it does not require HeyGen credentials or a cloud renderer. We install an exact
version and npm dependency lock under `tools/agentcut/`, disable telemetry and
update checks in the adapter, and expose local editing commands. ReelForge's
existing mastering, QA, review and manual Publish workflow remains the delivery gate.

## Other options considered

- [OpenCut](https://github.com/OpenCut-app/OpenCut#status) is undergoing a rewrite.
  Its README lists the Editor API, MCP and headless rendering as upcoming work.
  Building a separate renderer in an OpenCut fork would create another engine for
  ReelForge to maintain without using an existing OpenCut editing core.
- [Remotion](https://www.remotion.dev/docs/ai/skills) has strong React composition,
  headless rendering and agent support. Its
  [licence](https://www.remotion.dev/docs/license/pricing) offers free use to
  individuals and companies of up to three people, with paid company terms beyond
  that eligibility. HyperFrames is a simpler default for this open-source kit.
- [AgentCut](https://github.com/wuwangzhang1216/agentcut) is an unrelated MIT Rust
  CLI NLE with embedded agent instructions, JSON transactions and editor interchange.
  Its repository has Linux/macOS test coverage, but no published release was
  available at the time of research. It is a promising conventional NLE option;
  it is not the engine behind ReelForge's AgentCut command.
- [Kimo](https://github.com/naman-sharma12345/kimo) offers an MIT headless MCP editor
  with recent Linux/Windows binary releases. Its
  [platform notes](https://github.com/naman-sharma12345/kimo/blob/main/docs/RELEASE_BINARIES.md)
  mark macOS as untested. ReelForge needs a dependable path on all three platforms.
- [Renderly](https://github.com/isuryacharan/Renderly) offers shared CLI/MCP/GUI
  editing, but is pre-alpha, uses AGPL-3.0, and identifies Windows as its primary
  runtime-tested platform.
- [Cuttingfloor](https://github.com/Mvp2o-ai/cuttingfloor) offers a capable Docker
  MCP workflow, but no repository licence was found at research time. Its timeline
  cache also expires, while ReelForge keeps editable episodes on disk.

X search was used for discovery. Direct posts returned access errors, so social
summaries were not treated as evidence of shipped features. The choice above is
based on primary documentation, source, releases and CI configuration. It is a
fit decision for ReelForge, not a claim that one engine is best for every editor.

See [AGENTCUT.md](AGENTCUT.md) for the implemented workflow and commands.
