#!/usr/bin/env python3
"""
List all AWS resources with ARNs, grouped by service, alongside cost data.

- Resource ARNs come from the Resource Groups Tagging API (no opt-in needed).
- Costs come from Cost Explorer grouped by service.
- Resources without tags are still included if discoverable.

Usage:
    python aws_resource_inventory.py
    python3 aws_resource_inventory.py --start 2026-05-01 --end 2026-06-01
    python aws_resource_inventory.py --service ec2
    python aws_resource_inventory.py --tsv
"""

import argparse
import boto3
from collections import defaultdict
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed


# Maps ARN service slug -> Cost Explorer display name (best-effort)
ARN_TO_CE_SERVICE = {
    "ec2":              "Amazon EC2",
    "s3":               "Amazon Simple Storage Service",
    "rds":              "Amazon Relational Database Service",
    "lambda":           "AWS Lambda",
    "dynamodb":         "Amazon DynamoDB",
    "elasticache":      "Amazon ElastiCache",
    "es":               "Amazon OpenSearch Service",
    "ecs":              "Amazon Elastic Container Service",
    "eks":              "Amazon Elastic Kubernetes Service",
    "cloudfront":       "Amazon CloudFront",
    "route53":          "Amazon Route 53",
    "sns":              "Amazon Simple Notification Service",
    "sqs":              "Amazon Simple Queue Service",
    "kinesis":          "Amazon Kinesis",
    "firehose":         "Amazon Kinesis Firehose",
    "secretsmanager":   "AWS Secrets Manager",
    "ssm":              "AWS Systems Manager",
    "logs":             "Amazon CloudWatch",
    "monitoring":       "Amazon CloudWatch",
    "events":           "Amazon EventBridge",
    "states":           "AWS Step Functions",
    "glue":             "AWS Glue",
    "athena":           "Amazon Athena",
    "redshift":         "Amazon Redshift",
    "elasticmapreduce": "Amazon EMR",
    "sagemaker":        "Amazon SageMaker",
    "codecommit":       "AWS CodeCommit",
    "codebuild":        "AWS CodeBuild",
    "codepipeline":     "AWS CodePipeline",
    "elasticloadbalancing": "AWS Elastic Load Balancing",
    "autoscaling":      "AWS Auto Scaling",
    "wafv2":            "AWS WAF",
    "acm":              "AWS Certificate Manager",
    "kms":              "AWS Key Management Service",
    "backup":           "AWS Backup",
    "transfer":         "AWS Transfer Family",
    "mq":               "Amazon MQ",
    "kafka":            "Amazon Managed Streaming for Apache Kafka",
    "dax":              "Amazon DynamoDB Accelerator (DAX)",
    "neptune":          "Amazon Neptune",
    "docdb":            "Amazon DocumentDB",
    "timestream":       "Amazon Timestream",
    "iot":              "AWS IoT",
    "appsync":          "AWS AppSync",
    "apigateway":       "Amazon API Gateway",
    "execute-api":      "Amazon API Gateway",
    "cognito-idp":      "Amazon Cognito",
    "cognito-identity": "Amazon Cognito",
    "amplify":          "AWS Amplify",
}


# Services (by ARN slug) that are free and excluded from the default view
FREE_SERVICE_SLUGS = {
    "backup",           # AWS Backup
    "logs",             # CloudWatch Logs
    "monitoring",       # CloudWatch Metrics
    "events",           # Amazon EventBridge
    "iam",              # IAM
    "elasticfilesystem",# Amazon EFS (S3 file-system)
}

# EC2 resource sub-types that are free (no hourly/usage charge on their own)
FREE_EC2_RESOURCE_TYPES = {
    "security-group",
    "vpc",
    "subnet",
    "route-table",
    "network-acl",
    "internet-gateway",
    "vpc-peering-connection",
    "dhcp-options",
    "prefix-list",
}


def is_chargeable(arn: str) -> bool:
    """Return True if this resource is likely to incur AWS charges."""
    parts = arn.split(":", 5)
    if len(parts) < 3:
        return True
    slug = parts[2]
    if slug in FREE_SERVICE_SLUGS:
        return False
    if slug == "ec2" and len(parts) == 6:
        resource = parts[5]
        resource_type = resource.split("/")[0] if "/" in resource else resource.split(":")[0]
        if resource_type in FREE_EC2_RESOURCE_TYPES:
            return False
    return True


def service_slug_from_arn(arn: str) -> str:
    """Extract the service slug from an ARN (e.g. 'ec2' from 'arn:aws:ec2:...')."""
    parts = arn.split(":")
    return parts[2] if len(parts) >= 3 else "unknown"


