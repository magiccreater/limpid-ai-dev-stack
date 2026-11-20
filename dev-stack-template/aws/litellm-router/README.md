# Sydney LiteLLM with Laya routing

```text
IDE / WSL  ->  IAM Chat Completions endpoint  ->  LiteLLM on Sydney Lambda
                                                     |
                                                     +-> Laya Lambda [task metadata and score]
                                                     |
                                                     +-> approved free model/API -> streamed result
```

The normal coding request is the only AWS request needed from the client. LiteLLM invokes Laya inside Sydney using its execution role. Laya gets a task category and size derived from the first user message. LiteLLM ranks the approved pool using the returned tier and confidence. It uses rules on uncertainty or after a 4.5-second decision timeout. A warm router caches successful decisions for five minutes. It retries at most one alternate free route before starting the response. The coding request remains subject to the original shared monthly DynamoDB counter. The public pilot accepts `private-coder-public` for OpenRouter only and `public-free-coder` for the approved multi-provider pool. Private requests are rejected.

The image uses the repository's `litellm_config.yaml` as its model catalog. OpenRouter `:free` entries require tool support and a provider price ceiling of zero. `openrouter/free` is the last fallback with the same restrictions. Only OpenRouter is enabled by default because its encrypted key is already in the Sydney stack. Groq, GitHub Models, Cerebras and SambaNova entries require an approved free-only provider account and its own Standard SecureString. An advertised zero cost in YAML does not enforce an external provider's billing plan.

| Provider | Sydney SSM SecureString |
|---|---|
| OpenRouter | `/limpid/chat-gateway/openrouter` |
| Groq | `/limpid/litellm/free/groq` |
| GitHub Models | `/limpid/litellm/free/github` |
| Cerebras | `/limpid/litellm/free/cerebras` |
| SambaNova | `/limpid/litellm/free/sambanova` |

## Deploy from WSL

Use an active AWS Free Plan with the original Sydney gateway and Laya stacks deployed.

```bash
cd dev-stack-template/aws/litellm-router
python3 deploy.py build
python3 deploy.py deploy --profile god-of-code-kit --project YOUR_PROJECT_ID
```

To enable additional approved providers, pass `--free-providers openrouter,groq` (for example) after configuring their corresponding keys. The deployment builds from an explicit allowlist of files, checks AWS identity and the Free Plan, and publishes a private image by digest.

## Use from WSL

```bash
export GOD_AWS_PROFILE=god-of-code-kit
export GOD_AWS_STACK=limpid-litellm-router
god doctor
god task "Add tests to this public sample" --single --public-free
```

Use `--public-openrouter` to authorize OpenRouter only. The signed API response includes the selected LiteLLM alias in `X-Limpid-Route` and the decision source in `X-Limpid-Decision`. The `X-Limpid-Decision-Score` header is present when Laya returns a usable score. Use the existing `limpid-chat-gateway` stack for the original Bedrock-only profile. Signed requests share that stack's 20-request default cap.
