# Pulled from React Bits

`npx shadcn@latest add "https://reactbits.dev/r/<Name>-TS-TW"`

Source is vendored, so nothing here reaches the network at runtime.

**None of these are wired into the screening screen, on purpose.** They are
landing-page furniture: a score that counts up animates through wrong numbers
before settling, and a border officer reading DETAIN must never see a figure
that is briefly incorrect. Same reason there is no shimmer on the verdict.

Where they would earn their place:
- `CountUp` — the audit screen's event totals, which nobody acts on in seconds.
- `DecryptedText` — the capture screen's idle state, while waiting for a scan.
- `ShinyText` — unused; delete it if it is still here at week 8.

Skiper UI was also requested. Its registry (`skiper-ui.com/r/*.json`) returns
"Missing license key" — the components need a paid Pro licence. Add the key to
`components.json` and they will pull like the above.
