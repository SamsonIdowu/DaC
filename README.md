# DaC: Detection-Engineering as Code

This repository is used to conceptualize the automation of detection engineering, in a way that the integration of rulesets such as: decoders and rules to SIEM tools are automated. This approach to detection engineering allows for faster and effective collaboration among security engineers. It also limits access to the SIEM endpoint and reduces collaboration errors in production environments.

This concept can be adapted to work with any SIEM solution by following the guide, even though [Wazuh](https://wazuh.com/) is used to develop and test this concept.

> **Security model:** whatever is merged to `main` is applied to the SIEM by a root process. Treat write access to this repository, its branch rules and its Actions secrets with the same care as root access to the SIEM host. The setup below is built around that.

# Guide

## Requirements
Ensure that the following requirements are met to use this repository with ease:
* Ensure that [Git](https://git-scm.com/) is installed on the SIEM host.
* Ensure that the GitHub Actions runner can reach the SIEM host over SSH. Prefer a [self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners) inside your network, or a VPN/bastion. If you must expose SSH on a public IP (or NAT), allow key-based login only, disable root login, and restrict the source addresses as far as you can.
* Ensure that port `22` or your custom SSH port is reachable from the runner.
* Create a dedicated, non-root deploy user on the SIEM host and a **new SSH key pair for it** (do not reuse the host's own keys). The public key goes in that user's `~/.ssh/authorized_keys`; the private key becomes the `SSH_KEY` secret.
* Clone the parent [DaC](https://github.com/SamsonIdowu/DaC.git) repository to use its GitHub Actions workflow files and deploy script.


## Configuration
Perform the configuration steps after meeting the above requirements.

### SIEM
Perform the following steps on the SIEM endpoint:

1. Navigate to the directory where the decoder and rule files are stored. If the decoder and rules files are stored in separate directories, navigate to the parent directory:
```
cd <FULL_PATH_TO_RULESETS>    # Working directory, /var/ossec/etc for Wazuh
```
2. Copy this repository's [`.gitignore`](.gitignore) into the working directory. It is an **allow-list**: everything is ignored except the rulesets and the files this repository needs, so secrets that live next to the rulesets (`client.keys`, `authd.pass`, `sslmanager.key`, `ossec.conf`, ...) can never be committed by `git add .`. Extend the allow-list only for files you intend to manage through Git.
3. Mark the working directory as safe for Git:
```
git config --global --add safe.directory <FULL_PATH_TO_RULESETS>
```
4. Initialize the working directory as a Git repository:
```
git init
```
5. Add a remote repository to your local Git to push local changes:
```
git remote add origin <REMOTE_REPOSITORY>
```
6. Configure your Git user identity:
```
git config --global user.name <YOUR_NAME>
git config --global user.email <YOUR_EMAIL_ADDRESS>
```
7. Create a new branch `main` and switch to the new branch. Stage the files for commit in your local Git. Check what is staged before committing, then make an initial commit to your local Git repository:
```
git checkout -b main
git add .
git status        # Only rulesets and repository files should be listed
git commit -m "Initial commit"
```
8. Push the changes from your local Git repository to the `main` branch of remote repository:
```
git pull origin main --no-rebase   # Merge remote repo with local repo and resolve any merge conflicts manually if they appear.
git push -u origin main
```
9. After the initial push, replace any credentials with write access on the SIEM with a **read-only** [deploy key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys). The SIEM only ever needs to fetch, and a compromised SIEM should not be able to push to the repository.
10. Install the deploy script **outside** the Git working tree, so that repository changes cannot alter what runs as root, and allow the deploy user to run only that command:
```
sudo install -o root -g root -m 0755 deploy/dac-deploy.sh /usr/local/sbin/dac-deploy
sudo visudo -f /etc/sudoers.d/dac-deploy
# Add this single line, replacing <DEPLOY_USER>. The trailing "" forbids arguments.
<DEPLOY_USER> ALL=(root) NOPASSWD: /usr/local/sbin/dac-deploy ""
```
Remove any broader `sudo` rights the deploy user had. Whenever `deploy/dac-deploy.sh` changes in the repository, review it and re-run the `install` command; the copy in the working tree is never executed.

11. Record the SSH host key fingerprint for the `HOST_FINGERPRINT` secret:
```
ssh-keygen -l -E sha256 -f /etc/ssh/ssh_host_ed25519_key.pub    # SHA256:...
```

### GitHub (Remote Repository)

Perform the following steps on your GitHub repository (remote repository) after pushing local changes:

1. Edit the GitHub Actions workflow file `.github/workflows` > `integrate_rulesets.yml` and the deploy script `deploy/dac-deploy.sh` to adapt them to your SIEM tool.
2. Navigate to **Settings** > **Environments** and create an environment named `production`:
   - Under **Deployment branches and tags**, select **Selected branches and tags** and allow only `main`.
   - Optionally add **Required reviewers** so each deployment needs a manual approval.
3. In the `production` environment, add the following **environment secrets**. Do not create them as repository secrets: repository secrets can be read by a workflow pushed to any branch, while environment secrets are only released to jobs that pass the environment's branch rules.

|**Name**          |**Secret**                                                   |
|------------------|-------------------------------------------------------------|
| USERNAME         | <DEPLOY_USER_ON_SIEM_HOST>                                  |
| HOST             | <IP_OR_HOSTNAME_OF_SIEM_HOST>                               |
| SSH_KEY          | <PRIVATE_KEY_OF_THE_DEPLOY_KEY_PAIR>                        |
| PORT             | <SSH_PORT_OF_SIEM_HOST>                                     |
| HOST_FINGERPRINT | <SHA256_HOST_KEY_FINGERPRINT> (from SIEM step 11)           |

4. Delete any old repository-level copies of these secrets under **Settings** > **Secrets and variables** > **Actions**.
5. Apply the branch ruleset in [`branch_rules/protect_main.json`](branch_rules/protect_main.json) under **Settings** > **Rules** > **Rulesets** (**New ruleset** > **Import a ruleset**, or update the existing one). It requires a pull request with an approving code-owner review, signed commits, no force pushes, and a passing `check-rule-ids` check. Edit [`.github/CODEOWNERS`](.github/CODEOWNERS) to list your reviewers. GitHub does not let authors approve their own pull requests, so a single-maintainer repository needs a second reviewer, or a bypass entry for the admin role in the ruleset.
6. Under **Settings** > **Actions** > **General**, set **Workflow permissions** to **Read repository contents**.
7. Ensure that a `dev` branch is created if it does not already exist.
8. Create a pull request to merge the changes on the `main` branch to the `dev` branch. This will update the `dev` branch with the recent changes from the local Git repository and the workflow files (`check_rule_ids.yml` and `integrate_rulesets.yml`).


## Usage
This guides the use of the repository to create new or modify existing rulesets for automatic integration with the SIEM after completing configuration.

### **Warning:** 
*Perform all usage operations in the `dev` branch for code reviews before merging to the `main` branch to minimize deployment errors in production.*

- ### Creating or Modifying Custom Decoders
Create new or modify existing custom decoders in the `decoders` directory of the repository. Only top-level `*.xml` files are deployed.

- ### Creating or Modifying Custom Rules
Create new or modify existing custom rules in the `rules` directory of the repository. Only top-level `*.xml` files are deployed. Use rule IDs between `100000` and `120000`; IDs below that belong to the built-in Wazuh ruleset.

- ### Changing anything else on the SIEM
The deploy script refuses any update that touches files outside its allow-list (for example `ossec.conf`, `shared/agent.conf` or `lists/`). Change those on the SIEM directly, or deliberately extend `ALLOWED_PATHS` in `deploy/dac-deploy.sh` and reinstall it.

# Workflows

##  Ruleset Checker for Wazuh Rulesets

- **Workflow:** [`.github/workflows/check_rule_ids.yml`](.github/workflows/check_rule_ids.yml)
- **Script:** [`check_rule_ids.py`](check_rule_ids.py)
- **Purpose:** Runs on every pull request to `main` and validates the ruleset that would be deployed if the pull request were merged. It **fails closed**: anything it cannot read or parse fails the check instead of being skipped.

---

### How It Works

1. **Trigger:** The workflow runs on every pull request to the `main` branch. GitHub checks out the merge of the pull request into `main`, so the script sees exactly the files that would be deployed.

2. **Checks:** [`check_rule_ids.py`](check_rule_ids.py) validates the whole tree, so renamed or moved files and duplicates across several files in one pull request are all caught.
   - **Errors** (fail the check):
     - A symlink anywhere in the repository.
     - A file under `rules/` or `decoders/` that is not a top-level `*.xml` file.
     - A `rules/` or `decoders/` file that cannot be read or is not well-formed XML. Wazuh-style files with several top-level elements, an XML declaration, or a bare `&` are accepted.
     - A `<rule>` without a numeric `id`.
     - A rule ID defined more than once, in the same file or in different files.
     - A rule ID outside `100000`-`120000` without `overwrite="yes"`.
   - **Warnings** (shown as annotations for reviewers):
     - Rules with `overwrite="yes"`, which replace an existing rule.
     - Rules with `level="0"`, which silence every event they match.

You can run the same check locally before opening a pull request:
```
python3 check_rule_ids.py
```

### Example Output

```
🔍 Checked 2 ruleset file(s), 1 rule(s): 0 error(s), 0 warning(s).
✅ Ruleset check passed.
```

If a conflict is found:

```
❌ rules/new_rules.xml:3: rule id 100001 is defined 2 times (rules/local_rules.xml:12, rules/new_rules.xml:3)
❌ rules/local_rules.xml:12: rule id 100001 is defined 2 times (rules/local_rules.xml:12, rules/new_rules.xml:3)

🔍 Checked 3 ruleset file(s), 2 rule(s): 2 error(s), 0 warning(s).
❌ Ruleset check failed.
```

### Troubleshooting

- If you see a ❌ conflict, update your rule IDs to be unique across all files in `rules/`.
- If you see an XML parse error, fix the file at the reported line.

### Limitation

The check confirms the files are well-formed and the IDs are sound, not that Wazuh will accept every rule. The deploy script runs Wazuh's own configuration test (`wazuh-analysisd -t`) before restarting the manager and rolls back if it fails.


## Wazuh Ruleset Integration Workflow

- **Workflow file:** `.github/workflows/integrate_rulesets.yml`
- **Deploy script:** [`deploy/dac-deploy.sh`](deploy/dac-deploy.sh), installed on the SIEM as `/usr/local/sbin/dac-deploy`
- **Purpose:** **Automatically update and apply Wazuh decoders and rules** on your SIEM server whenever changes to `rules/*.xml` or `decoders/*.xml` are pushed to the `main` branch.

---

### How It Works

1. **Trigger:**
   - On push to `main` branch affecting `rules/*.xml` or `decoders/*.xml`.
   - Can also be run manually from `main` via the GitHub Actions UI (`workflow_dispatch`).
   - Deployments never run in parallel (`concurrency: siem-deploy`).

2. **Steps:**
   - Runs in the `production` environment, which releases the SSH secrets only to `main`.
   - Fails if `HOST_FINGERPRINT` is not set, then uses [appleboy/ssh-action](https://github.com/appleboy/ssh-action) (pinned to a commit SHA) to SSH into the SIEM with host key verification.
   - Runs `sudo /usr/local/sbin/dac-deploy`, which:
     - Refuses to deploy if tracked files were edited on the server, if `main`'s history was rewritten, if the update touches any path outside its allow-list, or if it contains a symlink.
     - Checks out the new commit of `main` and sets ownership and permissions on regular ruleset files only.
     - Tests the configuration with `wazuh-analysisd -t`.
     - Restarts the Wazuh manager and confirms it is running.
     - If the test or restart fails, rolls back to the previous commit, restarts the manager on the known-good ruleset, and fails the workflow run.
     - Prints the status of the Wazuh manager service.

### Security

- SSH credentials (`HOST`, `USERNAME`, `SSH_KEY`, `PORT`, `HOST_FINGERPRINT`) are stored as **environment secrets** on `production`, which only the `main` branch can use.
- Changes reach `main` only through a pull request with a code-owner approval and a passing `check-rule-ids` check (see [`branch_rules/protect_main.json`](branch_rules/protect_main.json)).
- The deploy user can run only `/usr/local/sbin/dac-deploy` as root, and that script lives outside the repository.
- Third-party actions are pinned to full commit SHAs, and the workflows' `GITHUB_TOKEN` is read-only.

### Example Output

```
[dac-deploy] Ruleset apply SUCCESS!!! - Wazuh manager restarted successfully on <commit>.
<status output>
```
or
```
[dac-deploy] FAILURE: wazuh-analysisd rejected the new ruleset. Rolling back to <previous commit>.
[dac-deploy] Wazuh manager restarted on the previous ruleset (<previous commit>).
<status output>
```

### Troubleshooting

- If the workflow fails, check the Actions logs for error messages. A failed deployment leaves the SIEM on the previous ruleset.
- `tracked files ... were edited on the server`: someone changed a managed file directly on the SIEM. Bring the change into Git through a pull request, or discard it with `git checkout -- <file>`, then re-run the workflow.
- `the update changes paths outside the deploy allow-list`: a commit on `main` touched a file the SIEM does not manage through Git. Revert it, or extend `ALLOWED_PATHS` on purpose.
- Ensure your SSH key and user have the necessary permissions on the SIEM server, and that the sudoers entry matches the command exactly.
- Make sure the SIEM server can fetch from your repository (read-only deploy key).
