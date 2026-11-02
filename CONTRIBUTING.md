# Contributing to Patchbay

Thanks for helping! Bug reports, ideas and pull requests are welcome.

## License of contributions

Patchbay is published under the [PolyForm Noncommercial License 1.0.0](LICENSE), and the
maintainer also sells commercial licenses ([COMMERCIAL.md](COMMERCIAL.md)). For that to
work, the maintainer must be able to license every part of the code under both.

By submitting a contribution (a pull request, patch or code in an issue) you agree that:

1. you wrote it, or otherwise have the right to submit it;
2. you grant the Patchbay maintainer a perpetual, worldwide, non-exclusive, royalty-free,
   irrevocable license to use, modify, sublicense and distribute your contribution under
   any license terms, including the PolyForm Noncommercial License and commercial
   licenses; and
3. your contribution contains no code from the NDI® SDK (headers, samples, libraries or
   documentation) or other third-party code under incompatible terms.

Add this line to your commit messages to confirm:

```
Contribution-License: I agree to the Patchbay contribution terms in CONTRIBUTING.md
```

## Development

See [docs/development.md](docs/development.md). Run the tests before opening a pull request:

```bash
.venv/bin/pytest -q
```

## NDI trademark

Keep the NDI attributions in the UI and docs intact. Write "NDI®" at the first use in a
new document, include "NDI® is a registered trademark of Vizrt NDI AB" and a link to
<https://ndi.video/>. See [NDI-SDK-NOTICE.md](NDI-SDK-NOTICE.md).
