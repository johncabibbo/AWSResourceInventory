# AWS Resource Inventory Script

## What Is This?

`aws_resource_inventory.py` is a Python script that connects to your AWS account and produces a complete list of every cloud resource you have running — things like virtual machines, databases, storage buckets, and serverless functions. For each resource it shows:

- The resource's unique **ARN** (Amazon Resource Name — a permanent ID that looks like `arn:aws:ec2:us-east-1:123456789012:instance/i-abc123`)
- The resource's **name** (if it has one)
- Which **AWS region** it lives in
- How much it **cost** you during a date range you choose
- A ready-to-use **AWS CLI delete command** for each resource, so you can clean up anything you no longer need

Think of it as a receipt + map of everything your AWS account is spending money on.

---

## Why Would You Use This?

- **Cost audits** — Find forgotten resources that are racking up charges (a stopped EC2 instance still costs money for its attached storage).
- **Cleanup** — Get delete commands for resources you no longer need, so you can paste them straight into your terminal.
- **Learning** — See a real-world snapshot of all the AWS services your project uses in one place.
- **Reporting** — Export the data as a spreadsheet-friendly TSV file or save it to a text file.

---

## Prerequisites

### 1. Python 3.10 or newer

Check your version:
```bash
python3 --version
```

### 2. The `boto3` library

`boto3` is the official Python SDK (software development kit) for AWS. Install it with:
```bash
pip install boto3
```

### 3. AWS credentials configured on your machine

The script needs permission to talk to your AWS account. The easiest way is the AWS CLI:

```bash
# Install the AWS CLI first if you haven't already:
# https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

aws configure
```

`aws configure` will prompt you for four things:

| Prompt | What to enter |
|---|---|
| AWS Access Key ID | Your IAM access key (starts with `AKIA...`) |
| AWS Secret Access Key | The secret that goes with your access key |
| Default region name | e.g. `us-east-1` |
| Default output format | Just press Enter (leave it blank) |

> **Where do I get an access key?** In the AWS Console, go to **IAM → Users → your user → Security credentials → Create access key**. Keep the secret somewhere safe — AWS will only show it once.

### 4. Required IAM permissions

Your AWS user or role needs at minimum these permissions:

| Permission | Why it's needed |
|---|---|
| `tag:GetResources` | Lists all resources via the Resource Groups Tagging API |
| `ec2:DescribeRegions` | Discovers which regions are active in your account |
| `ce:GetCostAndUsage` | Pulls cost data from Cost Explorer |

A quick way to satisfy this in a lab environment is attaching the `ReadOnlyAccess` managed policy to your IAM user.

---

## How the Script Works (Conceptual Overview)

The script performs three main tasks in sequence:

```
┌────────────────────────────────────────────────────────────┐
│  Step 1 — Fetch Cost Data                                   │
│  Calls AWS Cost Explorer to get spending by service         │
│  for your chosen date range.                                │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  Step 2 — Discover Resources (in parallel across regions)   │
│  Calls the Resource Groups Tagging API in every AWS         │
│  region simultaneously (using Python threads) to get a      │
│  full list of ARNs.                                         │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  Step 3 — Display Results                                   │
│  Groups resources by service, pairs each group with its     │
│  cost, prints the table, and appends delete commands.       │
└────────────────────────────────────────────────────────────┘
```

**Key concept — ARNs:** Every AWS resource has a globally unique ARN. Its format is:
```
arn:partition:service:region:account-id:resource-type/resource-id
     ↑         ↑       ↑      ↑          ↑
     aws      ec2   us-east-1 123456...  instance/i-abc123
```
The script uses the `service` segment (3rd field) to figure out what kind of resource it's dealing with.

---

## Running the Script

Navigate to the folder containing the script:
```bash
cd /path/to/awsResourceInventory
```

### Basic usage — scan everything this month

```bash
python3 aws_resource_inventory.py
```

