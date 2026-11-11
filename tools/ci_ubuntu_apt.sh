#!/usr/bin/env bash
# CI runner only. Keep standard Ubuntu signing keys and suites intact.
set -euo pipefail

if [[ $# == 0 ]]; then
  echo "::error::Specify Ubuntu packages to install."
  exit 2
fi
for package in "$@"; do
  if [[ ! $package =~ ^[a-z0-9][a-z0-9+.-]*$ ]]; then
    echo "::error::Invalid Ubuntu package name."
    exit 2
  fi
done

installed=1
for package in "$@"; do
  if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null) != 'install ok installed' ]]; then
    installed=0
    break
  fi
done
if [[ $installed == 1 ]]; then
  echo "Required Ubuntu packages are already installed."
  exit 0
fi

apt_network=(-o Acquire::Retries=2 -o Acquire::http::Timeout=25 -o Acquire::https::Timeout=25 -o Acquire::Languages=none)
fetch_packages() {
  sudo timeout --kill-after=10s 90s apt-get "${apt_network[@]}" -o APT::Update::Error-Mode=any update &&
    sudo timeout --kill-after=10s 6m apt-get "${apt_network[@]}" install --yes --no-install-recommends --download-only "$@"
}

sources=/etc/apt/sources.list.d/ubuntu.sources
mirror='(https?://azure[.]archive[.]ubuntu[.]com/ubuntu|mirror[+]file:/etc/apt/apt-mirrors[.]txt)'
if grep -Eq "${mirror}([[:space:]]|$)" "$sources"; then
  template=$(cat "$sources")
  fetched=0
  for archive in https://mirrors.mit.edu/ubuntu https://archive.ubuntu.com/ubuntu https://mirrors.edge.kernel.org/ubuntu; do
    if ! curl --fail --silent --show-error --head --max-time 6 --output /dev/null "$archive/dists/noble/InRelease"; then
      continue
    fi
    echo "Trying Ubuntu dependencies from $archive with APT signature checks."
    printf '%s\n' "$template" |
      sed -E "s@${mirror}([[:space:]]|$)@${archive}\2@g" |
      sudo tee "$sources" > /dev/null
    if fetch_packages "$@"; then
      fetched=1
      break
    fi
  done
  if [[ $fetched == 0 ]]; then
    echo "::error::No configured Ubuntu archive delivered the required dependencies."
    exit 1
  fi
else
  fetch_packages "$@"
fi

# Only downloads are retried. Package installation runs once from the acquired files.
sudo apt-get install --yes --no-install-recommends --no-download "$@"
