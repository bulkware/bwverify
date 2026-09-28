# Code Signing Policy

bwVerify release artifacts are not currently code signed. Windows and Linux users should
verify releases through the project's release notes, checksums, and source repository.

When signing is introduced, private keys must remain in the release automation's protected
secret store. Contributors must never commit certificates, private keys, passwords, or token
files to this repository.
