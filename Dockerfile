FROM odoo:18.0

USER root
# Install Thai fonts and clear cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-thai-tlwg && \
    fc-cache -fv && \
    rm -rf /var/lib/apt/lists/*

USER odoo
