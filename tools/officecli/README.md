# OfficeCLI runtime

The application looks for the platform-specific OfficeCLI binary in this
directory, or at the path supplied through `OFFICECLI_PATH`.

The release binary is deliberately not committed to Git. On a packaging
machine, run `scripts/download_officecli.ps1`; the resulting Windows binary is
then included in the offline installer. Teacher computers never need to reach
GitHub.

Pinned version: `1.0.142`

Required redistribution notices are stored in
`third_party/OfficeCLI/`.
