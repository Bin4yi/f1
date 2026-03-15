#!/usr/bin/env bash
# =============================================================================
# AeroMind 2026 — Memgraph VM Startup Script
# Runs automatically when the Compute Engine VM boots via --metadata startup-script
# Installs Docker and starts Memgraph graph database
# =============================================================================

set -euo pipefail

echo "[AeroMind] Memgraph startup script running..."

# Install Docker if not present
if ! command -v docker &> /dev/null; then
  apt-get update -y
  apt-get install -y docker.io
  systemctl enable docker
  systemctl start docker
  echo "[AeroMind] Docker installed"
fi

# Pull and run Memgraph
docker pull memgraph/memgraph:latest

# Create systemd service so Memgraph auto-restarts on VM reboot
cat > /etc/systemd/system/memgraph.service << 'EOF'
[Unit]
Description=Memgraph Graph Database
After=docker.service
Requires=docker.service

[Service]
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/docker stop memgraph
ExecStartPre=-/usr/bin/docker rm memgraph
ExecStart=/usr/bin/docker run \
  --name memgraph \
  -p 7687:7687 \
  -v /var/lib/memgraph:/var/lib/memgraph \
  memgraph/memgraph:latest \
  --bolt-port=7687 \
  --log-level=WARNING \
  --memory-limit=2048

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable memgraph
systemctl start memgraph

echo "[AeroMind] Memgraph started on port 7687"
