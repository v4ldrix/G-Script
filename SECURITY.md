# Security

g-script lets web chat pages and a phone drive Roblox Studio on your PC, so it is built defensively:

- The PC-side bridge listens on `127.0.0.1` only and checks the `Host` header, the extension's origin and a secret token.
- The first browser extension to connect is trusted; a second one is refused until the first goes quiet or you press
  "Forget the connected browser extension" in the g-script window.
- The phone server is **off by default**. Every new phone must be allowed on the PC (you compare two words).
  Phone links (QR) work once. Wrong guesses and request floods are rate-limited.
- The phone can only chat, approve/decline, stop and request previews. It cannot run Studio tools directly.
- Anything that changes your game needs your approval; builds set undo points.
- The phone link is plain HTTP and only meant for your home Wi-Fi, so use a network you trust.

Found a problem? Please open a private security advisory on GitHub instead of a public issue.
