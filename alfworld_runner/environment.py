"""Lazy ALFWorld loading keeps the transport tests independent of TextWorld."""

import os
from pathlib import Path

import yaml

SPLITS = {
    "train": "train",
    "valid_seen": "eval_in_distribution",
    "valid_unseen": "eval_out_of_distribution",
}


def make_environment(config_path, split, max_steps, seed):
    from alfworld.agents.environment import get_environment

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    config["rl"]["training"]["max_nb_steps_per_episode"] = max_steps
    key = {"train": "data_path", "valid_seen": "eval_id_data_path",
           "valid_unseen": "eval_ood_data_path"}[split]
    data_path = Path(os.path.expandvars(config["dataset"][key]))
    if not data_path.is_dir():
        raise ValueError(f"Dataset missing: {data_path}. Run the download command first.")
    owner = get_environment("AlfredTWEnv")(config, train_eval=SPLITS[split])
    owner.game_files = sorted(owner.game_files)
    if not owner.game_files:
        raise ValueError(f"No solvable ALFWorld games found in {data_path}")
    # Each execution process owns its environment and upstream parser/registry.
    env = owner.init_env(batch_size=1)
    try:
        env.seed(seed)
    except BaseException:
        env.close()
        raise
    return env, owner.game_files


def download_data():
    # Reuse the pinned upstream downloader's URLs and extraction logic, but
    # omit its visual detector and pre-trained model downloads.
    import runpy
    import shutil
    from alfworld.info import ALFWORLD_DATA, ALFRED_PDDL_PATH, ALFRED_TWL2_PATH

    script = shutil.which("alfworld-download")
    if script is None:
        raise RuntimeError("alfworld-download is missing from the image")
    upstream = runpy.run_path(script, run_name="alfworld_text_download")
    destination = Path(ALFWORLD_DATA)
    marker = destination / ".text-data-0.4.2.complete"
    required = [destination / "json_2.1.1" / split for split in SPLITS]
    required += [destination / "logic" / name for name in ("alfred.pddl", "alfred.twl2")]
    if marker.is_file() and all(path.exists() for path in required):
        print(f"Text data already downloaded: {destination}")
        return
    for key in ("JSON_FILES_URL", "PDDL_FILES_URL", "TW_PDDL_FILES_URL"):
        archive = upstream["download"](upstream[key], str(destination))
        upstream["unzip"](archive, str(destination))
        Path(archive).unlink()
    logic = destination / "logic"
    logic.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ALFRED_PDDL_PATH, logic / "alfred.pddl")
    shutil.copyfile(ALFRED_TWL2_PATH, logic / "alfred.twl2")
    marker.write_text("alfworld==0.4.2\n", encoding="utf-8")
