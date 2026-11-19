# Modification notice

Voice Forge Studio is a modified version of VoiceStudio
(https://github.com/debpalash/VoiceStudio), forked at commit 8f6c11343.

Modified from 2026-11-19 by Tamair. This notice is given under section 5(a) of the
GNU Affero General Public License version 3 (AGPL-3.0). The licence is unchanged;
see LICENSE and LICENSE-NOTICE.md.

## What changed

- Removed: the Electron desktop app, mobile apps, app-store and packaging tooling.
- Removed: cloud account and sync, analytics and diagnostics upload, community gallery,
  marketplace, telephony.
- Removed: dubbing, translation and video, dictation and live capture, audiobook and long-form.
- Reduced the speech engines and model catalogue to a game-development set, with VoxCPM2 as the
  default engine.

Generated audio is not covered by the AGPL. Each model's own licence decides whether its output
can be shipped.
