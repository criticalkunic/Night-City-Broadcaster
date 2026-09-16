# Troubleshooting

## First-launch artwork downloads stop

Keep the app open and check your internet connection. The progress screen reports the failed download; use Retry when the connection is restored. Successful downloads are kept. Do not delete the artwork directory just to retry.

The initial setup needs the current catalog, card images, alternate references, and the legend back. A source outage can prevent setup from completing.

## The camera is missing or busy

- Click **Refresh cameras** in Camera setup.
- Close other applications using the same device. Some camera drivers allow only one application to open a webcam.
- Check Windows camera privacy settings or Linux device permissions.
- If another application supplies the video, select its virtual capture device in Camera setup. Do not select an output produced by Night City Broadcaster itself.

## Video is slow

Try **More source options → Capture mode → 1080p · 30 FPS**, then **720p · 30 FPS** if necessary. Automatic negotiation may choose an uncompressed mode that cannot sustain 30 FPS over your camera’s USB connection.

Check the OBS Browser Source frame rate. Card detections per second in Debug are not the webcam frame rate. Close extra live previews while comparing performance. Performance depends on the camera, driver, browser, and computer; selecting 30 FPS is not a guarantee that every device can deliver it.

## A card is missed or identified incorrectly

Open **Debug** and inspect the detected card crop. If the crop shows the mat or another card, check the Played cards region in Camera setup. Keep cards inside that region and avoid including the legend row.

For weak matches:

1. Reduce glare and hard shadows; try a more direct camera angle.
2. Check focus and increase capture resolution if card text and art are blurred.
3. Adjust recognition brightness and contrast in Camera setup.
4. Run **Download missing card art** in Debug.
5. For an alternate printing, use **Teach a different card artwork**: capture the card, inspect the frozen sample, and assign the correct identity.

Teaching a reference improves recognition; it does not replace the artwork displayed on stream. Use the manual card picker to correct the current play.

## Legends are wrong or missing

Check the three numbered crops under **Live legend detection** in Debug. Align the Legends region with the physical row and leave space between cards. Face-down sleeves, reflections, and partially covered cards can be ambiguous. Assign the correct legend and use the manual flip control when needed.

## Nothing appears in OBS

Use **Copy OBS stream link** in Stream settings. The URL must end in `/broadcast/live`; `/overlay` is the settings page.

Existing `/overlay/live` sources redirect to `/broadcast/live`, but newly copied links use the new address.

Keep the service running. Confirm the preview in the app, then refresh the OBS source. Check the display toggles and whether a card has been recognized or selected. The desktop app may choose a different port if 8766 was already occupied.

## Linux AppImage will not open

Mark the file executable:

```bash
chmod +x Night\ City\ Broadcast-*.AppImage
```

If your system lacks FUSE support, extract it and launch the contents:

```bash
./Night\ City\ Broadcaster-1.0.3.AppImage --appimage-extract
./squashfs-root/AppRun
```

Replace the version in the filename with your download. If the error mentions a newer GLIBC version, use a release built on a compatible distribution or run [from source](../README.md#linux-from-source).

## The service says “address already in use”

The standalone app selects a free port automatically. With `start.sh`, choose a port explicitly:

```bash
PORT=9000 ./start.sh
```

Then copy the stream link from the newly opened service.

## Reporting a bug

Include your app version, operating system, camera model, capture mode, and steps to reproduce. For recognition issues, attach the relevant Debug crop and the correct card name or printing. For startup issues, include the error message or terminal output.

Do not upload the full AppData folder, browser cookies, or a downloaded card library. Review camera captures before sharing them.


## Low camera or broadcast frame rate

In **Troubleshooting**, compare the incoming camera FPS with **Video performance**. Include the capture backend, pixel format, driver-reported FPS, resolution, and feed processing times when reporting a problem. Feed FPS measures prepared images, not frames actually displayed by OBS.

If incoming camera FPS is low, try **Camera setup → Capture mode → 720p · 30 FPS**, then restart the camera. Report whether this improves it. A high driver-reported rate does not guarantee that frames are arriving at that rate.

If camera FPS is healthy but feed FPS is low, include which layout and preview windows are open. This helps separate capture issues from broadcast processing issues.


### Incoming camera stays near 15 FPS at both resolutions

This places the slowdown before broadcast encoding. One possible cause is automatic exposure using too much time per frame. First try lighting the board more brightly and check the incoming camera FPS again.

On Windows, **Camera setup → More source options → Camera exposure → Short exposure · prioritize motion (1/64 s)** requests a shorter manual exposure. Click **Start camera** to apply it. This can darken both the preview and broadcast; increase board lighting. Select **Automatic exposure** and restart the camera to restore automatic adjustment. **Keep camera settings** makes no exposure changes and does not undo a previous manual setting.

The driver may reject exposure controls; the app reports this in Camera setup. A short exposure is a diagnostic option, not a guaranteed FPS fix. If capture remains slow, report the Troubleshooting driver FPS, exposure, and video-performance readings.
