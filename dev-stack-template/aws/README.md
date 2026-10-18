# Private models on Amazon Bedrock (Sydney)

The stack's private models (`private-coder`, `private-coder-lite`, `private-general`,
`private-reasoner`, `private-glm`) run on Amazon Bedrock in **ap-southeast-2 (Sydney)**. AWS says Bedrock
does not store or log your prompts and completions, does not use them to train models, and
does not share them with the model makers (Qwen, DeepSeek).

One-time setup, about 15 minutes. You need a normal AWS account. An AWS Builder ID is a
different login and cannot use Bedrock.

## 1. AWS account

1. Create an account at https://aws.amazon.com (needs a card). New accounts get free-plan
   credit; small Bedrock usage like this stack's fits well inside it.
2. Turn on MFA for the root user (IAM → Security recommendations). Use root only for this
   setup.
3. In the top-right region menu, choose **Asia Pacific (Sydney) ap-southeast-2**. Stay in
   Sydney for every step below.

## 2. Try each model once

Bedrock console → **Playground → Chat**. Pick each model and send "hi":

| Stack name | Bedrock model | Model ID |
|---|---|---|
| `private-coder` | Qwen3 Coder Next | `qwen.qwen3-coder-next` |
| `private-coder-lite` | Qwen3 Coder 30B A3B | `qwen.qwen3-coder-30b-a3b-v1:0` |
| `private-general` | Qwen3 235B A22B 2507 | `qwen.qwen3-235b-a22b-2507-v1:0` |
| `private-reasoner` | DeepSeek V3.2 | `deepseek.v3.2` |
| `private-glm` | GLM 5 | `zai.glm-5` |

This completes any one-time enablement for your account, so the limited user below never
needs extra permissions. If a model says it is not available on your plan, note which one;
the stack still works with the others (its fallback just won't).

## 3. Create the limited user and the budget

CloudFormation → **Create stack → With new resources** → *Upload a template file* →
`aws/bedrock-access.yaml`.

- **BudgetEmail**: where alerts go. Confirm the subscription email AWS sends.
- **MonthlyBudgetUSD**: default 10. Alerts at 50% and 100% of actual spend, and when the
  forecast passes 100%. This is for the whole account, so it also catches anything else.
- Tick *"I acknowledge that AWS CloudFormation might create IAM resources with custom
  names"* and create the stack.

The stack refuses to deploy outside Sydney. It creates the user `devstack-bedrock`, which can
call **only** those five models **only** in Sydney: no console access, no other services.

Command-line alternative (needs the AWS CLI, signed in as an admin):

```bash
aws cloudformation deploy --region ap-southeast-2 \
  --template-file aws/bedrock-access.yaml --stack-name devstack-bedrock \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides BudgetEmail=you@example.com MonthlyBudgetUSD=10
aws iam create-access-key --user-name devstack-bedrock
```

## 4. Access key → .env

Open the stack's **Outputs → CreateAccessKeyUrl** (IAM → Users → devstack-bedrock →
Security credentials) → **Create access key** → use case *Application running outside AWS*.
Copy both values into the stack's `.env`:

```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

## 5. Check

```bash
just litellm          # in one terminal
just check-models     # in another: one tiny answer + one tool call per private model
```

Each line should say `answer ok` and `tools ok`. `tools NOT USED` means the model answered
without calling the tool; that model is fine for chat but weaker for agent tools.

## Good to know

- **Region is pinned** in `litellm_config.yaml` (`aws_region_name: ap-southeast-2`), not read
  from an environment variable, so requests cannot drift to another region.
- **Private stays private**: a private model only falls back to another private model, never
  to OpenRouter.
- **Logging**: Bedrock's model invocation logging is off unless you turn it on; leave it off.
  CloudTrail records that a call happened (time, model, user), not the prompt.
- **Costs** (Sydney on-demand, October 2026, per million tokens in/out): Qwen3 Coder Next
  $0.515/$1.236, Qwen3 Coder 30B $0.155/$0.618, Qwen3 235B $0.227/$0.906, DeepSeek V3.2
  $0.639/$1.906, GLM 5 $1.03/$3.30. That is about 3% more than the US regions. LiteLLM also caps Bedrock at $3/day.
- **Rotate the key** every few months, and deactivate it in IAM at once if it ever leaks.
- **Adding a model**: add it to `litellm_config.yaml` *and* to the policy's `Resource` list in
  `bedrock-access.yaml`, then update the stack.
- **GLM 5.3** is newer than GLM 5 but on Bedrock it runs only through a *global* profile
  (requests may be processed in any region worldwide) and only for eligible accounts, so it
  is not used as a private model. It is available as `open-glm` through OpenRouter.
- **Qwen3 Coder 30B** is marked Legacy by AWS (end of life 2027-03-30); replace it before then.
