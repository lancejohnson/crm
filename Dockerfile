# Build the Groundwork CRM image.
#
# Replaces the old pipeline, which mutated the live production backend
# container and `docker commit`ed it as the next gwN tag. That stacked one
# ~32 MB layer per deploy onto the previous image and never removed anything
# (layers are append-only), so by gw228 the image was 256 layers / 14 GB with
# 227 historical copies of the frontend bundle still inside it. Every build
# here starts from the same fixed base instead, so the image stays ~32 layers
# and ~3 GB no matter how many times we deploy.

# Last upstream tag whose published image actually contains the crm app --
# upstream's image CI is broken for everything after v1.67.0.
ARG BASE_IMAGE=ghcr.io/frappe/crm:v1.67.0
# The previous deploy's image. Used ONLY to carry its built assets forward.
# Defaults to the base so a from-scratch build works with no prior image.
ARG PREV_IMAGE=ghcr.io/frappe/crm:v1.67.0

# Vite content-hashes every chunk, and a one-line edit to a single component
# re-hashes ~124 of the 127 chunks. Shipping only the new set 404s every tab
# that later lazy-loads a route it hadn't visited yet -- which threw the SPA
# and lost whatever the user had typed. Keep a week of previous bundles alive.
#
# The prune runs HERE, in a stage that gets thrown away, rather than after the
# COPY below: deleting files in a later layer only writes whiteouts, so the
# bytes would still ship. Pruning first means only survivors are ever copied.
FROM ${PREV_IMAGE} AS prev
RUN find /home/frappe/frappe-bench/apps/crm/crm/public/frontend/assets \
      -type f -mtime +7 -delete

FROM ${BASE_IMAGE}
ARG APP=/home/frappe/frappe-bench/apps/crm
ARG GIT_REV=unknown
LABEL org.opencontainers.image.revision="${GIT_REV}"

# Nothing is inherited from the previous build, so a file deleted from the repo
# cannot survive into production. The old pipeline shipped source with
# `docker cp`, which has no delete semantics -- an abandoned module (and a
# debug script holding a real buyer's PII) sat in prod for over a year.
#
# There is deliberately no `yarn install`: node_modules comes from the base and
# the fork has never changed package.json or yarn.lock. If that ever changes,
# add an install step keyed on those two files so the layer cache still works.
COPY --chown=frappe:frappe crm/      ${APP}/crm/
COPY --chown=frappe:frappe frontend/ ${APP}/frontend/
COPY --from=prev --chown=frappe:frappe \
     ${APP}/crm/public/frontend/assets/ ${APP}/crm/public/frontend/assets/

# vite.config.js sets emptyOutDir:false, so this adds the new content-hashed
# chunks alongside the carried-forward ones instead of replacing them.
RUN cd ${APP}/frontend \
 && NODE_OPTIONS=--max-old-space-size=2048 yarn build
