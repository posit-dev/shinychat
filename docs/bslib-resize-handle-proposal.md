# `bslib-resize-handle` proposal

This is the public custom-element contract proposed for bslib. It provides the
interaction layer for a controlled vertical resize separator. It deliberately
does not provide sidebar markup, panel layout, width persistence, drawer state,
or focus management outside the separator itself.

## Public API

The element name is `bslib-resize-handle`. Its constructor exposes the static
`resizeHandleEvents` property with exactly these event names:

```ts
["resize-request", "resize-start", "resize-end"];
```

The element exposes:

```ts
configure(options: {
  value: number
  min: number
  max: number
  panelSide: "inline-start" | "inline-end"
  disabled: boolean
  label: string
  step?: number // 10
  largeStep?: number // 50
}): void
```

`value`, `min`, and `max` are pixel values. The caller owns the rendered width
and updates the configuration whenever its container geometry changes. The
element bounds every request but does not persist a width.

`panelSide` is logical. Pointer delta is resolved against the computed writing
direction, so an inline-start artifact edge grows correctly in both LTR and
RTL. Arrow keys use physical Left/Right directions; `Shift` applies
`largeStep`; `Home` and `End` request the supplied minimum and maximum.

The element has separator semantics: `role="separator"`, vertical orientation,
`aria-valuemin`, `aria-valuemax`, `aria-valuenow`, `aria-valuetext`, and
`aria-keyshortcuts="ArrowLeft ArrowRight Home End"`. It is removed from the
tab order when disabled.

## Events

Events bubble and are composed:

```ts
new CustomEvent("resize-request", {
  detail: { value: number, source: "pointer" | "keyboard" },
});

new CustomEvent("resize-start" | "resize-end", {
  detail: { source: "pointer" | "keyboard" },
});
```

A pointer interaction starts after a primary-button, primary-pointer press.
Cancellation, lost pointer capture, disablement, and disconnection each end an
active interaction exactly once.

## Test matrix

- Pointer drag, primary-pointer rejection, and bounds clamping.
- Arrow, Shift+Arrow, Home, End, and up-to-date ARIA values.
- Logical inline-start and inline-end behavior in LTR and RTL.
- Desktop 8px and coarse-pointer 26px hit targets.
- Disabled, cancellation, lost capture, disconnect/reconnect, and duplicate
  listener prevention.
- A provider consumer chooses this element only after checking both
  `configure` and `resizeHandleEvents`; it never checks a bslib package
  version or internal sidebar implementation details.
