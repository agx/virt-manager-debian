#!/bin/sh

# At least check we can execute the main binary
# to catch missing python dependenies

set -e

xvfb-run virt-manager --help
