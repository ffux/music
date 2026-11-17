# Wrapper build validation — 17 November 2026

- Target: vibedeploy, Linux x86_64.
- Wrapper source: `100e0a864e883e03a3ac450a780dd9563fff5271`.
- Input: Apple Music Android 3.6.0-beta build 1109 APKM, x86_64 split.
- APKM SHA-256: `5be907af370a7f6bd73344e646dcfebe2e64c2da3b9ad71192110c91950f3f67`.
- Apple library verification: 18 passed, 0 failed.
- Android runtime verification: 83 passed, 0 failed.
- Image: `music-wrapper:100e0a8`.
- Image ID: `sha256:c5a52621293d6fb63e4c8c7914ec4385754bfd2bcd4c02487ab83d9d5b058402`.
- Image size: 99,962,372 bytes.
- Build completed successfully using `wrapper/manage.py build`.

Prepared source and original input are retained on the VM under
`/root/music-alac-review/`, outside webhook-managed deployments. No Apple binaries
are committed to GitHub. The existing music storage and application configuration
were not changed. No wrapper service was started or account authenticated.

Still required: runtime readiness, private sign-in/2FA, one isolated ALAC download,
metadata validation and full playback. Do not interpret a successful image build
as confirmation of authentication or successful lossless downloading.
