# Validation matrix for the eight “Known broken” reports

This page is a runbook, not a resolution claim. A row remains `INFERRED` until
the named environment has run the same build and supplied the artifacts. Use a
fresh data directory for every arm so profiles and sockets cannot collide:

```sh
export XDG_DATA_HOME="$(mktemp -d /tmp/cordial-known-broken.XXXXXX)"
export CORDIAL_DEV_CONTROL=1
```

APK and extracted libraries stay outside the checkout. Do not drive the user's
real compositor with injected input; the two input harnesses create their own
nested compositor.

## Current implementation state

| Issue | Code/instrument now present | Acceptance still required | State |
|---|---|---|---|
| #35 SIGSEGV | `CORDIAL_NO_TOUCH=1` control and pre-call touch trace | Steam Deck run with a core/backtrace, with and without touch | `INFERRED` |
| #36 touchscreen | explicit MCP `begin/update/end/cancel`, stable IDs, both native-path controls | three runs per arm on real touchscreen hardware | `INFERRED` |
| #38 missing window | GTK/Wayland lifecycle and present instrumentation already present | COSMIC, KWin and wlroots runs; capture CPU plus two stacks if it spins | `INFERRED` |
| #39 fullscreen | live MCP fullscreen tool and ten-cycle runner | KDE/AMD and reporter's GNOME run | `INFERRED` |
| #41 X11 camera jump | XI2 `XI_RawMotion` primary path, warp fallback, focus-loss releases | real X11: ten drags, first person, shift lock and focus loss | `INFERRED` |
| #52 exit hang | bounded teardown watchdog and unit tests already present | workspace tests plus repeated real exits | awaiting local dependency |
| #53 TextBox | renderer-specific fullscreen/resize arm and compositor captures | Vulkan and cairo locally, then reporter's Hyprland | `INFERRED` |
| #56 Hyprland lock | toplevel target, confirmed-parent relative routing and expanded report | reporter's Hyprland run | `INFERRED` |

## #35 and #36: touch bisection

Start the same build three times for each row and set
`CORDIAL_TRACE_TOUCH=1` in all three:

| Arm | Extra environment | Meaning |
|---|---|---|
| both paths | none | current complete delivery |
| `nativePassInput` only | `CORDIAL_NO_AGDK_TOUCH=1` | excludes `onTouchEventNative` |
| `onTouchEventNative` only | `CORDIAL_NO_PASS_INPUT=1` | excludes `nativePassInput` |
| control | `CORDIAL_NO_TOUCH=1` | binds no Wayland touch and calls neither native |

For each run perform one down/move/up, a two-contact sequence, and cancel. The
MCP calls are `cordial_touch`; the equivalent raw protocol is:

```text
touch begin 7 300 220
touch update 7 340 240
touch begin 11 600 220
touch end 7
touch cancel
```

Keep the last `CORDIAL_TRACE_TOUCH` line and a core/backtrace if it faults. If
the last pre-call line is identical for #35 and #36, only then treat #35 as a
candidate duplicate. A healthy `DeviceUtils` warning alone is not evidence.
For the repeatable MCP sequence, run `tools/touch-e2e.py --profile default`
against each restarted arm; it requires all phases to be applied and the client
to remain responsive, but the trace/backtrace still decides which native died.

## #38: mapped window and first frame

The required timestamps are GTK activation, realise, map, `xdg_toplevel`
creation, first surface commit and first present. If no window appears and CPU
is near 100%, take two all-thread backtraces several seconds apart before
editing anything. A stable blocked stack and a moving hot stack are different
failures even when the screen is equally blank.

Run KWin and a wlroots compositor nested. COSMIC remains an external run; no
local result substitutes for it.

## #39: ten fullscreen cycles

Launch with `CORDIAL_DEV_CONTROL=1`, then:

```sh
tools/fullscreen-e2e.py --profile default --cycles 10
```

Every fullscreen and windowed state reads `info` twice, requires the present
counter to advance, requires a non-zero extent, and writes a swapchain PNG plus
`report.json` under `/tmp/cordial-fullscreen-e2e`. Run once on KDE/AMD and once
on the reporter's GNOME environment. A command returning `ok` is not a pass.

## #53: fullscreen text editor

Run the same signed-in profile in a nested sway twice:

```sh
tools/text-input-e2e.py --profile TextVulkan --gtk-renderer vulkan
tools/text-input-e2e.py --profile TextCairo --gtk-renderer cairo
```

The fullscreen arm requires the outer toplevel to equal the output exactly,
keeps a real TextBox focused, types into it, checks placement after the
transition, and requires presents to advance before and after leaving
fullscreen. It writes both compositor and swapchain captures. Repeat the two
arms on Hyprland; local sway establishes the harness, not Hyprland behaviour.

## #41 and #56: relative motion

`cordial_pointerlock` (or the raw `pointerlock` verb) now reports enough state
to distinguish the branches. On X11 require `backend=x11 mode=xi2`; force or
observe `mode=warp` once with `CORDIAL_NO_XI2=1` as the fallback control. On
Hyprland require `target=toplevel`, `pointer_surface=toplevel`,
`requested=true` and `confirmed=true` before judging camera movement.

In each environment perform ten right drags, shift lock, first person, Escape,
leave/re-enter, and focus loss/return. The cursor must neither drift nor jump,
and camera deltas must continue. `tools/pointer-lock-e2e.py` checks Cordial's
decision state in nested sway, but sway's refusal to confirm constraints means
it cannot replace either live compositor run.

## #52: shutdown

The unit tests cover watchdog expiry, an already-complete teardown, completion
during the wait, and the bounded no-native-handle path. After those tests pass,
run repeated real closes and assert that no profile-owned `cordial-run` remains.
Exit 124 is an explicit watchdog diagnosis; an indefinite process is a failure.

Only then remove #52 from `README.md`. This checkout could not reach those
tests on 2026-10-05 because the host lacked `libadwaita-1.pc`; keeping the row is
deliberate rather than overlooking that the GitHub issue is closed.