**Example output:**
```
Fetching costs from 2026-06-01 to 2026-06-23...
Fetching resource ARNs across all regions (this may take ~30s)...
Excluded 14 free resource(s) (use --all to include them).

================================================================================
  Amazon EC2  —  $12.4800 (2026-06-01 to 2026-06-23)
================================================================================
  ARN                                                        NAME         REGION
  -------------------------------------------------------------------
  arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123def  web-server   us-east-1
  arn:aws:ec2:us-east-1:123456789012:volume/vol-0xyz789     web-storage  us-east-1

================================================================================
  Amazon Simple Storage Service  —  $0.0230 (2026-06-01 to 2026-06-23)
================================================================================
  ARN                                          NAME    REGION
  ----------------------------------------------------------
  arn:aws:s3:::my-project-bucket                       us-east-1

3 resource(s) across 2 service(s).

================================================================================
  AWS CLI DELETE COMMANDS  (chargeable resources only)
  WARNING: Review carefully before running. These actions are irreversible.
================================================================================

# Amazon EC2
aws ec2 terminate-instances --instance-ids i-0abc123def --region us-east-1  # web-server
aws ec2 delete-volume --volume-id vol-0xyz789 --region us-east-1  # web-storage

# Amazon Simple Storage Service
aws s3 rb s3://my-project-bucket --force
```

> **Note:** The first run can take around 30 seconds because the script checks every AWS region in parallel.

---

## Command-Line Options

| Flag | What it does | Example |
|---|---|---|
| `--start YYYY-MM-DD` | Start of the cost date range (default: first day of current month) | `--start 2026-05-01` |
| `--end YYYY-MM-DD` | End of the cost date range (default: today) | `--end 2026-06-01` |
| `--service SLUG` | Only show resources for one service | `--service ec2` |
| `--tsv` | Output in tab-separated format (good for Excel/Google Sheets) | `--tsv` |
| `--output FILENAME` | Save a copy of the output to a file | `--output report.txt` |
| `--all` | Include free resources (VPCs, security groups, IAM, etc.) | `--all` |

---

## Usage Examples

### Example 1 — Check costs for a previous month

```bash
python3 aws_resource_inventory.py --start 2026-05-01 --end 2026-06-01
```

Useful for reviewing what you spent in May before the next billing cycle hits.

---

### Example 2 — Filter to only EC2 resources

```bash
python3 aws_resource_inventory.py --service ec2
```

Scans only EC2 resources. Other valid service slugs: `s3`, `rds`, `lambda`, `dynamodb`, `ecs`, `eks`, `cloudfront`, `sqs`, `sns`.

---

### Example 3 — Export to a spreadsheet

```bash
python3 aws_resource_inventory.py --tsv --output inventory.tsv
```

The `--tsv` flag changes the output to tab-separated columns: `service`, `ce_cost_usd`, `arn`, `name`, `region`. You can open `inventory.tsv` directly in Excel or Google Sheets using **File → Import**.

Sample TSV output:
```
service	ce_cost_usd	arn	name	region
Amazon EC2	12.4800	arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123def	web-server	us-east-1
Amazon Simple Storage Service	0.0230	arn:aws:s3:::my-project-bucket		us-east-1
```

---

### Example 4 — Include everything (even free resources)

```bash
python3 aws_resource_inventory.py --all
```

By default the script hides resources that are always free — VPCs, subnets, security groups, IAM, CloudWatch, EventBridge. The `--all` flag brings them back.

---

### Example 5 — Save a full report to a file

```bash
python3 aws_resource_inventory.py --start 2026-06-01 --end 2026-06-23 --output june_report.txt
```

Output still prints to the terminal AND gets saved to `june_report.txt`. Helpful when you want to share the results with an instructor or teammate.

---

### Example 6 — Combining flags

Flags can be combined freely. This shows only Lambda resources for May, saved to a file:

```bash
python3 aws_resource_inventory.py --service lambda --start 2026-05-01 --end 2026-06-01 --output lambda_may.txt
```