def delete_command_for_arn(arn: str, region: str) -> str:
    """Return the AWS CLI command to delete a resource given its ARN."""
    # ARN format: arn:partition:service:region:account:resource
    parts = arn.split(":", 5)
    if len(parts) < 6:
        return f"# Unable to generate delete command for: {arn}"

    service  = parts[2]
    resource = parts[5]  # e.g. "instance/i-abc123" or "function:my-func" or "bucket-name"

    # resource_type and resource_id handle both "/" and ":" separators
    if "/" in resource:
        resource_type, _, resource_id = resource.partition("/")
    elif ":" in resource:
        resource_type, _, resource_id = resource.partition(":")
    else:
        resource_type = resource
        resource_id   = resource

    r = f"--region {region}" if region else ""

    if service == "ec2":
        if resource_type == "instance":
            return f"aws ec2 terminate-instances --instance-ids {resource_id} {r}"
        if resource_type == "volume":
            return f"aws ec2 delete-volume --volume-id {resource_id} {r}"
        if resource_type == "snapshot":
            return f"aws ec2 delete-snapshot --snapshot-id {resource_id} {r}"
        if resource_type == "security-group":
            return f"aws ec2 delete-security-group --group-id {resource_id} {r}"
        if resource_type == "subnet":
            return f"aws ec2 delete-subnet --subnet-id {resource_id} {r}"
        if resource_type == "vpc":
            return f"aws ec2 delete-vpc --vpc-id {resource_id} {r}"
        if resource_type == "internet-gateway":
            return f"aws ec2 delete-internet-gateway --internet-gateway-id {resource_id} {r}"
        if resource_type == "natgateway":
            return f"aws ec2 delete-nat-gateway --nat-gateway-id {resource_id} {r}"
        if resource_type == "elastic-ip":
            return f"aws ec2 release-address --allocation-id {resource_id} {r}"
        if resource_type == "key-pair":
            return f"aws ec2 delete-key-pair --key-name {resource_id} {r}"
        if resource_type == "image":
            return f"aws ec2 deregister-image --image-id {resource_id} {r}"

    if service == "s3":
        bucket = resource_id or resource_type
        return f"aws s3 rb s3://{bucket} --force"

    if service == "rds":
        if resource_type == "db":
            return f"aws rds delete-db-instance --db-instance-identifier {resource_id} --skip-final-snapshot {r}"
        if resource_type == "cluster":
            return f"aws rds delete-db-cluster --db-cluster-identifier {resource_id} --skip-final-snapshot {r}"
        if resource_type == "snapshot":
            return f"aws rds delete-db-snapshot --db-snapshot-identifier {resource_id} {r}"

    if service == "lambda":
        return f"aws lambda delete-function --function-name {resource_id or resource_type} {r}"

    if service == "dynamodb":
        return f"aws dynamodb delete-table --table-name {resource_id} {r}"

    if service == "elasticache":
        if resource_type == "cluster":
            return f"aws elasticache delete-cache-cluster --cache-cluster-id {resource_id} {r}"
        if resource_type == "replicationgroup":
            return f"aws elasticache delete-replication-group --replication-group-id {resource_id} {r}"

    if service == "ecs":
        if resource_type == "cluster":
            return f"aws ecs delete-cluster --cluster {resource_id} {r}"
        if resource_type == "service":
            # resource_id is "cluster-name/service-name"
            cluster, _, svc_name = resource_id.partition("/")
            if svc_name:
                return f"aws ecs delete-service --cluster {cluster} --service {svc_name} --force {r}"
            return f"aws ecs delete-service --service {resource_id} --force {r}"

    if service == "eks":
        return f"aws eks delete-cluster --name {resource_id} {r}"

    if service == "elasticloadbalancing":
        return f"aws elbv2 delete-load-balancer --load-balancer-arn {arn}"

    if service == "cloudfront":
        dist_id = resource_id or resource_type
        return (f"# CloudFront requires an ETag first:\n"
                f"# ETAG=$(aws cloudfront get-distribution --id {dist_id} --query 'ETag' --output text)\n"
                f"# aws cloudfront delete-distribution --id {dist_id} --if-match $ETAG")

    if service == "route53":
        if resource_type == "hostedzone":
            return f"aws route53 delete-hosted-zone --id {resource_id}"

    if service == "sns":
        return f"aws sns delete-topic --topic-arn {arn}"

    if service == "sqs":
        account = parts[4]
        return f"aws sqs delete-queue --queue-url https://sqs.{region}.amazonaws.com/{account}/{resource_id} {r}"

    if service == "logs":
        log_group = resource.replace("log-group:", "").split(":")[0]
        return f"aws logs delete-log-group --log-group-name {log_group} {r}"

    if service == "secretsmanager":
        return f"aws secretsmanager delete-secret --secret-id {arn} --force-delete-without-recovery {r}"

    if service == "kms":
        return (f"# KMS keys cannot be deleted immediately — schedule for deletion (7–30 days):\n"
                f"# aws kms schedule-key-deletion --key-id {resource_id} --pending-window-in-days 7 {r}")

    if service == "ecr":
        return f"aws ecr delete-repository --repository-name {resource_id} --force {r}"

    if service == "glue":
        if resource_type == "database":
            return f"aws glue delete-database --name {resource_id} {r}"
        if resource_type == "job":
            return f"aws glue delete-job --job-name {resource_id} {r}"
        if resource_type == "crawler":
            return f"aws glue delete-crawler --name {resource_id} {r}"

    if service == "states":
        return f"aws stepfunctions delete-state-machine --state-machine-arn {arn}"

    if service == "kinesis":
        return f"aws kinesis delete-stream --stream-name {resource_id} {r}"

    if service == "sagemaker":
        if resource_type == "notebook-instance":
            return f"aws sagemaker delete-notebook-instance --notebook-instance-name {resource_id} {r}"
        if resource_type == "endpoint":
            return f"aws sagemaker delete-endpoint --endpoint-name {resource_id} {r}"

    if service == "redshift":
        if resource_type == "cluster":
            return f"aws redshift delete-cluster --cluster-identifier {resource_id} --skip-final-cluster-snapshot {r}"

    if service == "kafka":
        return f"aws kafka delete-cluster --cluster-arn {arn}"

    if service == "mq":
        return f"aws mq delete-broker --broker-id {resource_id} {r}"

    if service == "apigateway":
        return f"aws apigateway delete-rest-api --rest-api-id {resource_id} {r}"

    if service == "appsync":
        return f"aws appsync delete-graphql-api --api-id {resource_id} {r}"

    if service == "cognito-idp":
        return f"aws cognito-idp delete-user-pool --user-pool-id {resource_id} {r}"

    return f"# No known delete command for service '{service}': {arn}"


