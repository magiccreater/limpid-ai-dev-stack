# Laya decision pilot in Sydney

This stack serves the pinned public Laya typed-decisions checkpoint over the AWS Lambda Invoke API. The request and response use the kit's `/v1/systemone` decision body. The endpoint uses the caller's temporary AWS credentials. The function has no public URL, uses no OpenRouter calls, and downloads no weights at runtime.

The deployment uses one private ECR repository, a single on-demand Lambda (3 GiB, 45 seconds, concurrency one), a three-day log group, and a DynamoDB monthly counter with a default of 30 model requests. The execution role can write only this counter and log group. The image contains only public model files and runtime code. The model receives bounded text and typed questions. Requests and responses are kept out of application logs. Pass only public or synthetic patches from the kit.

## Build and deploy from WSL

Run the commands from this directory in WSL.

```bash
docker build --platform linux/amd64 -t limpid-laya-decisions:pilot .
docker run --rm --network none --read-only --tmpfs /tmp:rw \
  --memory 3g --cpus 1.5 --user 1000:1000 --entrypoint python3 \
  limpid-laya-decisions:pilot -c 'import service; result=service.handle({"state":"The test passed.","questions":{"passed":{"type":"noul","instructions":"Did the test pass?"}}},None); print(result); assert "answers" in result'
python3 deploy.py --profile god-of-code-kit --project YOUR_PROJECT_ID
```

Deployment verifies the selected project and active AWS Free Plan before creating or uploading resources, then deploys by immutable image digest. ECR storage can consume Free Plan credits beyond the private-repository storage allowance. The pilot stays within the Free Plan and has no instance or provisioned concurrency to keep running between checks. The plan expires when its plan period or credit balance runs out.

## Use

Use `god decision route --kind bugfix --scope small` in God of Code Kit for a capability recommendation. Use `god decision check --public` for a public or synthetic patch after setting that repository's deterministic readiness checks. Decisions are advisory while the checkpoint is evaluated on labelled coding tasks. The pilot does not train on agent memory.

The AWS stack name is `limpid-laya-decisions` in `ap-southeast-2`. Its private image and pilot resources are scoped to that stack.
