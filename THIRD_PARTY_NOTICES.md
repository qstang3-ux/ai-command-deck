# Third-party components

## asciinema-player 3.17.0

- Source: https://github.com/asciinema/asciinema-player
- Distribution: https://registry.npmjs.org/asciinema-player/-/asciinema-player-3.17.0.tgz
- License: Apache License 2.0, included in `ai_command_deck/static/vendor/LICENSE`.
- Copyright: the upstream authors; source attribution is retained in bundled JavaScript.
- Bundled files: `asciinema-player.min.js` and `asciinema-player.css`, unmodified.

## Runtime dependencies

The Python package installs aiohttp and its dependencies through pip. They are not vendored in this repository and retain their respective licenses.

## Protocols

The PTY recorder implements asciicast v2 and the local stream implements ALiS v1, documented by asciinema:

- https://docs.asciinema.org/manual/asciicast/v2/
- https://docs.asciinema.org/manual/server/streaming/
