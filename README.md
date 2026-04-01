# mtproxy_docker

This repository builds the official
[Telegram MTProxy](https://github.com/TelegramMessenger/MTProxy) from source and
wraps the runtime steps from the upstream README into a container entrypoint.

The image is pinned to `linux/amd64` because the upstream `Makefile` uses
x86-specific compiler flags such as `-march=core2` and SSE options.

At container start it will:

- download `proxy-secret`
- download the current `proxy-multi.conf`
- generate a client secret if you do not provide one
- start `mtproto-proxy` with the required arguments
- refresh `proxy-multi.conf` every 24 hours and restart `mtproto-proxy`

When `MTPROXY_PUBLIC_HOST` is set, the entrypoint also resolves:

- the container's local IPv4 address
- the public IPv4 address behind `MTPROXY_PUBLIC_HOST`

and passes them to MTProxy as `--nat-info <local-ip>:<public-ip>`.

## Build

```bash
docker build -t mtproxy .
```

Published image path:

```bash
ghcr.io/astrot1988/mtproxy_docker:latest
```

### Optional build args

- `MTPROXY_REPO` defaults to `https://github.com/TelegramMessenger/MTProxy`
- `MTPROXY_REF` defaults to `master`

## Run

```bash
docker run -d \
  --name mtproxy \
  --restart unless-stopped \
  -p 443:443 \
  -p 127.0.0.1:8888:8888 \
  -p 127.0.0.1:8080:8080 \
  -v mtproxy-data:/data \
  -e MTPROXY_PUBLIC_HOST=YOUR_SERVER_IP_OR_DNS \
  mtproxy
```

Then inspect the logs to get the generated client secret and Telegram links:

```bash
docker logs mtproxy
```

The stats web UI will be available at:

```bash
http://127.0.0.1:8080/
```

## Run With Compose

Create a `.env` file or export variables in your shell, then start:

```bash
docker compose up -d
docker compose logs -f mtproxy
```

The repository includes [docker-compose.yml](/Users/aleksejlutovinov/Projects/quank-mvp/mtproxy_docker/docker-compose.yml) with persistent `/data` storage and the same default ports as the plain `docker run` example.

## Environment variables

- `MTPROXY_PUBLIC_HOST`: public IP or DNS name used for the Telegram link output
- `MTPROXY_PORT`: public MTProxy port, default `443`
- `MTPROXY_STATS_PORT`: local stats port, default `8888`
- `MTPROXY_UI_PORT`: local stats UI port, default `8080`
- `SECRET`: one or more comma-separated 32-character hex secrets; this is the preferred setting
- `MTPROXY_TAG`: proxy tag from `@MTProxybot`
- `MTPROXY_WORKERS`: number of worker processes, default `1`
- `MTPROXY_HTTP_STATS`: enable `--http-stats`, default `true`
- `MTPROXY_REFRESH_INTERVAL`: refresh interval in seconds, default `86400`

## Notes

- Upstream recommends refreshing `proxy-multi.conf` regularly. This image refreshes it on startup and then every 24 hours by default, restarting `mtproto-proxy` after the refresh.
- If `SECRET` is not set, the container generates one secret and persists it in `/data/client-secret`.
- If `SECRET` contains multiple comma-separated values, the container passes each of them as a separate `-S` argument to `mtproto-proxy`.
- The runtime enables `--allow-skip-dh` and sets `-C 60000` to better match the behavior of the official MTProxy container image.
- The runtime enables `--http-stats` by default; set `MTPROXY_HTTP_STATS=false` to disable it.
- The same container also serves a dark stats dashboard on `MTPROXY_UI_PORT`, backed by the local MTProxy `http-stats` endpoint.
- To enable random padding in clients, use the logged `dd...` variant of the secret or link.

## CI/CD

GitHub Actions in [.github/workflows/docker.yml](/Users/aleksejlutovinov/Projects/quank-mvp/mtproxy_docker/.github/workflows/docker.yml) will:

- build the image on every push, pull request, and manual run
- publish to `ghcr.io/astrot1988/mtproxy_docker` on pushes to `master`
- publish version tags on git tags like `v1.0.0`

Repository settings should allow GitHub Actions to write packages with `GITHUB_TOKEN`.
