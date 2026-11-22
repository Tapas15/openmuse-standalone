FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    USER=browser \
    HOME=/home/browser \
    DISPLAY=:0 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080 \
    RESOLUTION=1920x1080x24

# GUI + runtime dependencies for Chromium-based BrowserOS
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      wget \
      curl \
      xvfb \
      x11vnc \
      novnc \
      websockify \
      fluxbox \
      x11-utils \
      procps \
      fonts-liberation \
      fonts-noto-color-emoji \
      libasound2t64 \
      libatk-bridge2.0-0 \
      libatk1.0-0 \
      libcups2 \
      libdbus-1-3 \
      libdrm2 \
      libgbm1 \
      libgtk-3-0 \
      libnspr4 \
      libnss3 \
      libx11-xcb1 \
      libxcomposite1 \
      libxdamage1 \
      libxfixes3 \
      libxkbcommon0 \
      libxrandr2 \
      xdg-utils \
      socat \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash "$USER" \
    && mkdir -p "$HOME/data" /downloads \
    && chown -R "$USER:$USER" "$HOME" /downloads \
    && ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html

# Optional: place BrowserOS Linux installer in ./installer/ (.deb preferred, .AppImage supported).
# If no local installer is found, install-browseros.sh downloads from BrowserOS CDN.
# Override with build args/env if needed:
#   --build-arg BROWSEROS_INSTALLER_URL=https://.../BrowserOS_neo.deb
#   --build-arg BROWSEROS_APPIMAGE_URL=https://.../BrowserOS_neo.AppImage
ARG BROWSEROS_INSTALLER_URL=https://cdn.browseros.com/download/BrowserOS_neo.deb
ARG BROWSEROS_APPIMAGE_URL=https://cdn.browseros.com/download/BrowserOS_neo.AppImage
ENV BROWSEROS_INSTALLER_URL=${BROWSEROS_INSTALLER_URL} \
    BROWSEROS_APPIMAGE_URL=${BROWSEROS_APPIMAGE_URL}
COPY installer/ /tmp/installer/
COPY install-browseros.sh /usr/local/bin/install-browseros.sh
RUN chmod +x /usr/local/bin/install-browseros.sh \
    && /usr/local/bin/install-browseros.sh \
    && rm -rf /tmp/installer

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

USER root
WORKDIR /home/browser

EXPOSE 5900 6080

ENTRYPOINT ["/usr/local/bin/start.sh"]
