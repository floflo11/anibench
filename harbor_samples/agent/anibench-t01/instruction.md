You are given an image, `image.png`, 1200x600 pixels, with a white background.

**Task:** Make the boy on the far left wave his raised hand, bending at the wrist. Nothing else in the image may move or change. Make it a seamless 2-second loop.

Write ONE self-contained HTML file that animates the image with three.js and follows this contract exactly:

1. Load three.js as an ES module from `./vendor/three.module.js`, e.g. `<script type="module">import * as THREE from './vendor/three.module.js';</script>`. No other libraries and no network requests.
2. Load `./image.png` and draw it on a canvas of exactly 1200x600 CSS pixels at the top-left of the page (body margin 0), at device pixel ratio 1 (`renderer.setPixelRatio(1)`). Use an orthographic camera so one image pixel maps to one canvas pixel. Use `texture.colorSpace = THREE.SRGBColorSpace` and no tone mapping, so that frame 0 matches the original image. Keep the white background.
3. Expose `window.setTime(t)`, which synchronously renders the frame at time `t` seconds (0 <= t <= 2). The animation must repeat every 2 seconds: `setTime(0)` and `setTime(2)` must render identical frames, and `setTime(0)` must show the original image unchanged.
4. Set `window.ANIM_READY = true` only after the texture has loaded and `setTime` works. Correctness must not depend on `requestAnimationFrame` timing (you may also run a rAF loop for live playback).
5. Deterministic: no unseeded randomness and no wall-clock time inside `setTime`.

How you isolate and move the part is up to you (for example: cut it out with a polygon or alpha mask into its own mesh, and fill what it reveals). Pixel coordinates refer to the image with (0,0) at the top-left.

---
You are working in `/app`. The image is `/app/image.png` and three.js is at `/app/vendor/three.module.js` (it imports `./three.core.js` next to it). Write your answer to `/app/index.html`. You may inspect the image with any tools available in the container.