---

## Understanding the Output

### Resource table (pretty-print mode)

```
================================================================================
  Amazon EC2  —  $12.4800 (2026-06-01 to 2026-06-23)
================================================================================
  ARN                                                        NAME         REGION
  ----------------------------------------------------------------
  arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123def  web-server   us-east-1
```

- Services are sorted **most expensive first**.
- Cost shown is the **total for that service** across your whole account — not per individual resource (AWS Cost Explorer doesn't break down to the individual resource level by default).
- `(no cost data)` means the service had zero cost in the selected period, which is normal for free-tier usage.

### Delete commands section

```
================================================================================
  AWS CLI DELETE COMMANDS  (chargeable resources only)
  WARNING: Review carefully before running. These actions are irreversible.
================================================================================

# Amazon EC2
aws ec2 terminate-instances --instance-ids i-0abc123def --region us-east-1
```

These are fully formed AWS CLI commands you can copy and paste. A few services (CloudFront, KMS) print multi-step comments instead because they require extra steps before deletion — the script explains exactly what to do.

> **Important:** Deleting cloud resources is permanent and immediate (with some exceptions like KMS). Always double-check the resource name and ID before running a delete command.

---

## What Resources Are Hidden by Default?

To keep the output focused on what costs money, the script hides these by default:

| Resource type | Why it's free |
|---|---|
| VPCs, subnets, route tables | No charge for the networking objects themselves |
| Security groups | Free — you pay for what's inside them, not the group |
| Internet gateways | Free |
| IAM (users, roles, policies) | Always free |
| CloudWatch Logs & Metrics | Basic metrics are free; log storage is charged but small |
| EventBridge rules | Free for default bus |
| AWS Backup | Free to configure, charged for storage used |
| EFS | Listed separately, often zero |

Use `--all` to see them anyway.

---

## Common Errors and Fixes

### `botocore.exceptions.NoCredentialsError`
**Cause:** AWS credentials aren't configured.
**Fix:** Run `aws configure` and enter your access key and secret.

---

### `botocore.exceptions.ClientError: AccessDenied`
**Cause:** Your IAM user doesn't have the required permissions.
**Fix:** Ask your AWS account administrator to attach the `ReadOnlyAccess` managed policy, or add the three specific permissions listed in the Prerequisites section.

---

### `ModuleNotFoundError: No module named 'boto3'`
**Cause:** The boto3 library isn't installed.
**Fix:** `pip install boto3`

---

### Cost Explorer returns an error about "subscription"
**Cause:** Cost Explorer must be enabled in your AWS account before first use. It's free but off by default.
**Fix:** In the AWS Console go to **Billing → Cost Explorer** and click **Enable Cost Explorer**. It takes up to 24 hours for data to appear.

---

### The scan takes more than 2 minutes
**Cause:** Some AWS regions are slow to respond or your network is slow.
**Fix:** This is normal — the script checks up to ~30 regions in parallel. Wait it out. If a specific region fails, the script silently skips it and continues.

---

## Key Concepts Glossary

| Term | Definition |
|---|---|
| **ARN** | Amazon Resource Name — a globally unique identifier for any AWS resource |
| **boto3** | The official Python library for interacting with AWS APIs |
| **Cost Explorer** | An AWS service that tracks and reports your spending by service, date, and more |
| **Resource Groups Tagging API** | An AWS API that lists resources across all services in a region, with their tags |
| **IAM** | Identity and Access Management — AWS's permission system for controlling who can do what |
| **Region** | A geographic cluster of AWS data centers (e.g., `us-east-1` = Northern Virginia) |
| **Blended Cost** | The combined cost after applying reserved instance or savings plan discounts |
| **TSV** | Tab-Separated Values — a text format similar to CSV that works well with spreadsheets |
| **Thread pool** | A Python technique for running many tasks at the same time (the script uses this to check all regions simultaneously) |
