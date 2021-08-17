import os
import subprocess
import time
import traceback
import click_spinner
from typing import List, Optional

import yaml

import typer

from ..cli.utils import (
    log_title,
    fetch_runner_logs,
    exec_in_robusta_runner,
    PLAYBOOKS_DIR,
)


app = typer.Typer()


@app.command()
def deploy(playbooks_directory: str):
    """deploy playbooks"""
    log_title("Updating playbooks...")
    with fetch_runner_logs():
        subprocess.check_call(
            f"kubectl create configmap -n robusta robusta-config --from-file {playbooks_directory} -o yaml --dry-run | kubectl apply -f -",
            shell=True,
        )
        subprocess.check_call(
            f'kubectl annotate pods -n robusta --all --overwrite "playbooks-last-modified={time.time()}"',
            shell=True,
        )
        time.sleep(
            5
        )  # wait five seconds for the runner to actually reload the playbooks
    log_title("Deployed playbooks!")


def get_runner_configmap():
    configmap_content = subprocess.check_output(
        f"kubectl get configmap -n robusta robusta-config -o yaml",
        shell=True,
    )
    return yaml.safe_load(configmap_content)


@app.command()
def pull(
    playbooks_directory: str = typer.Option(
        None,
        help="Local target directory",
    )
):
    """pull cluster deployed playbooks"""
    if not playbooks_directory:
        playbooks_directory = os.path.join(os.getcwd(), PLAYBOOKS_DIR)

    log_title(f"Pulling playbooks into {playbooks_directory} ")

    try:
        playbooks_config = get_runner_configmap()

        for file_name in playbooks_config["data"].keys():
            playbook_file = os.path.join(playbooks_directory, file_name)
            with open(playbook_file, "w") as f:
                f.write(playbooks_config["data"][file_name])

    except Exception as e:
        typer.echo(f"Failed to pull deployed playbooks {e}", traceback.print_exc())


def print_yaml_if_not_none(key: str, json_dict: dict):
    if json_dict.get(key):
        json = {}
        json[key] = json_dict.get(key)
        typer.echo(f"{yaml.dump(json)}")


@app.command("list")
def list_():  # not named list as that would shadow the builtin list function
    """list current active playbooks"""
    typer.echo(f"Getting deployed playbooks list...")
    with click_spinner.spinner():
        playbooks_config = get_runner_configmap()

    active_playbooks_file = playbooks_config["data"]["active_playbooks.yaml"]
    active_playbooks_yaml = yaml.safe_load(active_playbooks_file)
    for playbook in active_playbooks_yaml["active_playbooks"]:
        log_title(f"Playbook: {playbook['name']}")
        print_yaml_if_not_none("name", playbook)
        print_yaml_if_not_none("sinks", playbook)
        print_yaml_if_not_none("trigger_params", playbook)
        print_yaml_if_not_none("action_params", playbook)


@app.command()
def show_config():
    """fetch and show active_playbooks.yaml from cluster"""
    typer.echo("connecting to cluster...")
    with click_spinner.spinner():
        playbooks_config = get_runner_configmap()
    active_playbooks_file = playbooks_config["data"]["active_playbooks.yaml"]
    log_title("Contents of active_playbooks.yaml:")
    typer.echo(active_playbooks_file)


@app.command()
def trigger(
    trigger_name: str,
    param: Optional[List[str]] = typer.Argument(
        None,
        help="data to send to playbook (can be used multiple times)",
        metavar="key=value",
    ),
):
    """trigger a manually run playbook"""
    log_title("Triggering playbook...")
    trigger_params = " ".join([f"-F '{p}'" for p in param])
    with fetch_runner_logs():
        cmd = f"curl -X POST -F 'trigger_name={trigger_name}' {trigger_params} http://localhost:5000/api/trigger"
        exec_in_robusta_runner(
            cmd,
            tries=3,
            error_msg="Cannot trigger playbook - usually this means Robusta just started. Will try again",
        )
        typer.echo("\n")
    log_title("Done!")


if __name__ == "__main__":
    app()