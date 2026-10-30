#!/usr/bin/env bash

# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

# Starts the Opportunity Desk: the neuro-san server and nsflow on localhost, and
# Caddy on $PORT in front of them with HTTP basic auth. Neither nsflow nor the
# neuro-san server authenticates requests by itself, so nothing is reachable
# without the password. The container exits when any process exits, so the host
# restarts it instead of serving half a desk.

set -o errexit -o nounset -o pipefail

cd "$(dirname "$0")/../.."

DATA_DIR="${OPPORTUNITY_DESK_DATA_DIR:-/var/data}"

# A disk mounted by the host arrives owned by root: hand it to the desk user,
# then start this script again without root.
if [[ "$(id -u)" == "0" ]]; then
    mkdir -p "${DATA_DIR}"
    chown -R desk:desk "${DATA_DIR}"
    exec setpriv --reuid=desk --regid=desk --init-groups bash "$0" "$@"
fi

# Fail closed: never serve the desk behind a weak or missing password.
MIN_PASSWORD_LENGTH=16
DESK_PASSWORD="${DESK_PASSWORD:-}"
if [[ "${#DESK_PASSWORD}" -lt "${MIN_PASSWORD_LENGTH}" ]]; then
    echo "DESK_PASSWORD must be at least ${MIN_PASSWORD_LENGTH} characters; refusing to start." >&2
    exit 1
fi
export DESK_USERNAME="${DESK_USERNAME:-owner}"
DESK_PASSWORD_HASH="$(caddy hash-password --plaintext "${DESK_PASSWORD}")"
export DESK_PASSWORD_HASH
# The agents never need the password itself.
unset DESK_PASSWORD

if [[ -z "${OPENAI_API_KEY:-}${GOOGLE_API_KEY:-}${ANTHROPIC_API_KEY:-}" ]]; then
    echo "Warning: no LLM API key is set, so every request will fail until one is." >&2
fi
if [[ ! -r "${OPPORTUNITY_DESK_PROFILE:-}" ]]; then
    echo "Warning: OPPORTUNITY_DESK_PROFILE (${OPPORTUNITY_DESK_PROFILE:-unset}) is not readable." >&2
fi

# Stop every process in the group, this script included. The trap is cleared
# first so the signal this sends to the script itself ends it instead of re-entering.
stop_all() {
    trap - TERM INT
    kill 0
}
trap stop_all TERM INT

python -m neuro_san_studio run &
caddy run --config deploy/opportunity_desk/Caddyfile --adapter caddyfile &

wait -n
echo "A desk process exited; stopping so the host restarts the container." >&2
stop_all
