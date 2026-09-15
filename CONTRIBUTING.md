# Contributing

Bug reports, camera compatibility reports, and focused fixes are welcome. Check existing issues before opening a new one.

For a bug report, describe what you expected, what happened, and how to reproduce it. Include the operating system and app version. For recognition problems, a cropped Debug image is more useful than a full-screen screenshot.

For code changes:

1. Set up the project using the [development guide](docs/development.md).
2. Keep each pull request focused on one behavior or fix.
3. Add a regression test when changing recognition, state handling, or first-launch downloads.
4. Run the relevant Python and JavaScript tests.
5. Add user-facing changes to the **Unreleased** section of [CHANGELOG.md](CHANGELOG.md).
6. Describe the change and how you tested it. Include screenshots for interface changes.

Keep camera captures, downloaded artwork, card catalogs, personal settings, and build products out of pull requests. Synthetic images are preferred for recognition tests. Do not add card artwork to the application bundle.

Desktop changes should preserve the shared stream URL and keep saved data separate from the executable. Linux and Windows builds must continue to work without a pre-existing card database.

Contributions to project code are made under the repository’s GPL-3.0-only license.
