# Same-host benchmark

Run `python3 deploy.py --profile god-of-code-kit` from WSL with the two Sydney Lambda images deployed. The benchmark launches one 8 GiB EC2 instance for up to 45 minutes under an active AWS Free Plan. EBS persists after the host stops. Public IPv4 enables outbound AWS traffic. The security group permits no inbound connections. Use Systems Manager Run Command to inspect the containers or issue a request to port 8080 on the host loopback.

Laya uses the real checkpoint. LiteLLM calls it on a private Docker network and dispatches to a synthetic provider on the same host. The fixture uses no provider keys or shared chat requests. The two Lambda images remain the source for the containers.

Pipe `probe.py` into `docker exec -i litellm python -` to verify three streaming requests and their Laya scores. Use `docker logs laya` for model startup time and `docker stats --no-stream laya litellm` for container memory.