def get_all_regions() -> list[str]:
    ec2 = boto3.client("ec2", region_name="us-east-1")
    resp = ec2.describe_regions(
        Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
    )
    return [r["RegionName"] for r in resp["Regions"]]


def get_resources_in_region(region: str, service_filter: str = None) -> list[dict]:
    """Return all tagged resources in a region via Resource Groups Tagging API."""
    client = boto3.client("resourcegroupstaggingapi", region_name=region)
    resources = []
    kwargs = {}
    if service_filter:
        kwargs["ResourceTypeFilters"] = [service_filter]
    try:
        paginator = client.get_paginator("get_resources")
        for page in paginator.paginate(**kwargs):
            for r in page.get("ResourceTagMappingList", []):
                arn = r["ResourceARN"]
                tags = {t["Key"]: t["Value"] for t in r.get("Tags", [])}
                name = tags.get("Name") or tags.get("name") or ""
                resources.append({"arn": arn, "name": name, "region": region})
    except Exception:
        pass  # Region may not support the service
    return resources


def get_all_resources(regions: list[str], service_filter: str = None) -> list[dict]:
    """Fetch resources from all regions in parallel."""
    all_resources = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(get_resources_in_region, r, service_filter): r for r in regions}
        for future in as_completed(futures):
            all_resources.extend(future.result())
    return all_resources


def get_service_costs(start: str, end: str) -> dict[str, float]:
    """Return {ce_service_name: total_cost} for the date range."""
    client = boto3.client("ce", region_name="us-east-1")
    costs = defaultdict(float)
    next_token = None
    while True:
        kwargs = dict(
            TimePeriod={"Start": start, "End": end},
            Granularity="MONTHLY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            Filter={
                "Not": {
                    "Dimensions": {
                        "Key": "RECORD_TYPE",
                        "Values": ["Credit", "Refund", "Tax", "SavingsPlanNegation"],
                    }
                }
            },
        )
        if next_token:
            kwargs["NextPageToken"] = next_token
        resp = client.get_cost_and_usage(**kwargs)
        for period in resp.get("ResultsByTime", []):
            for group in period.get("Groups", []):
                svc = group["Keys"][0]
                costs[svc] += float(group["Metrics"]["BlendedCost"]["Amount"])
        next_token = resp.get("NextPageToken")
        if not next_token:
            break
    return dict(costs)


