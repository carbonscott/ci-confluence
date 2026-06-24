#!/usr/bin/env bash
set -euo pipefail

greet() {
    local name="$1"
    echo "hello, ${name}"
}

greet "world"
