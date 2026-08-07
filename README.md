<a href="https://ishank.dev">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ishankgupta95/ishankgupta95/master/dark_mode.svg">
    <img alt="Ishank Gupta's GitHub profile" src="https://raw.githubusercontent.com/ishankgupta95/ishankgupta95/master/light_mode.svg">
  </picture>
</a>

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

## Working notes

> Astronomical math is unforgiving. `panchang-ts` exists because most Panchang
> libraries quietly disagree with each other by several minutes, and in this
> domain minutes are the entire point.

> Privacy is an architecture decision, not a policy page. Transmute cannot leak
> your files because it never receives them.
