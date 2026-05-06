# Releasing Eargrape

This repository publishes the packaged Windows executable through GitHub Releases instead of committing `dist/Eargrape.exe` into git.

## Automatic release from a tag

Push a version tag that starts with `v`:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions will:

- install Python and build dependencies on `windows-latest`
- run `PyInstaller` with `eargrape.spec`
- upload `Eargrape-v0.1.0-windows-x64.exe` to the matching GitHub Release

## Manual release from GitHub Actions

You can also run the workflow manually from the GitHub Actions page:

- workflow: `Build And Publish Release`
- input `tag`: for example `v0.1.1`
- input `prerelease`: `true` if you do not want it shown as a stable release

If the tag does not exist yet, the workflow creates the release against the current commit.

## Notes

- The executable stays ignored by git because `dist/` is listed in `.gitignore`.
- The Release asset name includes the tag so multiple versions can coexist cleanly.
