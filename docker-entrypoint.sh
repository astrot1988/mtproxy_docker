#!/bin/sh

set -eu

DATA_DIR="${MTPROXY_DATA_DIR:-/data}"
PROXY_SECRET_FILE="${MTPROXY_PROXY_SECRET_FILE:-${DATA_DIR}/proxy-secret}"
PROXY_CONFIG_FILE="${MTPROXY_PROXY_CONFIG_FILE:-${DATA_DIR}/proxy-multi.conf}"
CLIENT_SECRET_FILE="${MTPROXY_CLIENT_SECRET_FILE:-${DATA_DIR}/client-secret}"
SECRET_VALUE="${SECRET:-}"
CLIENT_SECRET="${MTPROXY_CLIENT_SECRET:-}"
PUBLIC_HOST="${MTPROXY_PUBLIC_HOST:-}"
PUBLIC_PORT="${MTPROXY_PORT:-443}"
STATS_PORT="${MTPROXY_STATS_PORT:-8888}"
RUN_USER="${MTPROXY_USER:-nobody}"
WORKERS="${MTPROXY_WORKERS:-1}"
TAG="${MTPROXY_TAG:-}"
REFRESH_INTERVAL="${MTPROXY_REFRESH_INTERVAL:-86400}"

mkdir -p "${DATA_DIR}"

download_file() {
    url="$1"
    output="$2"
    tmp_file="${output}.tmp"

    curl --fail --show-error --silent --location "$url" -o "${tmp_file}"
    mv "${tmp_file}" "${output}"
}

refresh_runtime_files() {
    download_file "https://core.telegram.org/getProxySecret" "${PROXY_SECRET_FILE}"
    download_file "https://core.telegram.org/getProxyConfig" "${PROXY_CONFIG_FILE}"
}

if [ -n "${CLIENT_SECRET}" ]; then
    printf '%s' "${CLIENT_SECRET}" > "${CLIENT_SECRET_FILE}"
elif [ ! -s "${CLIENT_SECRET_FILE}" ]; then
    openssl rand -hex 16 > "${CLIENT_SECRET_FILE}"
fi

if [ -z "${SECRET_VALUE}" ]; then
    SECRET_VALUE="${CLIENT_SECRET:-$(tr -d '\r\n' < "${CLIENT_SECRET_FILE}")}"
fi

SECRET_VALUE="$(printf '%s' "${SECRET_VALUE}" | tr -d '\r\n' | sed 's/[[:space:]]//g')"

if [ -z "${SECRET_VALUE}" ]; then
    echo "Secret list is empty" >&2
    exit 1
fi

OLD_IFS="${IFS}"
IFS=','
set -- ${SECRET_VALUE}
IFS="${OLD_IFS}"

if [ "$#" -eq 0 ]; then
    echo "Secret list is empty" >&2
    exit 1
fi

SECRETS="$*"

start_proxy() {
    set -- \
        /usr/local/bin/mtproto-proxy \
        -u "${RUN_USER}" \
        -p "${STATS_PORT}" \
        -H "${PUBLIC_PORT}" \
        --aes-pwd "${PROXY_SECRET_FILE}" "${PROXY_CONFIG_FILE}" \
        -M "${WORKERS}"

    OLD_IFS="${IFS}"
    IFS=' '
    for secret in ${SECRETS}; do
        set -- "$@" -S "${secret}"
    done
    IFS="${OLD_IFS}"

    if [ -n "${TAG}" ]; then
        set -- "$@" -P "${TAG}"
    fi

    if [ -n "${MTPROXY_EXTRA_ARGS:-}" ]; then
        # shellcheck disable=SC2086
        set -- "$@" ${MTPROXY_EXTRA_ARGS}
    fi

    "$@" &
    PROXY_PID=$!
}

stop_proxy() {
    if kill -0 "${PROXY_PID}" 2>/dev/null; then
        kill -TERM "${PROXY_PID}" 2>/dev/null || true
        wait "${PROXY_PID}" || true
    fi
}

terminate() {
    stop_proxy
    exit 0
}

trap terminate INT TERM

secret_index=1
OLD_IFS="${IFS}"
IFS=' '
for secret in ${SECRETS}; do
    echo "MTProxy client secret ${secret_index}: ${secret}"
    echo "MTProxy client secret ${secret_index} with padding: dd${secret}"

    if [ -n "${PUBLIC_HOST}" ]; then
        echo "Telegram link ${secret_index}: tg://proxy?server=${PUBLIC_HOST}&port=${PUBLIC_PORT}&secret=${secret}"
        echo "Telegram padded link ${secret_index}: tg://proxy?server=${PUBLIC_HOST}&port=${PUBLIC_PORT}&secret=dd${secret}"
    fi

    secret_index=$((secret_index + 1))
done
IFS="${OLD_IFS}"

while :; do
    refresh_runtime_files
    echo "Starting mtproto-proxy"
    start_proxy

    elapsed=0
    while kill -0 "${PROXY_PID}" 2>/dev/null; do
        if [ "${elapsed}" -ge "${REFRESH_INTERVAL}" ]; then
            echo "Refresh interval reached, restarting mtproto-proxy"
            stop_proxy
            break
        fi

        sleep 1
        elapsed=$((elapsed + 1))
    done

    if [ "${elapsed}" -lt "${REFRESH_INTERVAL}" ]; then
        wait "${PROXY_PID}" || true
        echo "mtproto-proxy exited before scheduled refresh, restarting in 5 seconds"
        sleep 5
    fi
done
