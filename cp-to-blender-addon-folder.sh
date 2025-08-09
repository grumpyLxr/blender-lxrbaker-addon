#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

readonly blender_version="4.5"
readonly blender_addon_dir="${HOME}/.config/blender/${blender_version}/scripts/addons/BlenderLxrBakerAddon"

for file in ${blender_addon_dir}/*.py; do
    [ -e "${file}" ] || continue
    rm -v "${file}"
done
cp -v *.py "${blender_addon_dir}/"
