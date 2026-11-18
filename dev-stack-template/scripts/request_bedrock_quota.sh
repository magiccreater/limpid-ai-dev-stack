#!/usr/bin/env bash
# Request a Service Quota increase for Amazon Bedrock foundation models (e.g. Qwen3 Coder Next)
# Usage: ./request_bedrock_quota.sh [--model NAME] [--tpm VALUE] [--region REGION] [--profile PROFILE]
set -euo pipefail

REGION="ap-southeast-2"
MODEL_PATTERN="Qwen"
DESIRED_TPM=200000
PROFILE="${AWS_PROFILE:-chintanai-lenovo-mini}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)   MODEL_PATTERN="$2"; shift 2 ;;
    --tpm)     DESIRED_TPM="$2"; shift 2 ;;
    --region)  REGION="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--model NAME] [--tpm VALUE] [--region REGION] [--profile PROFILE]"
      echo "Example: $0 --model 'Qwen3 Coder Next' --tpm 200000 --profile chintanai-lenovo-mini"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

echo "=== Amazon Bedrock Service Quota Request ==="
echo "Model search: $MODEL_PATTERN"
echo "Desired TPM:  $DESIRED_TPM"
echo "Region:       $REGION"
echo "Profile:      $PROFILE"
echo ""

echo "Fetching Bedrock quotas in $REGION..."
QUOTAS_JSON=$(aws service-quotas list-service-quotas \
  --service-code bedrock \
  --region "$REGION" \
  --profile "$PROFILE" 2>/dev/null || true)

if [[ -z "$QUOTAS_JSON" ]] || echo "$QUOTAS_JSON" | grep -q "AccessDenied"; then
  echo "Note: Direct Service Quotas API query returned AccessDenied or empty."
  echo "Your IAM user ($PROFILE) needs the following IAM permissions:"
  echo "  - servicequotas:ListServiceQuotas"
  echo "  - servicequotas:RequestServiceQuotaIncrease"
  echo ""
  echo "To request in the AWS Console instead:"
  echo "  1. Open: https://${REGION}.console.aws.amazon.com/servicequotas/home/services/bedrock/quotas"
  echo "  2. Search for: '$MODEL_PATTERN' or 'Tokens per minute'"
  echo "  3. Click 'Request quota increase' and enter: $DESIRED_TPM"
  echo ""
  echo "Alternatively, deploy aws/bedrock-service-quota.yaml in CloudFormation with your target QuotaCode."
  exit 0
fi

MATCHING=$(echo "$QUOTAS_JSON" | jq -r --arg pat "$MODEL_PATTERN" '
  .Quotas[] | select(.QuotaName | test($pat; "i")) | select(.QuotaName | test("token"; "i")) |
  "\(.QuotaCode)\t\(.Value)\t\(.QuotaName)"
')

if [[ -z "$MATCHING" ]]; then
  echo "No token quota found matching '$MODEL_PATTERN'. Available quotas for Bedrock in $REGION:"
  echo "$QUOTAS_JSON" | jq -r '.Quotas[] | select(.QuotaName | test("token"; "i")) | "\(.QuotaCode) - \(.QuotaName) (Current: \(.Value))"' | head -n 15
  exit 1
fi

while IFS=$'\t' read -r code current name; do
  echo "Found Quota: $name"
  echo "  Quota Code: $code"
  echo "  Current Limit: $current"
  echo "  Requesting increase to: $DESIRED_TPM..."
  aws service-quotas request-service-quota-increase \
    --service-code bedrock \
    --quota-code "$code" \
    --desired-value "$DESIRED_TPM" \
    --region "$REGION" \
    --profile "$PROFILE"
  echo "  Request successfully submitted!"
done <<< "$MATCHING"

echo ""
echo "You can check status at: https://${REGION}.console.aws.amazon.com/servicequotas/home/services/bedrock/quotas"
