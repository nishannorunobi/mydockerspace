#!/bin/bash

# Script to copy files from input directory to mount directory
# Usage: bash copy_to_mount.sh <input_file_or_dir>
# Paths are configured in dockerspace/project.conf

set -e

# Source project configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/dockerspace/project.conf"
source "$SCRIPT_DIR/dockerspace/workspace.conf"

# Construct workspace paths
WORKSPACE_ROOT="$SCRIPT_DIR"
DEST_DIR="$WORKSPACE_ROOT/$MOUNTSPACE_DIR"

# Check if arguments provided or INPUT_FILE configured
if [[ -n "$INPUT_FILE" ]]; then
    # Use configured paths from project.conf
    INPUT="$SRC_DIR$INPUT_FILE"
    MOUNT_DIR="$DEST_DIR"
    echo "Using configured paths from project.conf:"
    echo "  Source: $INPUT"
    echo "  Destination: $MOUNT_DIR"
elif [[ $# -lt 1 ]]; then
    echo "Usage: bash copy_host2mount.sh [input_file_or_dir]"
    echo ""
    echo "Examples:"
    echo "  bash copy_host2mount.sh ~/Downloads/video.mp4"
    echo "  bash copy_host2mount.sh ~/Downloads/folder/"
    echo "  Or configure INPUT_FILE, SRC_DIR, DEST_DIR in dockerspace/project.conf"
    echo ""
    echo "Current config in dockerspace/project.conf:"
    echo "  INPUT_FILE: $INPUT_FILE"
    echo "  SRC_DIR: $SRC_DIR"
    echo "  DEST_DIR: $DEST_DIR"
    exit 1
else
    INPUT="$1"
    MOUNT_DIR="$DEST_DIR"
fi

# Check if input exists
if [[ ! -e "$INPUT" ]]; then
    echo "Error: Input file/directory does not exist: $INPUT"
    exit 1
fi

# Check if mount directory exists
if [[ ! -d "$MOUNT_DIR" ]]; then
    echo "Error: Mount directory does not exist: $MOUNT_DIR"
    exit 1
fi

# Copy file/directory
echo "Copying '$INPUT' to '$MOUNT_DIR'..."
cp -r "$INPUT" "$MOUNT_DIR/"

# Verify
if [[ -e "$MOUNT_DIR/$(basename "$INPUT")" ]]; then
    echo "✓ Success! File copied to: $MOUNT_DIR/$(basename "$INPUT")"
    echo "  Inside container, copy to your project input directory"
else
    echo "Error: Copy failed"
    exit 1
fi
