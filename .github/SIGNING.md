# Code signing the Windows installer

Windows and browsers warn about any new `.exe` that isn't signed: Edge says it "isn't commonly downloaded", Chrome
calls it a suspicious download, and Windows says "Windows protected your PC" until the user clicks **More info**,
then **Run anyway**. Where Windows 11's Smart App Control is on, it blocks unsigned apps it doesn't know, with no
**Run anyway** at all. Signing puts a verified publisher on the installer, lets its reputation carry over from one
release to the next instead of starting from zero every time, and lets Smart App Control run it. New releases can
still show a warning for a while until that reputation builds.

The release workflow signs the installer (and the uninstaller and the setup.tmp it unpacks) once the settings
below exist. Until then it builds the installer unsigned, exactly as before.

## Cost and who can use it

[Azure Artifact Signing](https://learn.microsoft.com/azure/artifact-signing/) (formerly Trusted Signing), Basic plan:
**$9.99 a month**. Individual developers must live in the **United States or Canada**. The certificate shows your
**legal name, city, state or province, and country** to anyone who opens the installer's Digital Signatures tab
(not your street address or email), and Windows shows the name as the publisher.

## One-time setup

1. **Azure.** Sign in at [portal.azure.com](https://portal.azure.com) and create a Pay-As-You-Go subscription. In
   **Cost Management + Billing**, check that the billing account's type is **Individual** and that its legal name
   and sold-to address match your government ID exactly: the identity check uses them.
2. **Subscriptions** > your subscription > **Resource providers** > **Microsoft.CodeSigning** > **Register**.
3. Search **Artifact Signing Accounts** > **Create**: a new resource group (e.g. `reelforge-signing`), an account
   name (3 to 24 letters and numbers, unique in Azure, e.g. `reelforgesigning`), region **East US**, pricing
   **Basic**. Then **Review + Create**.
4. On the new account: **Access control (IAM)** > **Add role assignment** > **Artifact Signing Identity Verifier**
   > yourself.
5. **Identity validations** > switch Organization to **Individual** > **New identity** > **Public**. Pick your
   billing account, check the **Certificate subject preview**, then **Create**. When the status says
   **Action Required**, open it and follow the link: you photograph your ID and yourself on your phone and add the
   result to Microsoft Authenticator. The status changes to **Completed**.
6. **Certificate profiles** > **Create** > **Public Trust**: a name (e.g. `reelforge`), your identity under
   **Verified CN and O**, street address and postal code left unticked. **Create**.
7. **Microsoft Entra ID** > **App registrations** > **New registration**, named `ReelForge GitHub signing`. Copy
   its **Application (client) ID** and **Directory (tenant) ID**. Then **Certificates & secrets** > **New client
   secret** (24 months) and copy its **Value** straight away: Azure shows it once.
8. Back on the Artifact Signing account: **Access control (IAM)** > **Add role assignment** > **Artifact Signing
   Certificate Profile Signer** > members: `ReelForge GitHub signing`.
9. On GitHub: the repository's **Settings** > **Secrets and variables** > **Actions**.
   - **Secrets:** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (step 7's values).
   - **Variables:** `ARTIFACT_SIGNING_ENDPOINT` (the account's URI from its Overview page, e.g.
     `https://eus.codesigning.azure.net`), `ARTIFACT_SIGNING_ACCOUNT` (step 3's name), `ARTIFACT_SIGNING_PROFILE`
     (step 6's name).
10. **Test without publishing:** **Actions** > **Release** > **Run workflow**. The Windows installer job's
    **Check the signature** step should say `Valid, signed by CN=<your name>, ...`.

Every version tag after that builds a signed installer. A release that can't sign fails instead of going out
unsigned, so make a new client secret before the old one expires and replace `AZURE_CLIENT_SECRET`. Once a signed
release is out, drop "the installer isn't code-signed" from the README, `.github/release-notes.md` and
`scripts/package.py`'s START-HERE text.

## Other options

- **An OV certificate** from a certificate authority (DigiCert, Sectigo, SSL.com and others): about $150 to $300 a
  year, works from any country, and needs a hardware token or the CA's cloud signing service. Same warnings and
  reputation as Artifact Signing.
- **EV certificates** cost $400 or more a year and no longer skip the SmartScreen warning (Microsoft removed that
  in 2024), so they aren't worth it for this.
- **[SignPath Foundation](https://signpath.org)** signs open-source projects for free under its own name instead
  of yours, but asks for a project with some verifiable reputation (download history), a code signing policy page
  and its own signing workflow.
