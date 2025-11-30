#!/bin/bash
# 🏠 Homie Compute - One-line installer
# Run: curl -fsSL <URL>/install.sh | bash -s -- YOUR_SECRET

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

GROUP_SECRET="${1:-}"

echo ""
echo "🏠 HOMIE COMPUTE INSTALLER"
echo "=========================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required${NC}"
    echo "Install it from https://www.python.org/downloads/"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python found"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}⚠ Docker not found${NC}"
    echo ""
    echo "Please install Docker Desktop:"
    echo "  https://www.docker.com/products/docker-desktop/"
    echo ""
    echo "Then run this script again."
    exit 1
fi

if ! docker info &> /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Docker is installed but not running${NC}"
    echo ""
    echo "Please start Docker Desktop, then run this script again."
    exit 1
fi
echo -e "${GREEN}✓${NC} Docker running"

# Clone or update repo
INSTALL_DIR="$HOME/homie_cli"

if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull 2>/dev/null || true
else
    echo "Cloning repository..."
    git clone https://github.com/YOUR_USERNAME/homie_cli.git "$INSTALL_DIR" 2>/dev/null || {
        echo -e "${YELLOW}Could not clone repo. Creating local copy...${NC}"
        mkdir -p "$INSTALL_DIR"
        # If no git, user needs to copy files manually
    }
    cd "$INSTALL_DIR"
fi

# Install Python package
echo "Installing dependencies..."
pip install -e . --quiet

echo -e "${GREEN}✓${NC} Homie installed"

# Configure
if [ -n "$GROUP_SECRET" ]; then
    echo "Configuring with provided secret..."
    mkdir -p ~/.homie
    cat > ~/.homie/config.yaml << EOF
name: $(whoami)
group_secret: $GROUP_SECRET
discovery_port: 5555
worker_port: 5556
container_image: python:3.11-slim
container_cpu_limit: 2.0
container_memory_limit: 4g
container_timeout: 600
container_network: none
heartbeat_interval: 2.0
peer_timeout: 10.0
EOF
    echo -e "${GREEN}✓${NC} Configured with group secret"
else
    echo ""
    echo -e "${YELLOW}Run 'homie setup' to configure your name and group secret${NC}"
fi

echo ""
echo "================================"
echo -e "${GREEN}Installation complete!${NC}"
echo "================================"
echo ""
echo "Next steps:"
echo "  1. Run: homie setup    (if you haven't already)"
echo "  2. Run: homie up       (to start sharing)"
echo "  3. Run: homie peers    (to see who's online)"
echo ""
echo "Happy computing! 🏠"
