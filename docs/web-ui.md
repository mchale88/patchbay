# Web UI guide

Open `http://<server>:8080/`. The UI updates live over a WebSocket; every browser and
API client sees changes immediately. The connection indicator in the header shows
**live** while connected and reconnects automatically.

## Layout

```
┌ Patchbay  ● live            [ ] Take mode  [+ Output]  API docs  [⚙ admin] [Log out] ┐
├──────────────────────────────────────────────────────────┬──────────────────────────────┤
│ OUTPUTS                                                  │ PRESETS                      │
│ ┌──────────────────────┐ ┌──────────────────────┐        │ [Save current routing as…]   │
│ │ PGM            live  │ │ AUX 1        pending │        │ Show open  Recall Update ✕   │
│ │ STUDIO-SRV (PGM)      │ │ STUDIO-SRV (AUX 1)    │        │                              │
│ │ [CAM-PC (Cam 1)   ▾] │ │ [WIRELESS (HH) ▾]    │        │ NDI SOURCES (5)              │
│ │ 👁 2  Clear Edit Del │ │ 👁 0  Clear Edit Del │        │ ● CAM-PC (Cam 1)             │
│ └──────────────────────┘ └──────────────────────┘        │ ● STUDIO-SRV (PGM)   router   │
└──────────────────────────────────────────────────────────┴──────────────────────────────┘
```

## Outputs

Each card is one virtual NDI® output.

- **Title / subtitle:** the output name and the complete NDI source name receivers see.
- **Status:** `idle` (grey), `live` (green), `pending` (amber: source offline, applied
  when it returns), `not advertised` (red: the NDI output could not be created; it is
  retried automatically, hover for details).
- **Source dropdown:** pick a source to route immediately. `— none —` clears the route.
  Offline sources stay selectable and are marked *(offline)*. Sources marked ↺ are other
  router outputs.
- **👁 N:** number of receivers connected to this output.
- **groups:** the NDI groups this output is published in, if set.
- **Clear:** remove the route (receivers get no video).
- **Edit:** rename the output or change its NDI groups. This recreates the NDI source,
  so connected receivers reconnect.
- **Delete:** remove the output from the network.

### Create an output

Click **+ Output**, enter a name (unique, max 100 characters) and optionally NDI groups
(comma-separated). Leave groups empty to use the server default (`NDI_GROUPS`, otherwise
the NDI `public` group).

> Receivers only see outputs in groups they are configured to receive. NDI tools
> receive the `public` group by default; if you put an output in group `Main`, add
> `Main` to the receivers' groups in NDI Access Manager.

## Take mode (salvo)

1. Tick **Take mode** in the header.
2. Change any number of dropdowns. Changed cards are outlined in purple and marked
   *staged*; nothing is sent yet.
3. Click **Take** in the bottom bar to apply all staged changes at once, or **Discard**.

The salvo is validated as a whole. If any entry is invalid (for example it would create a
loop), nothing is applied and an error is shown.

## Presets

- **Save:** type a name under *Presets* and click **Save**. The current route of every
  output is stored.
- **Recall:** applies the preset as a salvo. Outputs deleted since the preset was saved
  are skipped.
- **Update:** overwrite the preset with the current routing.
- **✕:** delete the preset.

## NDI sources

Lists every NDI source the server discovers, including the router's own outputs (marked
*router*). Hover a source to see its address.

## Settings (⚙)

Click **⚙ \<your username\>** in the header.

- **API keys:** create keys for Companion, Stream Deck and scripts; revoke them. A new
  key is shown once — copy it then. See [authentication.md](authentication.md#api-keys).
- **Users:** add users, set another user's password, delete users.
- **My password:** change your own password (logs out your other sessions).
- **About:** version, NDI runtime, license and trademark notice.

**Log out** ends your session in this browser.

## About and trademark notice

The footer and **⚙ Settings → About** show the version, the loaded NDI runtime, the
license, and the NDI trademark notice with a link to <https://ndi.video/>.

## API docs

The **API docs** link opens the interactive Swagger UI at `/docs`. Use **Authorize** there
with an API key to try requests. Full reference: [api.md](api.md).

## Keyboard

- **Esc** closes the open dialog or the Settings panel.
- Dialogs submit with **Enter**.

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. NDI tools (for example NDI Studio Monitor and NDI Access Manager) are available from <https://ndi.video/tools/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
