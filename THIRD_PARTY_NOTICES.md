# Third-party notices

The repository's MIT license covers Content Machine project code. It does not replace the terms of dependencies, models, fonts, browsers, or media. Executables, node_modules, models, and private assets are not shipped in this repository.

| Component | License / role |
| --- | --- |
| Python | PSF; separately installed runtime |
| NumPy | BSD-3-Clause; calculations and synthesized SFX |
| Pillow | HPND; contact sheets |
| Pydantic / pydantic-core | MIT; structured exchange |
| OpenCV Python headless | Apache-2.0 for the recent package/code; optional face processing with separately licensed weights |
| fontTools / Brotli | MIT; preparation of user-supplied fonts |
| React / React DOM / TypeScript | MIT; native compositions and type checking |
| Remotion 4.0.371 / @remotion packages | **Remotion License**, not MIT; separately installed from npm, pinned in lockfiles |
| FFmpeg / FFprobe | Depends on build: LGPL or GPL when components such as libx264 are included; system executables, not bundled |
| faster-whisper / CTranslate2 | MIT; optional local transcription, not required for SRT/JSON |
| Whisper / YuNet weights | Not bundled; check the specific model's license |
| Fonts, browser, footage, music | Not bundled; supplied by the user under appropriate rights |

Remotion currently permits free video creation for individuals, non-profit organizations, and companies with up to three employees. Other entities or uses may require a company license. Its terms also restrict resale of derivatives of the framework. Consult the [official license](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md) and [official licensing documentation](https://www.remotion.dev/docs/license) for your case. Setup does not purchase a license or subscription.

This project's React components use Remotion's public API. The framework is not copied into this repository or relicensed under MIT. FFmpeg-only steps remain usable without Remotion where animations are not required.

Use `python -m pip freeze` and the Node lockfiles to inspect the versions installed in your environment. Installed packages retain their own notices; preserve applicable notices if distributing a product that incorporates those runtimes. Licensing references checked on October 20, 2026.
