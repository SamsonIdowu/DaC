# DaC: Detection-Engineering as Code

This repository is used to conceptualize the automation of detection engineering, in a way that the integration of rulesets such as: decoders and rules to SIEM tools are automated. This approach to detection engineering allows for faster and effective collaboration among security engineers. It also limits access to the SIEM endpoint and reduces collaboration errors in production environments.

This concept can be adapted to work with any SIEM solution by following the guide, even though [Wazuh](https://wazuh.com/) is used to develop and test this concept.

# Guide

## Requirements
Ensure that the following requirements are met to use this repository with ease:
* Ensure that [Git](https://git-scm.com/) is installed on the SIEM host.
* Ensure that the SIEM host is accessible on the internet by assigning a public IP or NAT if behind a firewall.
* Ensure that port `22` or your custom SSH port is open on the public IP address.
* Ensure that the SIEM host is provisioned with a public/private key pair, to allow for SSH login.
* Clone the parent [DaC](https://github.com/SamsonIdowu/DaC.git) repository to use its GitHub Actions workflow file.


## Configuration
Perform the configuration steps after meeting the above requirements.

### SIEM
Perform the following steps on the SIEM endpoint:

1. Navigate to the directory where the decoder and rule files are stored. If the decoder and rules files are stored in separate directories, navigate to the parent directory:
```
cd <FULL_PATH_TO_RULESETS>    # Working directory
```
2. Create a `.gitignore` file in the working directory to ignore other files in the directory from being added to Git:
```
nano .gitignore     # Add directories/files to ignore
```
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
7. Create a new branch `main` and switch to the new branch. Stage the files for commit in your local Git.  Make an initial commit to your local Git repository:
```
git checkout -b main
git add .
git commit -m "Initial commit"
```
8. Push the changes from your local Git repository to the `main` branch of remote repository:
```
git pull origin main --no-rebase   # Merge remote repo with local repo and resolve any merge conflicts manually if they appear.
git push -u origin main
```

### GitHub (Remote Repository)

Perform the following steps on your GitHub repository (remote repository) after pushing local changes:

1. Edit the GitHub Actions workflow file `.github/workflows` > `integrate_rulesets.yml` to adapt it to your SIEM tool.
2. Navigate to **Settings** > **Secrets and variables** > **Actions** > **Secrets** to create the following repository secrets to be used by GitHub Actions:

|**Name**     |**Secret**                     |
|-------------|-------------------------------|
| USERNAME    | <USERNAME_OF_SIEM_HOST>       |
| HOST        | <PUBLIC_IP_OF_SIEM_HOST>      |
| SSH_KEY     | <PRIVATE_KEY_OF_SIEM_HOST>     |
| PORT        | <SSH_PORT_OF_SIEM_HOST>       |
3. Ensure that a `dev` branch is created if it does not not already exist.
4. Create a pull request to merge the changes on the `main` branch to the `dev` branch. This will update the `dev` branch with the recent changes from the local Git repository and the `automation.yml` file.


## Usage
This guides the use of the repository to create new or modify existing rulesets for automatic integration with the SIEM after completing configuration.

### **Warning:** 
*Perform all usage operations in the `dev` branch for code reviews before merging to the `main` branch to minimize deployment errors in production.*

- ### Creating or Modifying Custom Decoders
Create new or modify existing custom decoders in the `decoders` directory of the repository. This may vary depending on the directory structure of your SIEM.

- ### Creating or Modifying Custom Rules
Create new or modify existing custom rules in the `rules` directory of the repository. This may vary depending on the directory structure of your SIEM.

# Workflows

##  Rule ID Conflict Checker for Wazuh Rulesets

- **Workflow:** [`.github/workflows/check_rule_ids.yml`](.github/workflows/check_rule_ids.yml)
- **Script:** [`check_rule_ids.py`](check_rule_ids.py)
- **Purpose:** This repository includes a GitHub Actions workflow and a Python script to **automatically check for rule ID conflicts** in Wazuh ruleset XML files (`rules/*.xml`) whenever a pull request is opened against the `main` branch. The workflow ensures that any new or modified rules in pull requests do **not reuse rule IDs** already present in the `main` branch, preventing accidental overwrites and maintaining ruleset integrity.

---

### How It Works

1. **Trigger:** The workflow runs on every pull request to the `main` branch.

2. **Steps:**
   - Checks out the PR branch and fetches the latest `main` branch.
   - Sets up Python 3.10.
   - Runs [`check_rule_ids.py`](check_rule_ids.py), which:
     - Finds all changed or added `rules/*.xml` files in the PR.
     - Extracts all `<rule id="...">` values from these files.
     - Extracts all rule IDs from `rules/*.xml` files in the `main` branch.
     - Checks for any ID overlap (conflicts).
     - Fails the workflow if any conflicts are found, listing the conflicting IDs and files.


### Example Output

```
🔍 Checking these files for conflicts: ['local_rules.xml']

🔎 Checking file: local_rules.xml
✅ No rule ID conflicts in local_rules.xml.

✅ All checked files are conflict-free.
```

If a conflict is found:

```
❌ Conflicting rule IDs in local_rules.xml file. Rule IDs: [100001]
```

### Troubleshooting

- If you see a ❌ conflict, update your rule IDs to be unique compared to those in the `main` branch.


## Wazuh Ruleset Integration Workflow

- **Workflow file:** `.github/workflows/integrate_rulesets.yml`
- **Purpose:** This repository includes a GitHub Actions workflow to **automatically update and apply Wazuh decoders and rules** on your SIEM server whenever changes are pushed to the `main` branch. On every push to `main` that modifies any `.xml` file (typically in `rules/` or `decoders/`), the workflow connects to your SIEM server via SSH and:
  - Pulls the latest changes.
  - Updates file permissions for decoders and rules.
  - Restarts the Wazuh manager to apply the new rulesets.
  - Prints the status of the Wazuh manager.

---

### How It Works

1. **Trigger:**
   - On push to `main` branch affecting any `.xml` file.
   - Can also be run manually via the GitHub Actions UI (`workflow_dispatch`).

2. **Steps:**
   - Uses the [appleboy/ssh-action](https://github.com/appleboy/ssh-action) to SSH into your SIEM server.
   - Runs a script that:
     - Changes to `/var/ossec/etc/`
     - Pulls the latest code from the `main` branch.
     - Sets correct ownership and permissions for all decoders and rules.
     - Restarts the Wazuh manager.
     - Prints the status of the Wazuh manager service.

### Security

- SSH credentials (`HOST`, `USERNAME`, `SSH_KEY`, `PORT`) are stored as **GitHub Actions secrets** and never exposed in logs.
- Only users with access to your repository and secrets can trigger this workflow.

### Example Output

```
Ruleset apply SUCCESS!!! - Wazuh manager restarted successfully.
<status output>
```
or
```
Ruleset apply FAILURE!!! - Wazuh manager failed to restart, check ruleset for error...
<status output>
```

### Troubleshooting

- If the workflow fails, check the Actions logs for error messages.
- Ensure your SSH key and user have the necessary permissions on the SIEM server.
- Make sure the SIEM server can pull from your repository (deploy keys, access rights, etc.).
