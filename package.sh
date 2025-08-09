#!/bin/bash
set -euo pipefail
IFS=$'\n\t'


ln -s . BlenderLxrBakerAddon
zip BlenderLxrBakerAddon BlenderLxrBakerAddon/*.py
rm -f BlenderLxrBakerAddon