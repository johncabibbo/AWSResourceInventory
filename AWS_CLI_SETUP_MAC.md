# Installing & Configuring the AWS CLI on macOS

A complete, step-by-step guide to installing the AWS Command Line Interface (CLI) on a Mac and configuring the credentials that **AWS Resource Inventory** (and any `boto3` script) uses to talk to your AWS account.

Written so a first-timer can follow it top to bottom, with enough reference detail for an experienced user to skim.

---

## Table of Contents

1. [What you'll accomplish](#1-what-youll-accomplish)
2. [Prerequisites](#2-prerequisites)
3. [Install the AWS CLI](#3-install-the-aws-cli)
   - [Method A — Official PKG installer (recommended)](#method-a--official-pkg-installer-recommended)
   - [Method B — Homebrew](#method-b--homebrew)
   - [Verify the installation](#verify-the-installation)
4. [Create AWS access keys (IAM)](#4-create-aws-access-keys-iam)
5. [Configure the AWS CLI](#5-configure-the-aws-cli)
   - [`aws configure` — the default profile](#aws-configure--the-default-profile)
   - [What the files look like](#what-the-files-look-like)
   - [Named profiles (multiple accounts)](#named-profiles-multiple-accounts)
   - [AWS IAM Identity Center / SSO (optional)](#aws-iam-identity-center--sso-optional)
6. [Verify it works](#6-verify-it-works)
7. [IAM permissions for AWS Resource Inventory](#7-iam-permissions-for-aws-resource-inventory)
8. [Security best practices](#8-security-best-practices)
9. [Troubleshooting](#9-troubleshooting)
10. [Quick reference](#10-quick-reference)
11. [Updating & uninstalling](#11-updating--uninstalling)

---

## 1. What you'll accomplish

By the end of this guide you will have:

- The **AWS CLI v2** installed on your Mac (`aws --version` works from any terminal).
- An **IAM access key** created in the AWS Console.
- A configured **default profile** (`~/.aws/credentials` + `~/.aws/config`) so scripts authenticate automatically.
- A verified connection (`aws sts get-caller-identity` returns your account).

> **Why this matters for AWS Resource Inventory:** the script uses `boto3`, which reads the exact same credentials the AWS CLI writes to `~/.aws/`. Once `aws configure` is done, the script "just works" — no keys in code.

---

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| **macOS 11 (Big Sur) or newer** | Works on both Apple Silicon (M1/M2/M3) and Intel Macs. |
| **Administrator access** | Needed to run the installer (you'll enter your Mac password). |
| **An AWS account** | With permission to create IAM access keys (or someone who can create them for you). |
| **Terminal** | Use the built-in **Terminal.app** (Applications → Utilities) or iTerm2. |

> You do **not** need Homebrew or Python to install the AWS CLI v2 — it ships as a self-contained package. (Python/`boto3` are only needed to run the inventory script itself.)

Check your macOS version: **Apple menu → About This Mac**. Check your chip the same way (it will say "Apple M…" or "Intel").

---

## 3. Install the AWS CLI

Pick **one** method. Method A (the official installer) is recommended because it's what AWS supports directly and it auto-updates cleanly.

### Method A — Official PKG installer (recommended)

**Option 1: Graphical installer**

1. Download the installer:
   [https://awscli.amazonaws.com/AWSCLIV2.pkg](https://awscli.amazonaws.com/AWSCLIV2.pkg)
2. Double-click **AWSCLIV2.pkg** and follow the prompts (Continue → Agree → Install).
3. Enter your Mac password when asked. Installs to `/usr/local/aws-cli` with a symlink at `/usr/local/bin/aws`.

**Option 2: Command-line install (no browser)**

```bash
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
rm AWSCLIV2.pkg
```

**Install for just your user (no `sudo`)** — if you can't or don't want to install system-wide, use an XML choices file to target your home folder:

```bash
cat > choices.xml <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <array>
    <dict>
      <key>choiceAttribute</key><string>customLocation</string>
      <key>attributeSetting</key><string>/Users/YOUR_USERNAME</string>
      <key>choiceIdentifier</key><string>default</string>
    </dict>
  </array>
</plist>
XML

installer -pkg AWSCLIV2.pkg -target CurrentUserHomeDirectory -applyChoiceChangesXML choices.xml
```

Then add `~/aws-cli/` to your `PATH` (see [Troubleshooting → command not found](#aws-command-not-found)).

### Method B — Homebrew

If you already use [Homebrew](https://brew.sh):

```bash
brew install awscli
```

Upgrade later with `brew upgrade awscli`.

> **Heads-up:** Homebrew's `awscli` is community-maintained and occasionally lags the official release. For most users either method is fine; if you hit version-specific bugs, prefer Method A.

### Verify the installation

Open a **new** terminal window (so it picks up the updated `PATH`) and run:

```bash
aws --version
```

Expected output (versions will differ):

```
aws-cli/2.17.0 Python/3.11.9 Darwin/23.5.0 source/arm64
```

Also confirm where it lives:

```bash
which aws        # usually /usr/local/bin/aws  (or /opt/homebrew/bin/aws on Apple Silicon Homebrew)
```

If `aws` isn't found, jump to [Troubleshooting](#aws-command-not-found).

---

## 4. Create AWS access keys (IAM)

Your CLI needs an **access key** (an ID + a secret) tied to an IAM identity. **Never use your AWS account root user for day-to-day access** — create a dedicated IAM user.

### Step 4a — Create the IAM user

1. Sign in to the **AWS Console** as an administrator → in the top search bar, type **IAM** and open it.
2. In the left sidebar choose **Users**, then click **Create user** (top right).
3. **User name:** enter something descriptive, e.g. `cli-inventory`.
4. Leave **"Provide user access to the AWS Management Console"** *unchecked* — this user only needs programmatic (CLI/API) access, not console login. Click **Next**.
5. **Set permissions →** choose **Attach policies directly**, then either:
   - tick the AWS-managed **`ReadOnlyAccess`** policy (simplest for a lab), **or**
   - use a tight custom policy scoped to just this tool (see [section 7](#7-iam-permissions-for-aws-resource-inventory)).
6. Click **Next → Create user**.

### Step 4b — Generate an access key

1. Click the user you just created → open the **Security credentials** tab.
2. Under **Access keys**, click **Create access key**.
3. For **Use case**, choose **Command Line Interface (CLI)**, tick the confirmation checkbox, click **Next**, then **Create access key**.
4. On the final screen AWS shows the key **one time**:
   - **Access key ID** — looks like `AKIA...` (this part is not secret)
   - **Secret access key** — a long random string, shown **only here, only now**

> ### ⚠️ SAVE THE SECRET ACCESS KEY NOW — YOU CANNOT GET IT AGAIN
>
> - **The secret access key is displayed only once.** After you leave this screen, **AWS can never show or recover it.** There is no "reveal" button and no way to look it up later.
> - **If you lose it, it cannot be recreated** — your only option is to **delete the key and create a brand-new one** (then re-run `aws configure`).
> - **Save it in a secure place**, such as a password manager (1Password, Bitwarden, Keychain) — **not** in a plain text file, email, chat message, or anything committed to Git.
> - **Treat it like a password to your AWS account.** The access key ID **and** secret together **grant full programmatic access to your AWS account at the permissions you assigned** — anyone who obtains them can act as this user (create/read/delete resources, and potentially run up charges). **Never share it or paste it into code.**
> - Click **Download .csv file** on this screen to capture both values safely, then move them into your password manager and delete the download.
>
> If a key is ever exposed (committed, emailed, pasted publicly), **delete/deactivate it immediately** in IAM → the user → Security credentials, and create a new one.

You'll paste these two values into `aws configure` in the next step; after that they live (encrypted only if you encrypt your disk) in `~/.aws/credentials`.

---

## 5. Configure the AWS CLI

### `aws configure` — the default profile

Run:

```bash
aws configure
```

You'll be prompted for four things:

| Prompt | What to enter | Example |
|---|---|---|
| **AWS Access Key ID** | The access key ID from step 4 | `AKIAIOSFODNN7EXAMPLE` |
| **AWS Secret Access Key** | The secret from step 4 | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| **Default region name** | The region you work in most | `us-east-1` |
| **Default output format** | `json` (or press Enter to leave blank) | `json` |

> **Which region?** Pick where your resources live (e.g. `us-east-1` N. Virginia, `us-west-2` Oregon, `eu-west-1` Ireland). AWS Resource Inventory scans **all** regions regardless, but Cost Explorer calls are made from `us-east-1`, so `us-east-1` is a safe default.

### What the files look like

`aws configure` writes two plain-text files in `~/.aws/`:

**`~/.aws/credentials`**
```ini
[default]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**`~/.aws/config`**
```ini
[default]
region = us-east-1
output = json
```

You can edit these by hand at any time. Lock them down so only you can read them:

```bash
chmod 600 ~/.aws/credentials ~/.aws/config
```

### Named profiles (multiple accounts)

If you work with more than one AWS account or role, use **named profiles** instead of overwriting the default:

```bash
aws configure --profile personal
aws configure --profile client-prod
```

Use a profile per command:

```bash
aws s3 ls --profile client-prod
```

…or set it for a whole terminal session (this also makes `boto3`/AWS Resource Inventory use it):

```bash
export AWS_PROFILE=client-prod
python3 aws_resource_inventory.py
```

In `~/.aws/config`, named profiles are written as `[profile NAME]` (the default stays `[default]`):

```ini
[default]
region = us-east-1

[profile client-prod]
region = us-west-2
output = json
```

### AWS IAM Identity Center / SSO (optional)

If your organization uses **IAM Identity Center (SSO)** instead of long-lived keys, configure it with:

```bash
aws configure sso
```

Follow the browser prompts, then sign in each session with `aws sso login --profile your-sso-profile`. SSO avoids storing permanent secrets on disk and is the recommended approach for company accounts.

---

## 6. Verify it works

Confirm your identity (proves the credentials are valid):

```bash
aws sts get-caller-identity
```

Expected:
```json
{
    "UserId": "AIDA...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/cli-inventory"
}
```

Exercise a permission the inventory tool relies on:

```bash
aws ec2 describe-regions --query "Regions[].RegionName" --output text
```

You should see a space-separated list of region names. If both commands succeed, **AWS Resource Inventory is ready to run**.

---

## 7. IAM permissions for AWS Resource Inventory

The script makes read-only calls to three services. Grant at least:

| Permission | Used for |
|---|---|
| `tag:GetResources` | Listing all tagged resources via the Resource Groups Tagging API |
| `ec2:DescribeRegions` | Discovering which regions are enabled in your account |
| `ce:GetCostAndUsage` | Pulling cost figures from Cost Explorer |

**Easiest (lab):** attach the AWS-managed **`ReadOnlyAccess`** policy to your IAM user.

**Least privilege (recommended):** attach this custom policy instead —

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AWSResourceInventoryReadOnly",
      "Effect": "Allow",
      "Action": [
        "tag:GetResources",
        "ec2:DescribeRegions",
        "ce:GetCostAndUsage"
      ],
      "Resource": "*"
    }
  ]
}
```

> Cost Explorer (`ce:*`) must also be **enabled** in the Billing console (Cost Explorer has to be turned on once per account before the API returns data).

---

## 8. Security best practices

- **Never commit credentials.** Keep keys out of code and out of Git. `~/.aws/credentials` should never be in a repository.
- **Least privilege.** Grant only the permissions a task needs (see section 7). Avoid `AdministratorAccess` for a read-only inventory tool.
- **Don't use the root user.** Create an IAM user (or use SSO) for CLI access.
- **Rotate keys regularly** and delete unused ones: IAM → Users → Security credentials.
- **Prefer short-lived credentials** (IAM Identity Center/SSO, or `aws sts assume-role`) over permanent access keys when possible.
- **Restrict file permissions:** `chmod 600 ~/.aws/credentials`.
- **Enable MFA** on the IAM user and the account root.
- **Use `AWS_PROFILE`** rather than pasting keys into scripts or environment variables ad hoc.

---

## 9. Troubleshooting

### `aws: command not found`

The install directory isn't on your `PATH`, or you're in a terminal opened before installation.

1. Open a **new** terminal and retry `aws --version`.
2. Find the binary: `ls -l /usr/local/bin/aws` (system install) or `ls -l /opt/homebrew/bin/aws` (Apple-Silicon Homebrew).
3. Add the folder to your shell profile. macOS uses **zsh** by default (`~/.zshrc`); older setups use bash (`~/.bash_profile`):

   ```bash
   echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```

   (For a per-user PKG install, add `export PATH="$HOME/aws-cli:$PATH"` instead.)

### `Unable to locate credentials`

You haven't run `aws configure`, or the wrong profile is active.

- Run `aws configure` (or `aws configure --profile NAME`).
- Check what's set: `aws configure list`.
- Confirm the files exist: `cat ~/.aws/credentials`.
- If you set `AWS_PROFILE`, make sure that profile actually exists.

### `You must specify a region`

No default region is configured. Either add one with `aws configure`, set `export AWS_DEFAULT_REGION=us-east-1`, or pass `--region us-east-1` on the command.

### `AccessDenied` / `not authorized to perform`

The IAM user lacks a permission. Attach the policy in [section 7](#7-iam-permissions-for-aws-resource-inventory) (or `ReadOnlyAccess`). For `ce:GetCostAndUsage`, also enable Cost Explorer in the Billing console.

### `ExpiredToken` / `The security token included in the request is invalid`

Temporary/SSO credentials expired — run `aws sso login --profile NAME` again, or your access key was deleted/rotated (create a new one).

### `The config profile (NAME) could not be found`

`AWS_PROFILE` or `--profile` points at a profile that isn't in `~/.aws/config`. List them: `aws configure list-profiles`.

### The script sees different credentials than the CLI

`boto3` and the CLI both read `~/.aws/`, but environment variables win. Check for stray `AWS_ACCESS_KEY_ID` / `AWS_PROFILE` in your shell: `env | grep AWS`.

---

## 10. Quick reference

| Command | Purpose |
|---|---|
| `aws --version` | Show installed version |
| `aws configure` | Set up the default profile |
| `aws configure --profile NAME` | Set up a named profile |
| `aws configure list` | Show the active configuration |
| `aws configure list-profiles` | List all profiles |
| `aws sts get-caller-identity` | Show who you're authenticated as |
| `aws ec2 describe-regions` | List enabled regions |
| `export AWS_PROFILE=NAME` | Use a profile for the session |
| `aws sso login --profile NAME` | Refresh SSO credentials |

**File locations**

| Path | Contents |
|---|---|
| `~/.aws/credentials` | Access key ID + secret, per profile |
| `~/.aws/config` | Region, output format, SSO settings, per profile |
| `/usr/local/bin/aws` | The CLI binary (system install) |

---

## 11. Updating & uninstalling

**Update**
- PKG install: re-download and run [AWSCLIV2.pkg](https://awscli.amazonaws.com/AWSCLIV2.pkg) (installs over the old version).
- Homebrew: `brew upgrade awscli`.

**Uninstall (PKG install)**
```bash
sudo rm -rf /usr/local/aws-cli
sudo rm /usr/local/bin/aws /usr/local/bin/aws_completer
```
(Optionally remove `~/.aws/` to delete your saved profiles.)

**Uninstall (Homebrew)**
```bash
brew uninstall awscli
```

---

**Guide for:** AWS Resource Inventory
**Platform:** macOS (Apple Silicon & Intel)
**Last Updated:** Jul 6, 2026

Copyright © 2026 Cloud Box 9 Inc. All rights reserved.
