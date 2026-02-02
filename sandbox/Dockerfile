# Aura LaTeX Sandbox
# Full TeX Live image - already includes most academic packages

FROM texlive/texlive:latest

# Install additional system tools
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Default command
CMD ["/bin/bash"]
