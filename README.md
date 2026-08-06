```go
package main

type Engineer struct {
	Role     string
	Frontend []string
	Backend  []string
	Thesis   string
	Shipping []string
	Learning []string
}

var ishank = Engineer{
	Role:     "Engineer",
	Frontend: []string{"TypeScript", "React", "Next.js", "React Native"},
	Backend:  []string{"Go", "Rust", "Node"},
	Thesis:   "If it can run on the client, it should run on the client.",
	Shipping: []string{"panchang-ts", "Dharmagya", "Transmute", "Onstage"},
	Learning: []string{"retrieval", "agent design", "eval harnesses"},
}

// Reachable at the addresses below. Cold starts welcome.
func main() { ishank.Ship() }
```

React and TypeScript on the front, Go and Rust on the back. Most of what I build
ships without a server at all, and the parts that need one stay small and fast.

## Projects

| | What it is | Built with |
| :-- | :-- | :-- |
| **[panchang-ts](https://www.npmjs.com/package/panchang-ts)** | Pure TypeScript library for Hindu Panchang calculations: Tithi, Nakshatra, Yoga, Karana, Vara, sunrise/sunset, Rahu Kalam, Gulika, Yamaganda, Abhijit Muhurta. Zero native dependencies, Hermes-safe. | `TypeScript` |
| **[Dharmagya](https://dharmagya.app)** | Daily Panchang, aartis, and the Hindu calendar. Android and iOS app that runs fully offline, plus a Next.js web build sharing the same calculation core. | `React Native` `Expo` `Next.js` |
| **[Transmute](https://transmute.tools)** | Converts images, PDFs, audio, and video in the browser. There is no upload endpoint, so there is nothing to leak. | `Next.js` `WebAssembly` |
| **[Onstage](https://ishankgupta95.github.io/OnStage/)** | App Store and Play Store screenshot studio. 24 device frames, 20 layouts, pixel-exact exports per store slot. | `Next.js` `Canvas` |

## How the pieces fit

```
                    ephemeris math
                          │
                  ┌───────▼────────┐
                  │   panchang-ts  │   npm, zero deps
                  └───────┬────────┘
                          │ imported by
              ┌───────────▼───────────┐
              │       Dharmagya       │
              ├───────────┬───────────┤
              │  iOS/And  │    web    │
              │  offline  │  Next.js  │
              └───────────┴───────────┘

  Transmute  ──▶  ffmpeg.wasm / libvips  ──▶  file    │ client only
  Onstage    ──▶  canvas compositor      ──▶  PNG     │ client only
```

## Stack

| | |
| :-- | :-- |
| **Languages** | TypeScript, Go, Rust, JavaScript, Python |
| **Web** | React, Next.js, Tailwind |
| **State and data** | Zustand, React Query, Zod |
| **Mobile** | React Native, Expo |
| **Backend** | Go, Rust, Node, Express, PostgreSQL |
| **Tooling** | Nx monorepos, WebAssembly, Git |

## Working notes

> Astronomical math is unforgiving. `panchang-ts` exists because most Panchang
> libraries quietly disagree with each other by several minutes, and in this
> domain minutes are the entire point.

> Privacy is an architecture decision, not a policy page. Transmute cannot leak
> your files because it never receives them.

> Go and Rust earn their place where TypeScript starts fighting the problem. Go
> for concurrency and single-binary deploys with no runtime to babysit, Rust when
> the cost of a wrong assumption should be a compile error rather than a pager.

> Offline-first is a performance strategy in disguise. No spinner beats a render
> that never waited on a network.

## Elsewhere

| | |
| :-- | :-- |
| Portfolio | [ishank.dev](https://ishank.dev) |
| LinkedIn | [in/ishankg](https://www.linkedin.com/in/ishankg/) |
| Email | [ishank1995@gmail.com](mailto:ishank1995@gmail.com) |
