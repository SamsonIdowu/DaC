#!/usr/bin/env bash
# DaC deploy script for the Wazuh manager.
#
# The "Update Rulesets on SIEM" workflow runs this over SSH as
# `sudo /usr/local/sbin/dac-deploy`. It must NOT be run from the Git checkout:
# anything in the repository can be changed by a pull request, so a script that
# runs as root has to live outside it. Install (and re-install after reviewing
# any change to this file) as root:
#
#   install -o root -g root -m 0755 deploy/dac-deploy.sh /usr/local/sbin/dac-deploy
#
# and give the deploy user permission to run only this command, with no
# arguments (`visudo -f /etc/sudoers.d/dac-deploy`):
#
#   <DEPLOY_USER> ALL=(root) NOPASSWD: /usr/local/sbin/dac-deploy ""
#
# What it does:
#   1. Fetches main and refuses to deploy if the working tree has local edits,
#      if main's history was rewritten, if the update touches any path outside
#      the allow-list below (e.g. ossec.conf, shared/agent.conf), or if it
#      contains a symlink.
#   2. Checks out the new commit and fixes ownership/permissions of regular
#      files only (never following symlinks).
#   3. Tests the configuration with wazuh-analysisd -t, then restarts
#      wazuh-manager. If either step fails it rolls back to the previous commit,
#      restarts the manager on the known-good ruleset, and exits non-zero so the
#      workflow run fails.

set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
umask 0027

REPO_DIR=/var/ossec/etc
REMOTE=origin
BRANCH=main
WAZUH_OWNER=wazuh:wazuh
ANALYSISD=/var/ossec/bin/wazuh-analysisd
SERVICE=wazuh-manager
LOCK_FILE=/run/lock/dac-deploy.lock

# Paths a deployment may add, change, or delete. Everything else in
# /var/ossec/etc (ossec.conf, client.keys, authd.pass, shared/, lists/, ...) is
# off limits, even if a commit on main tries to change it.
ALLOWED_PATHS='^(rules/[^/]+\.xml|decoders/[^/]+\.xml|\.github/[^/]+(/[^/]+)*|\.gitignore|README\.md|check_rule_ids\.py|branch_rules/[^/]+\.json|deploy/dac-deploy\.sh)$'

log()  { printf '[dac-deploy] %s\n' "$*"; }
fail() { printf '[dac-deploy] ERROR: %s\n' "$*" >&2; exit 1; }

[[ $# -eq 0 ]] || fail "this command takes no arguments"
[[ $EUID -eq 0 ]] || fail "must run as root (sudo /usr/local/sbin/dac-deploy)"
[[ -x $ANALYSISD ]] || fail "$ANALYSISD not found; cannot test the configuration"

exec 9>"$LOCK_FILE"
flock -n 9 || fail "another deployment is already running"

cd "$REPO_DIR"

fix_permissions() {
  # -type f never matches a symlink, and find does not follow links by default.
  find "$REPO_DIR/rules" "$REPO_DIR/decoders" -maxdepth 1 -type f \
    -exec chown -h "$WAZUH_OWNER" {} + -exec chmod 0660 {} +
}

show_status() {
  systemctl status "$SERVICE" -l --no-pager || true
}

prev=$(git rev-parse --verify HEAD^{commit})

if [[ -n $(git status --porcelain --untracked-files=no) ]]; then
  git status --short --untracked-files=no >&2
  fail "tracked files in $REPO_DIR were edited on the server; commit those changes through a pull request (or discard them) before deploying"
fi

git fetch --quiet "$REMOTE" "$BRANCH"
target=$(git rev-parse --verify FETCH_HEAD^{commit})

git merge-base --is-ancestor "$prev" "$target" \
  || fail "$REMOTE/$BRANCH ($target) does not contain the deployed commit ($prev); history was rewritten, refusing to deploy"

changed=$(mktemp "${TMPDIR:-/tmp}/dac-deploy.XXXXXX")
trap 'rm -f "$changed"' EXIT
git diff --name-only --no-renames -z "$prev" "$target" >"$changed"

blocked=()
while IFS= read -r -d '' path; do
  [[ $path =~ $ALLOWED_PATHS ]] || blocked+=("$path")
done <"$changed"
if (( ${#blocked[@]} )); then
  printf '  %q\n' "${blocked[@]}" >&2
  fail "the update changes paths outside the deploy allow-list (listed above)"
fi

if git ls-tree -r "$target" | awk '$1 == "120000" { found = 1 } END { exit !found }'; then
  fail "$target contains a symlink; refusing to deploy"
fi

rollback() {
  log "FAILURE: $1. Rolling back to $prev."
  git reset --hard --quiet "$prev"
  fix_permissions
  if systemctl restart "$SERVICE"; then
    log "Wazuh manager restarted on the previous ruleset ($prev)."
  else
    log "Wazuh manager also failed to start on the previous ruleset. Manual action required."
  fi
  show_status
  exit 1
}

log "Deploying $prev -> $target"
git reset --hard --quiet "$target" || rollback "could not check out $target"
fix_permissions || rollback "could not set ruleset file permissions"

log "Testing configuration with $ANALYSISD -t"
"$ANALYSISD" -t || rollback "wazuh-analysisd rejected the new ruleset"

systemctl restart "$SERVICE" || rollback "$SERVICE failed to restart"
sleep 5
systemctl is-active --quiet "$SERVICE" || rollback "$SERVICE is not running after the restart"

log "Ruleset apply SUCCESS!!! - Wazuh manager restarted successfully on $target."
show_status