def main():
    today = date.today()
    default_start = today.replace(day=1).isoformat()
    default_end = today.isoformat()

    parser = argparse.ArgumentParser(description="List AWS resources with ARNs and costs")
    parser.add_argument("--start", default=default_start, help="Start date YYYY-MM-DD (default: first of month)")
    parser.add_argument("--end", default=default_end, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--service", help="Filter by ARN service slug (e.g. ec2, s3, rds, lambda)")
    parser.add_argument("--tsv", action="store_true", help="Output as tab-separated values")
    parser.add_argument("--output", help="Write output to a text file (e.g. report.txt)")
    parser.add_argument("--all", dest="show_all", action="store_true",
                        help="Include all resources (default excludes free resources such as "
                             "security groups, VPCs, CloudWatch, EventBridge, IAM, Backup, EFS)")
    args = parser.parse_args()

    import sys
    import io

    # If --output is set, tee stdout to the file
    if args.output:
        file_out = open(args.output, "w")
        original_stdout = sys.stdout

        class Tee:
            def write(self, data):
                original_stdout.write(data)
                file_out.write(data)
            def flush(self):
                original_stdout.flush()
                file_out.flush()

        sys.stdout = Tee()

    print(f"Fetching costs from {args.start} to {args.end}...")
    try:
        costs = get_service_costs(args.start, args.end)
    except Exception as e:
        print(f"Error fetching costs: {e}")
        raise SystemExit(1)

    print("Fetching resource ARNs across all regions (this may take ~30s)...")
    try:
        regions = get_all_regions()
        resources = get_all_resources(regions, args.service)
    except Exception as e:
        print(f"Error fetching resources: {e}")
        raise SystemExit(1)

    if not resources:
        print("No resources found.")
        return

    if not args.show_all:
        before = len(resources)
        resources = [r for r in resources if is_chargeable(r["arn"])]
        excluded = before - len(resources)
        if excluded:
            print(f"Excluded {excluded} free resource(s) (use --all to include them).\n")

    if not resources:
        print("No chargeable resources found.")
        return

    # Group resources by ARN service slug
    by_slug: dict[str, list] = defaultdict(list)
    for r in resources:
        slug = service_slug_from_arn(r["arn"])
        by_slug[slug].append(r)

    if args.tsv:
        print("service\tce_cost_usd\tarn\tname\tregion")
        for slug, items in sorted(by_slug.items()):
            ce_name = ARN_TO_CE_SERVICE.get(slug, slug)
            cost = costs.get(ce_name, 0.0)
            for r in sorted(items, key=lambda x: x["arn"]):
                print(f"{ce_name}\t{cost:.4f}\t{r['arn']}\t{r['name']}\t{r['region']}")
        return

    # Pretty print
    for slug, items in sorted(by_slug.items(), key=lambda kv: -costs.get(ARN_TO_CE_SERVICE.get(kv[0], ""), 0.0)):
        ce_name = ARN_TO_CE_SERVICE.get(slug, slug)
        cost = costs.get(ce_name, 0.0)
        cost_str = f"${cost:.4f}" if cost else "(no cost data)"

        print(f"\n{'='*80}")
        print(f"  {ce_name}  —  {cost_str} ({args.start} to {args.end})")
        print(f"{'='*80}")

        col_arn  = max(len("ARN"),  max(len(r["arn"])  for r in items))
        col_name = max(len("NAME"), max(len(r["name"]) for r in items)) if any(r["name"] for r in items) else 0
        col_reg  = max(len("REGION"), max(len(r["region"]) for r in items))

        if col_name:
            header = f"  {'ARN':<{col_arn}}  {'NAME':<{col_name}}  {'REGION':<{col_reg}}"
        else:
            header = f"  {'ARN':<{col_arn}}  {'REGION':<{col_reg}}"
        print(header)
        print("  " + "-" * (len(header) - 2))

        for r in sorted(items, key=lambda x: x["arn"]):
            if col_name:
                print(f"  {r['arn']:<{col_arn}}  {r['name']:<{col_name}}  {r['region']:<{col_reg}}")
            else:
                print(f"  {r['arn']:<{col_arn}}  {r['region']:<{col_reg}}")

    print(f"\n{len(resources)} resource(s) across {len(by_slug)} service(s).")

    # Delete commands (only for chargeable resources)
    print(f"\n{'='*80}")
    print("  AWS CLI DELETE COMMANDS  (chargeable resources only)")
    print(f"  WARNING: Review carefully before running. These actions are irreversible.")
    print(f"{'='*80}\n")
    for slug, items in sorted(by_slug.items(), key=lambda kv: -costs.get(ARN_TO_CE_SERVICE.get(kv[0], ""), 0.0)):
        ce_name = ARN_TO_CE_SERVICE.get(slug, slug)
        print(f"# {ce_name}")
        for r in sorted(items, key=lambda x: x["arn"]):
            cmd = delete_command_for_arn(r["arn"], r["region"])
            if cmd.startswith("# No known delete command"):
                continue
            label = f"  # {r['name']}" if r["name"] else ""
            print(f"{cmd}{label}")
        print()

    if args.output:
        sys.stdout = original_stdout
        file_out.close()
        print(f"Output written to {args.output}")


if __name__ == "__main__":
    main()
