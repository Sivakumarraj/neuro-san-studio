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

# Image for the Opportunity Desk (registries/experimental/opportunity_desk.hocon):
# the neuro-san server and the nsflow web client on localhost, with Caddy in front
# of them on $PORT asking for a password. Caddy's port is the only one published.
#
# Build from the repository root, then run with your settings in an env file:
#   docker build --file deploy/opportunity_desk/Dockerfile --tag opportunity-desk .
#   docker run --env-file .env --publish 10000:10000 opportunity-desk
# Hosting on Render is described in render.yaml at the repository root.

FROM caddy:2.8.4 AS caddy

FROM python:3.13-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/usr/local/opportunity-desk

RUN useradd --create-home --uid 1001 desk

WORKDIR ${APP_HOME}

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=caddy /usr/bin/caddy /usr/local/bin/caddy

# What `python -m neuro_san_studio run` needs at runtime, and nothing else.
COPY neuro_san_studio ./neuro_san_studio
COPY registries ./registries
COPY coded_tools ./coded_tools
COPY middleware ./middleware
COPY skills ./skills
COPY config ./config
COPY logging.hocon ./
COPY deploy/opportunity_desk ./deploy/opportunity_desk

RUN mkdir -p /var/data logs && chown -R desk:desk ${APP_HOME} /var/data

# Serve only the desk, keep its tracker on the persistent disk, listen where Render expects.
ENV AGENT_MANIFEST_FILE=${APP_HOME}/registries/manifest_opportunity_desk.hocon \
    OPPORTUNITY_DESK_DATA_DIR=/var/data \
    NEURO_SAN_SERVER_HOST=localhost \
    NSFLOW_HOST=localhost \
    PORT=10000

EXPOSE 10000

# start.sh starts as root only to hand a freshly mounted disk to the desk user,
# then drops to that user before anything else runs.
CMD ["bash", "deploy/opportunity_desk/start.sh"]
