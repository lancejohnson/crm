# Build the Groundwork CRM image.
#
# Replaces the old pipeline, which mutated the live production backend
# container and `docker commit`ed it as the next gwN tag. That stacked one
# ~32 MB layer per deploy onto the previous image and never removed anything
# (layers are append-only), so by gw228 the image was 256 layers / 14 GB with
# 227 historical copies of the frontend bundle still inside it. Every build
# here starts from the same fixed base instead, so the image stays ~30 layers
# and ~3 GB no matter how many times we deploy.

# Last upstream tag whose published image actually contains the crm app --
# upstream's image CI is broken for everything after v1.67.0.
ARG BASE_IMAGE=ghcr.io/frappe/crm:v1.67.0

FROM ${BASE_IMAGE}
ARG APP=/home/frappe/frappe-bench/apps/crm

# LAYER ORDER IS LOAD-BEARING. `yarn build` is ~40s and by far the most
# expensive step, so nothing that changes independently of the frontend may
# appear above it. crm/ (the Python app) is copied AFTER the build for exactly
# that reason: it accounts for roughly a third of our commits, and when it sat
# above the build every backend-only deploy paid the full vite cost for a
# bundle that could not have changed. Now those deploys hit the cache and skip
# the build entirely.
#
# Nothing is inherited from a previous build, so a file deleted from the repo
# cannot survive into production. The old pipeline shipped source with
# `docker cp`, which has no delete semantics -- an abandoned module (and a
# debug script holding a real buyer's PII) sat in prod for over a year.
#
# The fork pins its own vite/plugin versions (Vite 8 + Rolldown, see below), so
# node_modules can no longer be inherited unchanged from the base image. Keyed
# on package.json + yarn.lock ONLY and placed above the source copy, so it is
# cached on every build where dependencies did not change -- which is nearly all
# of them. When it does miss, expect ~150s instead of ~20s.
COPY --chown=frappe:frappe frontend/package.json frontend/yarn.lock ${APP}/frontend/
RUN cd ${APP}/frontend && yarn install --frozen-lockfile

# Vite 8 (Rolldown) rather than the Vite 5 upstream still ships. Roughly halves
# the bundle step: measured 36s -> 18s best case, ~40s -> ~25s median, and it is
# markedly more consistent under load. Upstream frappe/crm is still on vite
# ^5.4.21 and frappe-ui's develop only reached vite ^7, with no Rolldown work in
# flight, so this will not arrive on its own.
#
# vite-plugin-pwa MUST stay >= 1.x here. The 0.21.x we used to pin writes to the
# `bundle` variable in generateBundle, which Rolldown ignores -- the build still
# succeeds but silently drops registerSW.js and manifest.webmanifest, so the
# self-destroying service worker never registers and users keep being served
# stale bundles from an old SW. That is the exact bug selfDestroying exists to
# prevent, and it is invisible unless you diff the output.
COPY --chown=frappe:frappe frontend/ ${APP}/frontend/

# src/socket.js does a BUILD-TIME `import { socketio_port } from
# '../../../../sites/common_site_config.json'`, so rollup needs that key to
# exist or the build dies with "socketio_port is not exported by". At runtime
# sites/ is a named volume holding the real config, but during `docker build`
# there is no volume and the base image ships `{}` -- which is exactly why the
# old in-container build worked and this one didn't. Seed the key for the build
# and put the original file back, all in one RUN so nothing leaks into the
# image (the volume would shadow it anyway).
#
# The value is inert in production: socket.js only uses it when
# window.location.port is set, i.e. when served on an explicit port in dev.
#
# vite.config.js sets emptyOutDir:false so a build adds new content-hashed
# chunks rather than deleting the ones open tabs are still importing. Retention
# across deploys is handled by the shared crm-assets volume, not here -- see
# docker-compose.yml and the publish step in build_image.sh.
RUN CSC=/home/frappe/frappe-bench/sites/common_site_config.json \
 && cp "$CSC" /tmp/csc.orig \
 && python3 -c "import json,sys;p=sys.argv[1];d=json.load(open(p));d.setdefault('socketio_port',9000);json.dump(d,open(p,'w'))" "$CSC" \
 && cd ${APP}/frontend \
 && NODE_OPTIONS=--max-old-space-size=2048 yarn build \
 && cp /tmp/csc.orig "$CSC" && rm /tmp/csc.orig

# Below the build on purpose (see above). .dockerignore keeps crm/public/frontend
# out of the context, so this cannot clobber what yarn build just produced.
COPY --chown=frappe:frappe crm/ ${APP}/crm/

# DEAD LAST, and it has to stay here. GIT_REV changes on every single commit,
# and BuildKit invalidates everything below an ARG whose value changed -- so
# declaring this at the top (where it naturally wants to live) silently voided
# the layer cache on every deploy and made the ordering above pointless. Caught
# only because a cache test was run with the arg held constant.
ARG GIT_REV=unknown
LABEL org.opencontainers.image.revision="${GIT_REV}"
